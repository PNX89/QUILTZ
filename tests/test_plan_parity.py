"""Two binaries, one configuration, and whether they actually agree.

The matrix is the repository's headline decision and the licence is the reason for it, so the
matrix has to do more than run twice. These plans were captured on 28-8-2026 from Terraform
1.16.0 and OpenTofu 1.12.6 against the same module and the same emulator, and are committed so
this runs offline. The `emulator` job regenerates them and fails if they have drifted.
"""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any

from quiltz.planparity import TOOL_METADATA_LEAVES, compare

PLANS = pathlib.Path(__file__).resolve().parents[1] / "docs" / "evidence" / "plans"


def plans() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        json.loads((PLANS / "terraform.json").read_text()),
        json.loads((PLANS / "opentofu.json").read_text()),
    )


def test_the_two_binaries_disagree_about_nothing_that_would_be_built() -> None:
    """The claim. Thirteen leaves differ and every one of them is about the tools."""
    terraform, opentofu = plans()
    differences = compare(terraform, opentofu)
    real = [d for d in differences if not d.is_tool_metadata]

    assert real == [], "\n".join(f"{d.path}: {d.detail}" for d in real)
    assert len(differences) == 13, (
        f"expected the thirteen tool-metadata leaves measured on 28-8-2026, found "
        f"{len(differences)}. A new one is either a real disagreement or an exemption that "
        f"needs adding deliberately, and both should be looked at rather than absorbed."
    )


def test_what_would_be_created_is_identical() -> None:
    """Said directly rather than inferred from the absence of differences."""
    terraform, opentofu = plans()
    for left, right in zip(
        terraform["resource_changes"], opentofu["resource_changes"], strict=True
    ):
        assert left["address"] == right["address"]
        assert left["type"] == right["type"]
        assert left["change"]["actions"] == right["change"]["actions"]
        assert left["change"]["after"] == right["change"]["after"]
    assert len(terraform["resource_changes"]) == 2


def test_the_comparison_catches_a_real_disagreement() -> None:
    """Adversarially. A comparison that forgave everything would pass every test above.

    The injected change is the one that matters: a bucket name. If the two binaries ever
    planned different infrastructure, this is the shape it would take.
    """
    terraform, opentofu = plans()
    tampered = copy.deepcopy(opentofu)
    tampered["resource_changes"][0]["change"]["after"]["bucket"] = "somebody-elses-bucket"

    real = [d for d in compare(terraform, tampered) if not d.is_tool_metadata]
    assert real, "a changed bucket name was forgiven, so the comparison proves nothing"
    assert any("bucket" in d.path for d in real)


def test_no_exemption_is_stale() -> None:
    """An exemption that no longer applies is a hole nobody is watching.

    Every entry in the allowlist has to be doing work against these plans. When a version bump
    stops emitting one of them, the entry should be removed rather than left as a standing
    permission for that leaf to differ.
    """
    terraform, opentofu = plans()
    exercised = {d.leaf for d in compare(terraform, opentofu) if d.is_tool_metadata}
    stale = sorted(set(TOOL_METADATA_LEAVES) - exercised)
    assert stale == [], (
        f"these exemptions forgive nothing in the current plans and should go: {stale}"
    )


def test_every_exemption_says_why_it_is_there() -> None:
    """An unexplained exemption is how an allowlist turns into a way of passing."""
    for leaf, reason in TOOL_METADATA_LEAVES.items():
        assert len(reason) > 20, f"{leaf} is exempt without a stated reason"
