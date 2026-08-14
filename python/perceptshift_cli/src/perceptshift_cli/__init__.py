"""PerceptShift CLI package."""

from __future__ import annotations

__all__ = ["app"]


def __getattr__(name: str) -> object:
    if name == "app":
        from perceptshift_cli.app import app

        return app
    raise AttributeError(name)
