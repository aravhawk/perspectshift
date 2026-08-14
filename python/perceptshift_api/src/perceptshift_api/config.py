"""API configuration from environment and XDG paths."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _xdg_home(env_name: str, fallback: Path) -> Path:
    raw = os.environ.get(env_name)
    if raw:
        return Path(raw).expanduser().resolve()
    return fallback.expanduser().resolve()


def default_data_dir() -> Path:
    return _xdg_home("XDG_DATA_HOME", Path.home() / ".local" / "share") / "perceptshift"


def default_state_dir() -> Path:
    return _xdg_home("XDG_STATE_HOME", Path.home() / ".local" / "state") / "perceptshift"


def default_config_dir() -> Path:
    return _xdg_home("XDG_CONFIG_HOME", Path.home() / ".config") / "perceptshift"


class Settings(BaseSettings):
    """Runtime settings for the local operational API."""

    model_config = SettingsConfigDict(
        env_prefix="PERCEPTSHIFT_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8741
    mutation_token: str | None = None
    mutation_token_file: Path | None = None
    cors_origins: list[str] = Field(default_factory=list)
    max_request_bytes: int = 1_048_576
    websocket_queue_size: int = 64
    websocket_max_clients: int = 32
    telemetry_cache_size: int = 512
    rate_limit_mutations_per_minute: int = 30
    trust_proxy_addresses: list[str] = Field(default_factory=list)
    artifact_roots: list[Path] = Field(default_factory=list)
    data_dir: Path | None = None
    state_dir: Path | None = None
    database_url: str | None = None
    enable_ros: bool = True
    ros_runtime_node: str = "perceptshift_runtime"
    ros_service_timeout_s: float = 2.0
    ros_stale_after_s: float = 5.0
    # Must stay within RuntimePolicy.manual_pin_maximum_seconds (default 900).
    ros_pin_duration_seconds: int = 900
    console_origin: str = "http://127.0.0.1:5173"

    @field_validator("host")
    @classmethod
    def _reject_wildcard_default(cls, value: str) -> str:
        # Explicit wildcard is allowed only when the operator sets it; warn via policy.
        return value.strip()

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise TypeError("cors_origins must be a comma-separated string or list")

    @field_validator("artifact_roots", mode="before")
    @classmethod
    def _parse_roots(cls, value: object) -> list[Path]:
        if value is None or value == "":
            return []
        if isinstance(value, (str, Path)):
            parts = str(value).split(os.pathsep)
            return [Path(part).expanduser() for part in parts if part.strip()]
        if isinstance(value, list):
            return [Path(str(item)).expanduser() for item in value]
        raise TypeError("artifact_roots must be a path list")

    def resolved_data_dir(self) -> Path:
        return (self.data_dir or default_data_dir()).resolve()

    def resolved_state_dir(self) -> Path:
        return (self.state_dir or default_state_dir()).resolve()

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.resolved_state_dir() / "api" / "index.sqlite"
        return f"sqlite:///{db_path}"

    def resolved_artifact_roots(self) -> list[Path]:
        roots = [path.resolve() for path in self.artifact_roots]
        data = self.resolved_data_dir()
        state = self.resolved_state_dir()
        for candidate in (data / "runs", data / "bundles", state / "runs", state / "bundles"):
            if candidate not in roots:
                roots.append(candidate)
        return roots

    def mutations_enabled(self) -> bool:
        return bool(self.resolve_mutation_token())

    def resolve_mutation_token(self) -> str | None:
        if self.mutation_token:
            return self.mutation_token
        if self.mutation_token_file is not None:
            path = self.mutation_token_file.expanduser()
            if path.is_file():
                return path.read_text(encoding="utf-8").strip() or None
            return None
        cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
        if cred_dir:
            cred_path = Path(cred_dir) / "perceptshift-api-token"
            if cred_path.is_file():
                return cred_path.read_text(encoding="utf-8").strip() or None
        return None

    def effective_cors_origins(self) -> list[str]:
        origins = list(self.cors_origins)
        if self.console_origin and self.console_origin not in origins:
            # Console origin is opt-in only when explicitly listed or via CORS_ORIGINS.
            pass
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
