"""CLI entrypoint for the local operational API."""

from __future__ import annotations

import argparse

import uvicorn

from perceptshift_api.config import get_settings


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="PerceptShift local operational API")
    parser.add_argument("--host", default=settings.host, help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=settings.port, help="Bind port")
    args = parser.parse_args()

    uvicorn.run(
        "perceptshift_api.app:app",
        host=args.host,
        port=args.port,
        factory=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
