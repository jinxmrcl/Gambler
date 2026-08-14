#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETS_DIR="$WORKDIR/secrets"

mkdir -p "$SECRETS_DIR"

gen_if_missing() {
  local file="$1"
  if [[ ! -s "$file" ]]; then
    openssl rand -base64 24 > "$file"
    chmod 600 "$file"
    echo "Generated $file"
  else
    echo "$file already exists, leaving it as-is"
  fi
}

gen_if_missing "$SECRETS_DIR/mysql_root_password.txt"
gen_if_missing "$SECRETS_DIR/db_password.txt"

echo
echo "Done. Point .env's DB_PASSWORD_FILE at:"
echo "  $SECRETS_DIR/db_password.txt"
