"""Mint a demo analystAuth JWT.

Usage (from the repo root):

    PYTHONPATH=services/api python -m app.mint_token --sub analyst-demo

The token is HS256, signed with JWT_SECRET, and carries iss/aud/exp/sub.
It prints the token only. DEV_JWT in .env.example is not accepted as a credential.
"""

from __future__ import annotations

import argparse

from app.auth import mint_analyst_token
from app.settings import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mint a demo analystAuth JWT (HS256).")
    parser.add_argument("--sub", default="analyst-demo", help="Analyst id stored in sub")
    parser.add_argument("--name", default=None, help="Optional display name")
    parser.add_argument("--ttl-seconds", type=int, default=86400)
    args = parser.parse_args(argv)
    token = mint_analyst_token(
        load_settings(),
        args.sub,
        display_name=args.name,
        ttl_seconds=args.ttl_seconds,
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
