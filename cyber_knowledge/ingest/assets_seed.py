#!/usr/bin/env python3
"""Seed 4 universal Asset reference nodes from data/threats/assets.yaml."""
import sys
from pathlib import Path

import httpx
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class SeedSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


ASSETS_FILE = Path(__file__).parent.parent / "data" / "threats" / "assets.yaml"


def main() -> None:
    cfg = SeedSettings()

    if not ASSETS_FILE.exists():
        print(f"Error: assets file not found: {ASSETS_FILE}", file=sys.stderr)
        sys.exit(1)

    with open(ASSETS_FILE) as f:
        data = yaml.safe_load(f)

    assets = data.get("assets", [])
    print(f"Seeding {len(assets)} asset(s) from {ASSETS_FILE.name}")

    failures = 0
    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:
        for asset in assets:
            r = client.post("/knowledge/assets", json=asset)
            if r.status_code in (200, 201):
                print(f"  [OK] {asset['id']}")
            elif r.status_code == 409:
                print(f"  [EXISTS] {asset['id']}")
            else:
                print(f"  [FAIL] {asset['id']}: {r.status_code} {r.text}", file=sys.stderr)
                failures += 1

    print("\nDone.")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
