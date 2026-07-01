#!/usr/bin/env bash
set -euo pipefail
# Encrypt .env to .env.enc using SECRETS_KEY
# Usage: ./scripts/encrypt-env.sh [input_file] [output_file]
# Requires: SECRETS_KEY env var or .env with SECRETS_KEY set

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

INPUT="${1:-$PROJECT_ROOT/.env}"
OUTPUT="${2:-$PROJECT_ROOT/.env.enc}"
KEY="${SECRETS_KEY:-}"

if [ -z "$KEY" ]; then
  if [ -f "$PROJECT_ROOT/.env" ]; then
    KEY=$(grep -E '^SECRETS_KEY=' "$PROJECT_ROOT/.env" | cut -d= -f2-)
  fi
fi

if [ -z "$KEY" ]; then
  echo "ERROR: SECRETS_KEY not set. Provide via env var or in .env" >&2
  exit 1
fi

if [ ! -f "$INPUT" ]; then
  echo "ERROR: Input file not found: $INPUT" >&2
  exit 1
fi

cd "$PROJECT_ROOT"
export SECRETS_KEY="$KEY"
python3 -c "
import json, os, sys
from huawei_manager.vault import CryptoEnvBackend
key = os.environ['SECRETS_KEY']
backend = CryptoEnvBackend(encryption_key=key, storage_path='$OUTPUT')
with open('$INPUT') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        k, _, v = line.partition('=')
        k = k.strip()
        v = v.strip().strip(\"'\").strip('\"')
        if k and v:
            backend.put(k, v)
print(f'Encrypted {len(backend._store)} keys to $OUTPUT')
"
