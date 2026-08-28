#!/usr/bin/env bash
# Fetch the Ansible collection this repository invokes but does not vendor.
#
# WHY IT IS FETCHED RATHER THAN COMMITTED. amazon.aws ships under GPL-3.0-or-later and this
# repository is MIT, so committing its source into the tree would put GPL source inside an MIT
# package. Ansible is used here as a command rather than a library for the same reason: nothing
# GPL is imported, distributed or derived from. check_repo.sh G13 fails on any vendored
# dependency in a tree, and collections/ is in .gitignore so that stays true.
#
# The version is pinned. An unpinned collection makes every idempotence transcript in
# docs/evidence/ansible a claim about whatever was on the shelf that morning.
set -euo pipefail

COLLECTION_VERSION="11.4.0"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v ansible-galaxy >/dev/null 2>&1; then
  echo "ansible-galaxy is not on PATH. Run this through the project environment:" >&2
  echo "  uv run scripts/fetch_tools.sh" >&2
  exit 1
fi

ansible-galaxy collection install \
  "amazon.aws:==${COLLECTION_VERSION}" \
  --collections-path "$ROOT/collections" \
  --force

installed="$ROOT/collections/ansible_collections/amazon/aws/MANIFEST.json"
python3 - "$installed" "$COLLECTION_VERSION" <<'PY'
import json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
found = manifest["collection_info"]["version"]
if found != sys.argv[2]:
    sys.exit(f"asked for {sys.argv[2]} and got {found}")
print(f"amazon.aws {found} in place")
PY
