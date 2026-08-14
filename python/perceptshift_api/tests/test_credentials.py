"""Mutation token resolution, including systemd credentials."""

from __future__ import annotations

from pathlib import Path

from perceptshift_api.config import Settings


def test_env_token_wins_over_file_and_credentials(tmp_path: Path, monkeypatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("from-file\n", encoding="utf-8")
    cred_dir = tmp_path / "creds"
    cred_dir.mkdir()
    (cred_dir / "perceptshift-api-token").write_text("from-creds\n", encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    settings = Settings(mutation_token="from-env", mutation_token_file=token_file)
    assert settings.resolve_mutation_token() == "from-env"


def test_token_file_wins_over_credentials(tmp_path: Path, monkeypatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("from-file\n", encoding="utf-8")
    cred_dir = tmp_path / "creds"
    cred_dir.mkdir()
    (cred_dir / "perceptshift-api-token").write_text("from-creds\n", encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    settings = Settings(mutation_token=None, mutation_token_file=token_file)
    assert settings.resolve_mutation_token() == "from-file"


def test_credentials_directory_token(tmp_path: Path, monkeypatch) -> None:
    cred_dir = tmp_path / "creds"
    cred_dir.mkdir()
    (cred_dir / "perceptshift-api-token").write_text("systemd-secret\n", encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    settings = Settings(mutation_token=None, mutation_token_file=None)
    assert settings.resolve_mutation_token() == "systemd-secret"


def test_missing_credentials_directory_yields_none(monkeypatch) -> None:
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    settings = Settings(mutation_token=None, mutation_token_file=None)
    assert settings.resolve_mutation_token() is None
