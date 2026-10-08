#!/usr/bin/env bash
set -euo pipefail
# Decrypt .env.enc to stdout using SECRETS_KEY
# Usage: ./scripts/decrypt-env.sh [input_file]
# Requires: SECRETS_KEY env var (fallback: SECRETS_KEY no .env do usuario)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
USER_ENV="$HOME/.config/huawei-manager/.env"

INPUT="${1:-$PROJECT_ROOT/.env.enc}"
KEY="${SECRETS_KEY:-}"

if [ -z "$KEY" ]; then
  if [ -f "$USER_ENV" ]; then
    KEY=$(grep -E '^SECRETS_KEY=' "$USER_ENV" | cut -d= -f2-)
  fi
fi

if [ -z "$KEY" ]; then
  echo "ERROR: SECRETS_KEY not set. Provide via env var or in .env" >&2
  exit 1
fi

if [ ! -f "$INPUT" ]; then
  echo "ERROR: Encrypted file not found: $INPUT" >&2
  exit 1
fi

cd "$PROJECT_ROOT"
export SECRETS_KEY="$KEY"
python3 -c "
import json, os
from huawei_manager.vault import CryptoEnvBackend
key = os.environ['SECRETS_KEY']
backend = CryptoEnvBackend(encryption_key=key)
store = json.loads(open('$INPUT').read())
for k in sorted(store.keys()):
    v = backend.get(k)
    print(f'{k}={v}')
"
