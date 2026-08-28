"""Every policy these modules create is checked, and by the right standard for its kind.

The emulator accepts a policy whether it is valid, over-broad or meaningless. That is the first
entry in `boundary.NOT_REPRODUCED` and it is the reason this file exists: if the only check on a
policy is that moto accepted it, nothing has been checked.

The documents come from a committed Terraform plan, so they are the exact JSON the modules would
send. Linting hand-written examples would pass forever while the modules drifted.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from quiltz.policies import ATTRIBUTE_KINDS, Document, Kind, documents_in_plan, lint

PLAN = (
    pathlib.Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "plans"
    / "identity-terraform.json"
)


def plan() -> dict[str, Any]:
    return dict(json.loads(PLAN.read_text()))


def test_the_modules_produce_the_two_documents_this_suite_expects() -> None:
    """If a module gains a policy, this fails until somebody looks at it."""
    documents = documents_in_plan(plan())
    assert {d.origin for d in documents} == {
        "aws_iam_policy.read_one_bucket.policy",
        "aws_iam_role.reader.assume_role_policy",
    }
    assert {d.kind for d in documents} == {Kind.IDENTITY, Kind.TRUST}


def test_every_policy_the_modules_create_is_clean() -> None:
    """The claim, over the real plan rather than over a fixture."""
    offending = [f for document in documents_in_plan(plan()) for f in lint(document)]
    assert offending == [], "\n".join(f"{f.origin}: {f.issue} {f.detail}" for f in offending)


def test_an_over_broad_identity_policy_is_caught() -> None:
    """Adversarially. A linter that passed everything would satisfy the test above."""
    document = Document(
        address="aws_iam_policy.careless",
        attribute="policy",
        body={
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}],
        },
    )
    issues = {f.issue for f in lint(document)}
    assert "RESOURCE_STAR" in issues, f"an s3:* on * was passed as clean: {issues}"


def test_widening_the_real_module_policy_is_caught() -> None:
    """The same thing done to the actual document, which is the drift that would happen."""
    tampered = plan()
    for change in tampered["resource_changes"]:
        after = change["change"].get("after") or {}
        if after.get("policy"):
            body = json.loads(after["policy"])
            body["Statement"][0]["Resource"] = "*"
            after["policy"] = json.dumps(body)
    offending = [f for d in documents_in_plan(tampered) for f in lint(d)]
    assert offending, "widening the module's own policy to * was reported as clean"


@pytest.mark.parametrize(
    ("label", "statement", "expected"),
    [
        (
            "any account may assume it",
            {"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": "*"},
            "TRUST_PRINCIPAL_STAR",
        ),
        (
            "a wildcard inside the principal map",
            {"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {"AWS": "*"}},
            "TRUST_PRINCIPAL_STAR",
        ),
        (
            "nobody at all",
            {"Effect": "Allow", "Action": "sts:AssumeRole"},
            "TRUST_NO_PRINCIPAL",
        ),
        (
            "something other than assuming the role",
            {
                "Effect": "Allow",
                "Action": ["sts:AssumeRole", "s3:GetObject"],
                "Principal": {"Service": "lambda.amazonaws.com"},
            },
            "TRUST_UNEXPECTED_ACTION",
        ),
        (
            "a Deny this checker does not reason about",
            {
                "Effect": "Deny",
                "Action": "sts:AssumeRole",
                "Principal": {"Service": "lambda.amazonaws.com"},
            },
            "TRUST_NOT_ALLOW",
        ),
    ],
)
def test_the_trust_checks_parliament_cannot_make(
    label: str, statement: dict[str, Any], expected: str
) -> None:
    """parliament reads every document as an identity policy, so these are ours to make.

    Handed a valid trust policy it answers MALFORMED, "Statement contains neither Resource nor
    NotResource", which is right for an identity policy and wrong here: the resource is the role
    the document is attached to. Skipping trust policies instead would have made the claim that
    every policy is checked false for half of them.
    """
    document = Document(
        address="aws_iam_role.careless",
        attribute="assume_role_policy",
        body={"Version": "2012-10-17", "Statement": [statement]},
    )
    issues = {f.issue for f in lint(document)}
    assert expected in issues, f"{label} was not caught: {issues}"


def test_parliament_really_does_reject_a_valid_trust_policy() -> None:
    """The reason the split exists, asserted against parliament rather than described.

    If a future version of parliament learns about resource policies, this fails and the design
    should be revisited rather than left carrying a hand-rolled checker it no longer needs.
    """
    import parliament

    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Principal": {"Service": "lambda.amazonaws.com"},
            }
        ],
    }
    analysed = parliament.analyze_policy_string(json.dumps(trust))
    issues = {str(f.issue) for f in analysed.findings}
    assert "MALFORMED" in issues, (
        "parliament now accepts a trust policy, so the purpose-built trust checker may be "
        "redundant and the design decision should be re-read"
    )


def test_a_policy_attribute_that_is_not_json_raises_rather_than_passing() -> None:
    """A document the checker cannot read is not a document that passed."""
    broken = plan()
    broken["resource_changes"][0]["change"]["after"]["policy"] = "{not json at all"
    with pytest.raises(ValueError, match="not parseable JSON"):
        documents_in_plan(broken)


def test_an_unrecognised_document_kind_raises() -> None:
    """The exhaustive match is reachable and does work.

    A catch-all would return an empty finding list for a document nobody examined, and an empty
    finding list reads on a report as clean.
    """
    document = Document(address="aws_iam_role.odd", attribute="policy", body={})
    object.__setattr__(document, "attribute", "some_future_policy_attribute")
    ATTRIBUTE_KINDS["some_future_policy_attribute"] = "not-a-kind"  # type: ignore[assignment]
    try:
        with pytest.raises(AssertionError, match="not handled by this match"):
            lint(document)
    finally:
        del ATTRIBUTE_KINDS["some_future_policy_attribute"]
