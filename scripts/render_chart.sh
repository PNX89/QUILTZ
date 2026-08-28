#!/usr/bin/env bash
# Regenerate both committed helm artefacts: the golden render and the lint transcript.
#
# Usage:  scripts/render_chart.sh [output-directory]
#
# The output directory is an argument so a test can render into a temporary one and compare,
# rather than writing into the repository and asking git whether anything moved. Asking git
# conflates "the chart changed" with "somebody has uncommitted work", and the second is the
# normal state of a working tree.
#
# The golden render was already compared byte for byte by a helm-marked test. The lint
# transcript was not: nothing produced it, nothing compared it, and the test over it asserted
# two strings that a successful lint of ANY chart prints. It also did not record its own
# invocation, so the file could not support the claim being made about it, which is the same
# defect the Ansible and state lock transcripts each had to be corrected for.
#
# KUBECONFIG is pointed at a file that does not exist, and the transcript says so, because the
# claim is about the absence of a cluster.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART="$ROOT/charts/evidence-collector"
OUT="${1:-$ROOT/docs/evidence/helm}"

command -v helm >/dev/null || { echo "helm is not on PATH" >&2; exit 1; }
mkdir -p "$OUT"

export KUBECONFIG=/nonexistent

KUBECONFIG=/nonexistent helm template quiltz "$CHART" > "$OUT/rendered.golden.yaml"

{
  echo "\$ KUBECONFIG=/nonexistent helm lint $(basename "$(dirname "$CHART")")/$(basename "$CHART")"
  echo "# helm $(helm version --short)"
  echo "# KUBECONFIG names a path that does not exist: $(test -e /nonexistent && echo "IT EXISTS, which invalidates this" || echo "confirmed absent")"
  echo
  KUBECONFIG=/nonexistent helm lint "$CHART" 2>&1 | sed "s#$ROOT/##"
} > "$OUT/lint-with-no-cluster.txt"

echo "written:"
ls -1 "$OUT"
