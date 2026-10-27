#!/bin/bash
# runner/ci/bin/seal.sh: symmetric sealing for private material that must travel through GitHub (the staged pool as a
# release asset of the organiser-only ops store; the per-game bundles and full results of every scoring run).
# OpenSSL only (preinstalled on GitHub-hosted runners and Ubuntu): AES-256-CTR, PBKDF2-SHA256 (600k iterations),
# plus an HMAC-SHA256 over the ciphertext with a key derived from the same passphrase, checked before decryption.
#
#   seal.sh seal  IN  OUT.enc  PASSFILE
#   seal.sh open  IN.enc OUT   PASSFILE
#   seal.sh newkey PASSFILE              # 32 random bytes, base64, mode 600
# The passphrase lives only in the organiser's password manager and in GitHub environment secrets
# (DFBENCH_SEAL_KEY). Integrity of the pool is also pinned by POOL.json's public sha256.
set -euo pipefail
cmd=${1:-}; in=${2:-}; out=${3:-}; pf=${4:-}
ITER=600000
hex() { od -An -vtx1 | tr -d ' \n'; }
mac_key() { printf '%s' "dfbench-seal-mac:$(cat "$pf")" | openssl dgst -sha256 -binary | hex; }
case "$cmd" in
  newkey)
    umask 077; openssl rand -base64 32 > "$in"; echo "wrote $in" ;;
  seal)
    [ -s "$pf" ] || { echo "passphrase file $pf missing" >&2; exit 2; }
    umask 077
    openssl enc -aes-256-ctr -salt -pbkdf2 -md sha256 -iter $ITER -pass file:"$pf" -in "$in" -out "$out.body"
    openssl dgst -sha256 -mac HMAC -macopt hexkey:"$(mac_key)" -binary "$out.body" > "$out.mac"
    { printf 'DFBSEAL1'; cat "$out.mac" "$out.body"; } > "$out"
    rm -f "$out.body" "$out.mac"
    echo "sealed $(wc -c < "$out" | tr -d ' ') bytes" ;;
  open)
    [ -s "$pf" ] || { echo "passphrase file $pf missing" >&2; exit 2; }
    umask 077
    [ "$(head -c 8 "$in")" = DFBSEAL1 ] || { echo "not a DFBSEAL1 file" >&2; exit 1; }
    head -c 40 "$in" | tail -c 32 > "$out.mac"   # not tail | head: under pipefail, head closing early SIGPIPEs tail on big files
    tail -c +41 "$in" > "$out.body"
    calc=$(openssl dgst -sha256 -mac HMAC -macopt hexkey:"$(mac_key)" -binary "$out.body" | hex)
    want=$(hex < "$out.mac")
    [ "$calc" = "$want" ] || { rm -f "$out.mac" "$out.body"; echo "seal MAC mismatch (wrong key or tampered)" >&2; exit 1; }
    openssl enc -d -aes-256-ctr -pbkdf2 -md sha256 -iter $ITER -pass file:"$pf" -in "$out.body" -out "$out"
    rm -f "$out.mac" "$out.body" ;;
  *) sed -n '2,12p' "$0"; exit 2 ;;
esac
