#!/usr/bin/env python3
"""Create a local .env from .env.example with freshly generated random secrets.

Usage:  python scripts/init_env.py [--force]

Secrets are generated with the `secrets` module and written only to .env
(which is git-ignored). Nothing is printed except the variable names.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = {
    "COMMAND_HMAC_KEY": lambda: secrets.token_hex(32),
    "OPERATOR_TOKEN": lambda: secrets.token_urlsafe(24),
    "ADMIN_TOKEN": lambda: secrets.token_urlsafe(24),
    "POSTGRES_PASSWORD": lambda: secrets.token_urlsafe(18),
    "MINIO_ROOT_PASSWORD": lambda: secrets.token_urlsafe(18),
    "MQTT_PASSWORD": lambda: secrets.token_urlsafe(18),
}


def main() -> int:
    env = ROOT / ".env"
    if env.exists() and "--force" not in sys.argv:
        print(".env already exists - use --force to regenerate (this rotates all secrets)")
        return 1
    lines = []
    for line in (ROOT / ".env.example").read_text().splitlines():
        key = line.split("=", 1)[0].strip()
        if key in GENERATED and line.strip().endswith("="):
            line = f"{key}={GENERATED[key]()}"
        lines.append(line)
    env.write_text("\n".join(lines) + "\n")
    env.chmod(0o600)
    print(f"wrote {env.relative_to(ROOT)} with generated: {', '.join(GENERATED)}")
    print("Your operator/admin tokens are in .env (OPERATOR_TOKEN / ADMIN_TOKEN).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
