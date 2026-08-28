#!/usr/bin/env bash
# Regenerate every committed JSON plan in docs/evidence/plans, from a clean state, against a
# running moto_server. This is the ONE path: CI runs this script and then fails if the tree
# changed, so a plan in the repository cannot drift away from the configuration it claims to
# describe without somebody noticing.
#
# Usage:  scripts/regenerate_plans.sh [endpoint]      default http://127.0.0.1:5599
#
# The endpoint is a variable rather than a default inside the modules, because a module that
# talks to a real AWS account when a variable is unset is the accident this repository exists
# to refuse. It is therefore also passed here explicitly rather than read from the environment.
set -euo pipefail

ENDPOINT="${1:-http://127.0.0.1:5599}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLANS="$ROOT/docs/evidence/plans"

# module | binary | output file | extra -var arguments
#
# Terraform and OpenTofu both plan modules/storage, and comparing those two files is the whole
# point of src/quiltz/planparity.py. modules/identity is planned by Terraform alone because it
# is consumed by src/quiltz/policies.py as a source of policy documents rather than as a
# parity subject. modules/events is planned by Terraform alone, for its policy documents.
#
# It was excluded at first on the assumption that its archive_file data source rewrites the zip
# on every run and would produce meaningless drift. Measured, that is wrong: archive_file stamps
# a fixed epoch, and two consecutive plans of modules/events differ only in `timestamp` and in
# the order of `relevant_attributes`, which is already handled. Excluding it meant half the
# policy documents in this repository were never linted while a headline claim said they all
# were.
TARGETS=(
  "storage|terraform|terraform.json|-var bucket_name=quiltz-evidence"
  "storage|tofu|opentofu.json|-var bucket_name=quiltz-evidence"
  "identity|terraform|identity-terraform.json|-var bucket_arn=arn:aws:s3:::quiltz-evidence"
  "events|terraform|events-terraform.json|-var endpoint_from_lambda=http://host.docker.internal:5599"
)

if ! curl -fsS --max-time 5 "$ENDPOINT" >/dev/null 2>&1; then
  echo "no emulator answering at $ENDPOINT" >&2
  echo "start one with:  uv run python -m moto.server -p 5599" >&2
  exit 1
fi

for target in "${TARGETS[@]}"; do
  IFS='|' read -r module binary output extra <<<"$target"
  echo "==> $binary plan of modules/$module into $output"
  workdir="$ROOT/modules/$module"
  (
    cd "$workdir"
    # A clean state every time. A plan taken on top of leftover state describes a different
    # question from the one the committed file claims to answer.
    rm -rf .terraform terraform.tfstate terraform.tfstate.backup .plan.bin
    "$binary" init -input=false -no-color >/dev/null
    # shellcheck disable=SC2086
    "$binary" plan -input=false -no-color -out=.plan.bin \
      -var "endpoint=$ENDPOINT" $extra >/dev/null
    "$binary" show -json .plan.bin > "$PLANS/$output"
    rm -f .plan.bin
  )
  python3 -c "
import json, pathlib, sys
path = pathlib.Path('$PLANS/$output')
plan = json.loads(path.read_text())
# Re-serialise so the committed file is stably formatted rather than one long line, which
# makes a diff in a pull request readable instead of a wall.
path.write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n')
if not plan.get('resource_changes'):
    sys.exit('$output has no resource_changes, which means the plan is empty')
"
done

echo "done. ${#TARGETS[@]} plans written to docs/evidence/plans."
