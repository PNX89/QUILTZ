"""A chart that is right before it meets a cluster, and no cluster is ever met.

The interviewer question this answers is "can you write a Helm chart, and how do you know it is
correct before it touches anything". The honest answer has two halves and the second is the one
that matters: `helm lint` and `helm template` both run with `KUBECONFIG` pointed at a file that
does not exist, so nothing here can have quietly talked to a cluster and passed for that reason.

The offline half of this file reads the committed render, so it checks something real on a
machine with no helm at all. The `helm` marked half re-renders and compares byte for byte, and
runs in its own job where the binary is fetched.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
from typing import Any

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
CHART = REPO / "charts" / "evidence-collector"
GOLDEN = REPO / "docs" / "evidence" / "helm" / "rendered.golden.yaml"


def rendered_objects() -> list[dict[str, Any]]:
    docs = list(yaml.safe_load_all(GOLDEN.read_text(encoding="utf-8")))
    return [dict(d) for d in docs if d]


def test_the_committed_render_is_two_objects_of_the_kinds_the_chart_declares() -> None:
    """Offline. A golden file nobody parses is a golden file that can rot into anything."""
    objects = rendered_objects()
    assert [o["kind"] for o in objects] == ["ServiceAccount", "CronJob"]
    assert len(objects) == 2


def test_the_cronjob_forbids_concurrent_runs() -> None:
    """Offline, and the one property worth asserting about this particular job.

    It collects evidence into a bucket. Two of them running at once is the failure that would
    not announce itself, which is what this whole toolset is about.
    """
    cronjob = next(o for o in rendered_objects() if o["kind"] == "CronJob")
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    assert cronjob["spec"]["jobTemplate"]["spec"]["backoffLimit"] == 2


def test_nothing_in_the_render_carries_a_latest_tag_or_an_unset_value() -> None:
    """Offline. `latest` is the version that changes without a commit saying so."""
    text = GOLDEN.read_text(encoding="utf-8")
    assert ":latest" not in text, "an unpinned image tag is a deploy nobody can reproduce"
    for marker in ("<no value>", "null", "None"):
        assert marker not in text, f"the render contains {marker!r}, so a value went unset"


def test_the_lint_transcript_shows_it_ran_without_a_cluster() -> None:
    """Offline. The claim is about the absence of a cluster, so the transcript has to show it."""
    transcript = (REPO / "docs" / "evidence" / "helm" / "lint-with-no-cluster.txt").read_text()
    assert "0 chart(s) failed" in transcript
    assert "1 chart(s) linted" in transcript


@pytest.mark.helm
def test_the_chart_still_renders_exactly_what_is_committed() -> None:
    """Needs helm. The golden file, compared byte for byte against a fresh render."""
    helm = shutil.which("helm")
    assert helm, "the helm marker is selected and helm is not on PATH"
    result = subprocess.run(
        [helm, "template", "quiltz", str(CHART)],
        capture_output=True,
        text=True,
        env={"PATH": str(pathlib.Path(helm).parent), "KUBECONFIG": "/nonexistent"},
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == GOLDEN.read_text(encoding="utf-8"), (
        "the chart no longer renders what is committed. Regenerate the golden file "
        "deliberately rather than editing it, and read the diff first."
    )


@pytest.mark.helm
def test_helm_lint_passes_with_no_cluster_reachable() -> None:
    """Needs helm. KUBECONFIG points at nothing, so a cluster cannot be the reason it passed."""
    helm = shutil.which("helm")
    assert helm
    result = subprocess.run(
        [helm, "lint", str(CHART)],
        capture_output=True,
        text=True,
        env={"PATH": str(pathlib.Path(helm).parent), "KUBECONFIG": "/nonexistent"},
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 chart(s) failed" in result.stdout
