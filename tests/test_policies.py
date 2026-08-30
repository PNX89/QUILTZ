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
import re
from typing import Any

import pytest

from quiltz.policies import (
    ATTRIBUTE_KINDS,
    Document,
    Finding,
    Kind,
    documents_in_plan,
    lint,
    unknown_in_plan,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
PLANS = REPO / "docs" / "evidence" / "plans"
GENERATOR = REPO / "scripts" / "regenerate_plans.sh"

# The plans this suite reads used to be two filenames typed here. Reading only the identity one,
# which is what it did until 28-8-2026, left the two documents in modules/events unlinted while
# the PROVED column said every policy the modules write is linted. Naming two instead of one
# fixed that case and left the shape: a plan committed for any further module was neither linted
# nor named as unreadable, and the completeness assertion below was computed from the same two
# files it was supposed to be pinning, so it moved with them.
#
# So the set is the directory, and the directory is pinned to the one script that writes it.
PLAN_FILES = {
    "terraform.json",
    "opentofu.json",
    "identity-terraform.json",
    "events-terraform.json",
}

PLAN = PLANS / "identity-terraform.json"


def plan() -> dict[str, Any]:
    return dict(json.loads(PLAN.read_text()))


def every_plan() -> list[dict[str, Any]]:
    """Every plan in the evidence directory, not a list of the ones somebody remembered."""
    return [dict(json.loads(path.read_text())) for path in sorted(PLANS.glob("*.json"))]


def test_the_committed_plans_are_exactly_the_ones_the_generator_writes() -> None:
    """The directory, the generator and the name pinned here all have to agree.

    Three ways for the claim below to go quietly false, closed together. A plan file dropped into
    the directory by hand is read by nothing that regenerates it, so it can say anything. A
    target added to the generator with no plan committed means CI regenerates a file the suite
    never sees. And reading the generator without pinning the names here would mean deleting a
    target buys a smaller claim with a green suite, which is how a list read out of the thing
    under test stops being a check at all.
    """
    written = re.findall(r'^\s*"[^"|]+\|[^"|]+\|([^"|]+)\|', GENERATOR.read_text(), re.M)
    assert set(written) == PLAN_FILES, (
        f"scripts/regenerate_plans.sh writes {sorted(written)}. Adding a module means adding it "
        f"here too, which is the point: this suite makes a claim about every policy those "
        f"modules write."
    )
    assert len(written) == len(PLAN_FILES), f"the generator writes a name twice: {written}"
    assert {path.name for path in PLANS.glob("*.json")} == PLAN_FILES, (
        "docs/evidence/plans holds a plan the generator does not write, or is missing one it "
        "does. Nothing regenerates a hand-placed plan, so nothing checks what it claims."
    )


def test_the_modules_produce_the_documents_this_suite_expects() -> None:
    """If a module gains a policy, this fails until somebody looks at it.

    Across every committed plan. The set is spelled out rather than counted, because a count
    would go on passing if one document were swapped for another.
    """
    found = {d.origin for p in every_plan() for d in documents_in_plan(p)}
    assert found == {
        "aws_iam_policy.read_one_bucket.policy",
        "aws_iam_role.reader.assume_role_policy",
        "aws_iam_role.consumer.assume_role_policy",
    }
    kinds = {d.kind for p in every_plan() for d in documents_in_plan(p)}
    assert kinds == {Kind.IDENTITY, Kind.TRUST}


def test_the_documents_a_plan_cannot_show_are_named_rather_than_skipped() -> None:
    """The limit of linting at plan time, stated as data.

    `aws_iam_policy.consume_and_announce.policy` interpolates the ARNs of a queue and a topic
    that do not exist yet, so Terraform reports the whole attribute as unknown and there is no
    body to lint. Before this was named, `documents_in_plan` simply found nothing there and the
    document was counted as neither linted nor unlintable: it was invisible.
    """
    unknown = sorted(u for p in every_plan() for u in unknown_in_plan(p))
    assert unknown == ["aws_iam_policy.consume_and_announce.policy"]


def test_every_policy_the_modules_write_is_either_linted_or_named_as_unreadable() -> None:
    """Nothing falls between the two. This is the assertion the PROVED claim rests on.

    Counted from the configuration blocks rather than from the two functions, so this cannot
    pass by both of them agreeing to miss the same document. The four is a pin rather than an
    observation: it was computed from the same file list it was meant to be checking, so it
    moved whenever the list did.
    """
    written = {
        f"{resource['address']}.{attribute}"
        for p in every_plan()
        for resource in p["configuration"]["root_module"]["resources"]
        for attribute in ATTRIBUTE_KINDS
        if attribute in resource.get("expressions", {})
    }
    accounted = {d.origin for p in every_plan() for d in documents_in_plan(p)} | {
        u for p in every_plan() for u in unknown_in_plan(p)
    }
    assert written == accounted, f"unaccounted for: {sorted(written ^ accounted)}"
    assert len(written) == 4


def test_every_policy_the_modules_create_is_clean() -> None:
    """The claim, over every real plan rather than over a fixture or over one of them.

    This read the identity plan alone, so `aws_iam_role.consumer.assume_role_policy` was found
    by the two tests above and linted by neither.
    """
    offending = [
        f for p in every_plan() for document in documents_in_plan(p) for f in lint(document)
    ]
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


@pytest.mark.parametrize(
    "principal",
    [
        pytest.param("*", id="bare-string"),
        pytest.param(["*"], id="bare-list"),
        pytest.param({"AWS": "*"}, id="scalar-under-a-key"),
        pytest.param({"AWS": ["*"]}, id="list-under-a-key"),
        pytest.param({"AWS": ["arn:aws:iam::111111111111:root", "*"]}, id="one-of-several"),
        pytest.param({"Service": "lambda.amazonaws.com", "AWS": ["*"]}, id="beside-a-service"),
    ],
)
def test_every_spelling_of_a_wildcard_principal_is_caught(principal: object) -> None:
    """Each shape separately, because the suite used to test two and cover one branch.

    Until 28-8-2026 the check read `"*" in principal.values()`, comparing the dict's values with
    the string "*". It caught {"AWS": "*"} and missed {"AWS": ["*"]}. That is not an exotic
    shape: the aws provider emits the scalar form for a principals block with one identifier and
    a JSON array the moment it has two, so adding a second principal to modules/identity would
    have disarmed the only check for a role the whole internet can assume, with the suite green.

    The parametrize looked like it explored the shape space. It tested two spellings of one
    branch.
    """
    document = Document(
        address="aws_iam_role.example",
        attribute="assume_role_policy",
        body={
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": principal, "Action": "sts:AssumeRole"}],
        },
    )
    assert "TRUST_PRINCIPAL_STAR" in [f.issue for f in lint(document)]


def test_a_principal_shape_the_check_does_not_understand_raises() -> None:
    """Rather than being read as "no wildcard here" and reported clean.

    A guard that quietly accepts what it cannot parse reports clean for documents it never
    examined, and that is the whole failure this module is written against.
    """
    document = Document(
        address="aws_iam_role.example",
        attribute="assume_role_policy",
        body={
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Principal": {"AWS": 42}, "Action": "sts:AssumeRole"}
            ],
        },
    )
    with pytest.raises(TypeError, match="shape this check has not been taught"):
        lint(document)


@pytest.mark.parametrize(
    "action",
    [
        "sts:AssumeRole",
        "sts:AssumeRoleWithSAML",
        "sts:AssumeRoleWithWebIdentity",
        "sts:SetSourceIdentity",
        "sts:TagSession",
    ],
)
def test_no_legitimate_assume_action_is_reported_as_a_finding(action: str) -> None:
    """The other direction, which is the one that puts false findings into committed evidence.

    sts:AssumeRoleWithSAML and sts:SetSourceIdentity were both missing from the allowed set, so
    a perfectly ordinary SAML federation trust policy was reported as granting something other
    than assuming the role. A linter that cries wolf on correct configuration is worse than
    absent, because the next real finding is read as noise.

    One case per action, so a missing entry names itself instead of failing a bundle.
    """
    document = Document(
        address="aws_iam_role.example",
        attribute="assume_role_policy",
        body={
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": action,
                }
            ],
        },
    )
    assert [f.issue for f in lint(document)] == []


def test_an_action_outside_the_family_is_still_reported() -> None:
    """Widening the allowed set must not have widened it to everything."""
    document = Document(
        address="aws_iam_role.example",
        attribute="assume_role_policy",
        body={
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "s3:GetObject",
                }
            ],
        },
    )
    assert "TRUST_UNEXPECTED_ACTION" in [f.issue for f in lint(document)]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"Version": "2012-10-17", "Statement": []}, id="empty-list"),
        pytest.param({"Version": "2012-10-17"}, id="no-statement-key"),
    ],
)
def test_a_document_with_no_statements_is_not_called_clean(body: dict[str, Any]) -> None:
    """It used to return no findings, which is an empty list for a document nobody examined."""
    document = Document(address="aws_iam_role.example", attribute="assume_role_policy", body=body)
    assert [f.issue for f in lint(document)] == ["TRUST_NO_STATEMENT"]


def test_the_set_of_trust_checks_is_pinned() -> None:
    """So a sixth check cannot ship untested with the suite green.

    The issue codes are read out of the source rather than out of a run, because a check that is
    never triggered by any fixture would not appear in a run at all, which is exactly the case
    this is meant to catch.
    """
    from quiltz import policies

    source = pathlib.Path(policies.__file__).read_text(encoding="utf-8")
    codes = set(re.findall(r'"(TRUST_[A-Z_]+)"', source))
    assert codes == {
        "TRUST_NO_PRINCIPAL",
        "TRUST_NO_STATEMENT",
        "TRUST_NOT_ALLOW",
        "TRUST_PRINCIPAL_STAR",
        "TRUST_UNEXPECTED_ACTION",
    }, f"the set of trust checks changed to {sorted(codes)}. Add the test with the check."


def test_no_finding_carries_a_blank_title() -> None:
    """parliament returns an empty title on this API, exactly as it returns an empty severity.

    The module docstring warned against presenting a blank as a rating and named severity. The
    title is blank by the same mechanism, was stored anyway, and the warning sat one field away
    from the thing it described.

    Checked over real findings from a genuinely over-broad policy, rather than over the clean
    plans, because a clean document produces no findings and this would pass vacuously.
    """
    over_broad = Document(
        address="aws_iam_policy.too_much",
        attribute="policy",
        body={
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}],
        },
    )
    findings = lint(over_broad)
    assert findings, "the fixture is not over-broad enough to produce a finding"
    for finding in findings:
        assert finding.title, f"{finding.issue} has a blank title"
        assert finding.issue, "a finding with no issue code cannot be looked up"


def test_the_severity_field_is_not_reported_at_all() -> None:
    """The other half of the same warning, asserted rather than trusted.

    If a severity ever appears on Finding it will be parliament's blank unless somebody has
    chosen a scale deliberately, and an invented rating on a security finding is worse than none.
    """
    assert not hasattr(Finding, "severity"), (
        "Finding grew a severity field. parliament's is an empty string on this API, so it can "
        "only have been invented by the reporting layer"
    )
