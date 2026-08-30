#!/usr/bin/env bash
# Apply twice under one binary and require the second to change nothing.
#
# Usage:  scripts/prove_convergence.sh <terraform|tofu> <endpoint> <bucket>
#
# WHY. boundary.PROVED says the configuration "parses, plans and converges, under two independent
# binaries". Until 28-8-2026 nothing established either half of that. OpenTofu planned and never
# applied anything anywhere in the repository, so the second binary was only ever half tested;
# and no test asserted that a repeat apply is a no-op under either of them, so "converges" was
# a word rather than a measurement.
#
# Convergence is the claim that matters for infrastructure code. An apply that succeeds tells you
# it ran. An apply that succeeds and then reports nothing to do tells you the configuration
# describes a fixed point, which is the property that makes it safe to run again.
set -euo pipefail

BINARY="${1:?terraform or tofu}"
ENDPOINT="${2:?the emulator endpoint}"
BUCKET="${3:?a bucket name unique to this binary}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/modules/storage"
OUT="$ROOT/docs/evidence/convergence"

command -v "$BINARY" >/dev/null || { echo "$BINARY is not on PATH" >&2; exit 1; }
mkdir -p "$OUT"

# Its own state file, so the two binaries do not fight over one and so this proves convergence
# rather than proving that the second binary found the first one's work already done.
STATE="$ROOT/.convergence-$BINARY.tfstate"
rm -f "$STATE"

cd "$WORK"
"$BINARY" init -input=false -no-color -reconfigure >/dev/null

run() {
  "$BINARY" apply -auto-approve -no-color \
    -state="$STATE" -var "endpoint=$ENDPOINT" -var "bucket_name=$BUCKET" 2>&1
}

FIRST="$(run)"
SECOND="$(run)"

first_line="$(printf '%s' "$FIRST" | grep -E '^Apply complete!' || true)"
second_line="$(printf '%s' "$SECOND" | grep -E '^Apply complete!' || true)"

{
  echo "\$ $BINARY apply -auto-approve -no-color -state=\"$STATE\" -var endpoint=$ENDPOINT -var bucket_name=$BUCKET"
  echo "\$ $BINARY apply -auto-approve -no-color -state=\"$STATE\" -var endpoint=$ENDPOINT -var bucket_name=$BUCKET"
  echo "# the same command twice. The second one is the claim."
  echo
  echo "$BINARY version: $("$BINARY" version -json | python3 -c 'import json,sys;print(json.load(sys.stdin)["terraform_version"])')"
  echo
  echo "first  run: $first_line"
  echo "second run: $second_line"
} > "$OUT/$BINARY.txt"

if [ -z "$first_line" ]; then
  echo "the first apply did not complete under $BINARY" >&2
  printf '%s\n' "$FIRST" >&2
  exit 1
fi
if ! printf '%s' "$first_line" | grep -qE '[1-9][0-9]* added'; then
  echo "the first apply under $BINARY added nothing, so the second changing nothing proves nothing" >&2
  echo "  $first_line" >&2
  exit 1
fi
if ! printf '%s' "$second_line" | grep -q '0 added, 0 changed, 0 destroyed'; then
  echo "the second apply under $BINARY was not a no-op, so the configuration does not converge" >&2
  echo "  $second_line" >&2
  exit 1
fi

rm -f "$STATE" "$STATE.backup"
echo "$BINARY converges: $second_line"
