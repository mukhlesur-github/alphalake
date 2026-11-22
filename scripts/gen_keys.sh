#!/usr/bin/env bash
# Generate RSA key pairs for the two Snowflake service users. Private keys never leave keys/.
set -euo pipefail
cd "$(dirname "$0")/../keys"
for u in pipeline app; do
  f="svc_alphalake_${u}"
  if [[ -f "$f.p8" ]]; then echo "exists: keys/$f.p8 (skipping)"; continue; fi
  openssl genrsa 2048 2>/dev/null | openssl pkcs8 -topk8 -inform PEM -out "$f.p8" -nocrypt
  openssl rsa -in "$f.p8" -pubout -out "$f.pub" 2>/dev/null
  chmod 600 "$f.p8"
  echo "created: keys/$f.p8 + .pub"
done
