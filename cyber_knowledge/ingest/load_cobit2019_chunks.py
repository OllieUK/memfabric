#!/usr/bin/env python3
"""load_cobit2019_chunks.py — Load reviewed COBIT 2019 YAML into the knowledge graph.

Reads the reviewed YAML produced by inspect_cobit2019.py and:
  1. Creates/upserts all Framework hierarchy nodes with statement_type classification

Cross-reference edges (INFORMS) are deferred to WP-105.

Usage:
    python3 -m scripts.load_cobit2019_chunks \
        [--yaml scripts/cobit2019_inspection.yaml] \
        [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter

import httpx
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoadSettings(BaseSettings):
    api_base_url: str = 'http://localhost:8000'
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


# Map YAML type → graph level
_LEVEL_MAP: dict[str, str] = {
    'framework': 'framework',
    'domain':    'domain',
    'objective': 'objective',
    'practice':  'practice',
    'activity':  'activity',
}

# Map YAML type → statement_type
_STATEMENT_TYPE_MAP: dict[str, str] = {
    'framework': 'structural',
    'domain':    'structural',
    'objective': 'informative',
    'practice':  'informative',
    'activity':  'informative',
}


def _post(client: httpx.Client, endpoint: str, body: dict, label: str) -> str:
    try:
        r = client.post(endpoint, json=body)
        if r.status_code == 409:
            return 'exists'
        r.raise_for_status()
        return 'ok'
    except httpx.HTTPStatusError as exc:
        print(
            f'  [ERR] {label}: HTTP {exc.response.status_code} — {exc.response.text[:200]}',
            file=sys.stderr,
        )
        return 'error'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--yaml', default='scripts/cobit2019_inspection.yaml')
    parser.add_argument('--dry-run', action='store_true', help='Parse and validate only — no API calls')
    args = parser.parse_args()

    cfg = LoadSettings()

    # --- Load YAML ---
    with open(args.yaml, encoding='utf-8') as f:
        entries: list[dict] = yaml.safe_load(f)

    type_counts = Counter(e['type'] for e in entries)
    print(f'Loaded {len(entries)} entries from {args.yaml}')
    print(
        f"  framework: {type_counts['framework']}, "
        f"domain: {type_counts['domain']}, "
        f"objective: {type_counts['objective']}, "
        f"practice: {type_counts['practice']}, "
        f"activity: {type_counts['activity']}"
    )

    if args.dry_run:
        print('\nDry run — no changes made.')
        return

    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:

        # 2. Framework hierarchy
        print(f'\n2. Framework hierarchy ({len(entries)} entries)')

        ok = err = 0
        PREVIEW = 3

        for i, e in enumerate(entries):
            fw_id: str = e['id']
            entry_type: str = e['type']
            level = _LEVEL_MAP.get(entry_type, 'informative')
            statement_type = _STATEMENT_TYPE_MAP.get(entry_type, 'informative')
            text: str | None = e.get('text') or None
            heading: str = e.get('heading') or fw_id
            parent_id: str | None = e.get('parent_id') or None

            payload: dict = {
                'id': fw_id,
                'title': heading,
                'level': level,
                'statement_type': statement_type,
            }
            if text:
                payload['body'] = text
            if parent_id:
                payload['parent_id'] = parent_id

            status = _post(client, '/knowledge/frameworks', payload, fw_id)

            if status == 'error':
                err += 1
            else:
                ok += 1

            if i < PREVIEW:
                print(f'   {fw_id}: {status}')
            elif i == PREVIEW:
                print('   ...')

        print(f'   Summary: {ok} ok, {err} errors')

    print('\nDone.')


if __name__ == '__main__':
    main()
