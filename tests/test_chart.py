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

import json
import pathlib
import shutil
import subprocess
import tempfile
from typing import Any

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
CHART = REPO / "charts" / "evidence-collector"
GOLDEN = REPO / "docs" / "evidence" / "helm" / "rendered.golden.yaml"
LINT = REPO / "docs" / "evidence" / "helm" / "lint-with-no-cluster.txt"


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
    """Offline. `latest` is the version that changes without a commit saying so.

    THE MARKER LIST WAS THE WHOLE GUARD AND IT MISSED THE SHAPE THIS CHART ACTUALLY USES. Every
    value here is piped through `quote`, so an unset one renders as `value: ""`, which contains
    no `<no value>`, no `null` and no `None`. A chart whose bucket was empty passed this test.

    The render is parsed now rather than grepped, and the real defence is
    charts/evidence-collector/values.schema.json, which makes helm itself refuse the empty
    value before anything renders at all.
    """
    text = GOLDEN.read_text(encoding="utf-8")
    assert ":latest" not in text, "an unpinned image tag is a deploy nobody can reproduce"
    for marker in ("<no value>", "null", "None"):
        assert marker not in text, f"the render contains {marker!r}, so a value went unset"

    cronjob = next(o for o in rendered_objects() if o["kind"] == "CronJob")
    container = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    for variable in container["env"]:
        assert variable.get("value"), (
            f"{variable['name']} rendered empty. Piped through quote, an unset value becomes "
            f"an empty string rather than any of the markers above"
        )
    assert container["image"].count(":") == 1 and not container["image"].endswith(":")


def test_the_service_account_the_chart_creates_is_the_one_the_pods_use() -> None:
    """Offline, and it was not true until 28-8-2026.

    The chart rendered a ServiceAccount and the pod spec never named it, so every pod ran under
    the namespace `default` while the chart shipped an identity implying otherwise. A
    ServiceAccount nothing references is worse than none at all: it reads as scoped access that
    was never actually granted, and the reviewer who sees it in the chart has no reason to look
    for the reference that is missing.

    The two names are compared rather than each being checked against a literal, which is what
    would still pass if one of them were renamed.
    """
    objects = rendered_objects()
    account = next(o for o in objects if o["kind"] == "ServiceAccount")
    cronjob = next(o for o in objects if o["kind"] == "CronJob")
    pod = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]

    assert pod.get("serviceAccountName") == account["metadata"]["name"], (
        "the pods do not run under the ServiceAccount this chart creates"
    )
    assert pod.get("automountServiceAccountToken") is False, (
        "the token is mounted into a pod that has no reason to call the API server"
    )


def test_the_chart_carries_a_values_schema_that_rejects_the_dangerous_values() -> None:
    """Offline. The schema is the guard; this checks the guard exists and says what it must.

    Read as data rather than trusted, because a schema file that exists and constrains nothing
    would leave every string check above as the only defence again.
    """
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))
    properties = schema["properties"]
    assert properties["bucket"]["minLength"] == 1
    assert properties["region"]["minLength"] == 1
    assert properties["image"]["properties"]["tag"]["not"] == {"const": "latest"}
    assert schema["additionalProperties"] is False, (
        "a typo in a values key would otherwise be accepted silently and take the default"
    )


def test_the_lint_transcript_shows_it_ran_without_a_cluster() -> None:
    """Offline. The claim is about the absence of a cluster, so the transcript has to show it.

    This test used to assert two strings that a successful lint of ANY chart prints, over a file
    that nothing produced and nothing compared. It could not fail, and it certainly could not
    establish the thing it is named for, since neither string says anything about a cluster.
    """
    transcript = LINT.read_text(encoding="utf-8")
    first = transcript.splitlines()[0]
    assert first.startswith("$ "), f"the transcript does not record its command, it opens {first!r}"
    assert "KUBECONFIG=/nonexistent" in first, (
        "the recorded command does not point KUBECONFIG at nothing, so this transcript cannot "
        "support a claim about linting without a cluster"
    )
    assert "confirmed absent" in transcript, (
        "the transcript does not record that the KUBECONFIG path was actually missing. If a "
        "file appeared at /nonexistent the run would prove the opposite of what is claimed"
    )
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


@pytest.mark.helm
def test_the_lint_transcript_is_what_helm_prints_today() -> None:
    """Needs helm. The transcript, re-derived and compared.

    Without this the file is a claim about the past, exactly as the plans were before anything
    regenerated them. The version line is included in the comparison deliberately: a helm upgrade
    that changes the output should be a decision rather than a silent difference.
    """
    helm = shutil.which("helm")
    assert helm, "the helm marker is selected and helm is not on PATH"
    with tempfile.TemporaryDirectory() as scratch:
        result = subprocess.run(
            ["bash", str(REPO / "scripts" / "render_chart.sh"), scratch],
            capture_output=True,
            text=True,
            env={"PATH": f"{pathlib.Path(helm).parent}:/usr/bin:/bin"},
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        # Compared against a fresh render rather than against git, so this says something about
        # the chart rather than about whether the working tree happens to be clean.
        for committed in (GOLDEN, LINT):
            produced = pathlib.Path(scratch) / committed.name
            assert produced.read_text(encoding="utf-8") == committed.read_text(encoding="utf-8"), (
                f"{committed.name} is not what helm produces now. Regenerate it with "
                f"scripts/render_chart.sh and read the diff before committing it."
            )


@pytest.mark.helm
def test_helm_refuses_an_empty_bucket_and_a_latest_tag() -> None:
    """Needs helm. The schema, enforced by helm rather than asserted about.

    Each rejection separately, so a schema that lost one constraint names which one.
    """
    helm = shutil.which("helm")
    assert helm
    env = {"PATH": str(pathlib.Path(helm).parent), "KUBECONFIG": "/nonexistent"}

    for override, expected in (("bucket=", "/bucket"), ("image.tag=latest", "/image/tag")):
        result = subprocess.run(
            [helm, "template", "quiltz", str(CHART), "--set", override],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        assert result.returncode != 0, f"helm rendered {override!r}, which the schema must refuse"
        assert expected in result.stderr, (
            f"helm refused {override!r} for some other reason: {result.stderr[:300]}"
        )
