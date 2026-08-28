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

from quiltz.planparity import ORDER_INSENSITIVE, TOOL_METADATA_PATHS, compare

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
    paths = [d.path for d in compare(terraform, opentofu)]
    stale = sorted(e.leaf for e in TOOL_METADATA_PATHS if not any(e.covers(p) for p in paths))
    assert stale == [], (
        f"these exemptions forgive nothing in the current plans and should go: {stale}"
    )


def test_every_exemption_says_why_it_is_there() -> None:
    """An unexplained exemption is how an allowlist turns into a way of passing."""
    for exemption in TOOL_METADATA_PATHS:
        assert len(exemption.reason) > 20, f"{exemption.leaf} is exempt without a stated reason"


def test_a_changed_resource_type_is_not_forgiven() -> None:
    """The regression test for the hole this allowlist had until 28-8-2026.

    The exemptions were leaf names matched anywhere in the path. `type` is on the list to admit
    the variable metadata OpenTofu emits, and as a bare name it also admitted
    `.resource_changes[0].type`, which is the kind of resource the plan would create. Rewriting
    one plan's bucket into a DynamoDB table produced sixteen differences and not one of them was
    counted as real, while the module's first sentence promised that anything outside the
    allowlist fails.

    The count assertion in the first test would have caught this particular mutation, sixteen
    against thirteen, but it would have reported it as an unexpected number of differences
    rather than as two tools planning different infrastructure. That is a diagnostic pointing
    away from the problem, and it only holds while the arithmetic happens to disagree.
    """
    terraform, opentofu = plans()
    tampered = copy.deepcopy(opentofu)
    for where in (
        tampered["resource_changes"][0],
        tampered["planned_values"]["root_module"]["resources"][0],
        tampered["configuration"]["root_module"]["resources"][0],
    ):
        where["type"] = "aws_dynamodb_table"

    real = [d for d in compare(terraform, tampered) if not d.is_tool_metadata]
    assert real, "a changed resource type was forgiven, which is the hole this test exists for"
    assert any(d.path.startswith(".resource_changes") and d.leaf == "type" for d in real), (
        f"the resource type change was not among the differences counted: {[d.path for d in real]}"
    )


def test_no_exemption_travels_beyond_where_it_was_measured() -> None:
    """Each pattern is anchored, so an exemption cannot follow its leaf name elsewhere.

    Tested per entry rather than in aggregate: an exemption that quietly matched everything
    would still let the suite above pass, because everything it forgave would simply never be
    counted.
    """
    elsewhere = (
        ".resource_changes[0].type",
        ".planned_values.root_module.resources[0].type",
        ".configuration.root_module.resources[0].type",
        ".resource_changes[0].change.after.required",
        ".prior_state.values.root_module.resources[0].values.complete",
        ".configuration.root_module.resources[0].provider_name.applyable",
    )
    for exemption in TOOL_METADATA_PATHS:
        for path in elsewhere:
            assert not exemption.covers(path), (
                f"exemption {exemption.leaf} forgives {path}, which is not where it was measured"
            )


def test_a_reordered_list_is_not_a_disagreement() -> None:
    """CI found this before a person did, which is the argument for regenerating in CI at all.

    The identity plan regenerated on a Linux runner carried the same four relevant_attributes as
    the one committed from macOS, with two of them swapped, and the positional walk read that as
    four disagreements about infrastructure.

    The reordering reproduced here is the exact one CI hit.
    """
    plan = json.loads((PLANS / "identity-terraform.json").read_text())
    swapped = copy.deepcopy(plan)
    entries = swapped["relevant_attributes"]
    entries[1], entries[2] = entries[2], entries[1]
    assert entries != plan["relevant_attributes"], "the swap did not change anything"

    assert compare(plan, swapped) == [], "a pure reordering is being read as a disagreement"


def test_sorting_that_list_does_not_stop_it_being_compared() -> None:
    """The failure mode of the easy fix, tested directly.

    Exempting relevant_attributes would also have passed this test's mutations, which is why it
    was rejected: it would have stopped the check noticing that the set of attributes changed at
    all. Sorting gives up the sequence and keeps every element under comparison.

    Each mutation is asserted separately. A single assertion over all three would pass while two
    of them silently did nothing.
    """
    plan = json.loads((PLANS / "identity-terraform.json").read_text())

    changed = copy.deepcopy(plan)
    changed["relevant_attributes"][0]["attribute"] = ["something_else"]
    assert compare(plan, changed), "a changed attribute was forgiven"

    removed = copy.deepcopy(plan)
    removed["relevant_attributes"].pop()
    assert compare(plan, removed), "a removed entry was forgiven"

    added = copy.deepcopy(plan)
    added["relevant_attributes"].append({"attribute": ["id"], "resource": "aws_iam_role.other"})
    assert compare(plan, added), "an added entry was forgiven"


def test_every_order_insensitive_path_says_why() -> None:
    """One entry today. It is a dict rather than a bare tuple so it cannot grow silently."""
    assert ORDER_INSENSITIVE, "the mechanism exists with nothing declared, which is a dead branch"
    for path, reason in ORDER_INSENSITIVE.items():
        assert path.startswith("."), path
        assert len(reason) > 40, f"{path} is sorted without a stated reason"


def test_canonical_leaves_an_ordered_list_alone() -> None:
    """Only the declared paths are sorted, so resource_changes order is still compared.

    Without this, widening ORDER_INSENSITIVE to everything would pass every other test here.
    """
    plan = json.loads((PLANS / "terraform.json").read_text())
    reordered = copy.deepcopy(plan)
    reordered["resource_changes"].reverse()
    assert compare(plan, reordered), (
        "reversing resource_changes was forgiven, so sorting is no longer confined to the "
        "paths that declared it"
    )
