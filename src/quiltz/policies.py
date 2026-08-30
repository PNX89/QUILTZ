"""Linting the IAM policies the modules produce, not the ones somebody wrote for a slide.

The emulator applies a policy whether it is valid, over-broad or meaningless: that is the
first entry in `boundary.NOT_REPRODUCED`, and it is why this module exists. If the only check
on a policy is that moto accepted it, then nothing has been checked at all.

WHAT IS LINTED, AND WHY IT MATTERS THAT IT IS THIS AND NOT A FIXTURE. The documents come out of
the Terraform plan, so they are the exact JSON the modules would send. A suite that linted
hand-written examples would pass forever while the module drifted, which is the same shape of
defect as a README whose numbers were true once.

A NOTE ON THE BLANK FIELDS, BECAUSE IT WOULD BE EASY TO REPORT ONE AS A RATING. `severity` is
an empty string on the objects `analyze_policy_string` returns; parliament fills it from its own
configuration only along its command-line path. So nothing here reports a severity, and a blank
presented as "severity: LOW" would be a rating invented by the reporting layer.

`title` IS BLANK BY EXACTLY THE SAME MECHANISM, and this paragraph said it was real until
28-8-2026 while `_lint_identity`, below, stored `str(finding.title)` into a field the rest of
the module treats as meaningful. So the warning was correct, and the file was committing
the very thing it warned about, one field over. What is genuinely real from the Python API is
the issue code and the detail. An identity finding therefore takes its title from its issue
code, which is the human-readable name parliament gives it, and a test asserts no finding
anywhere carries a blank title.

PARLIAMENT CANNOT LINT A TRUST POLICY, AND THIS IS THE PART WORTH READING. Handed a perfectly
valid `assume_role_policy` it answers `MALFORMED`, detail "Statement contains neither Resource
nor NotResource". That is right for an identity policy and wrong for a trust policy, where the
resource is the role the document is attached to and naming it would be the error. Version
1.6.4's `analyze_policy_string` has no resource-policy mode at all.

There were three ways to handle that and two of them were wrong. Reporting the MALFORMED would
put a false finding in committed evidence. Silently skipping trust policies would mean the
sentence "every policy these modules create is linted" was false for half of them, and that is
the kind of guard that looks present and does nothing. So trust policies get their own explicit
check, small and purpose-built, and a document whose kind is not recognised RAISES rather than
passing through unexamined.

AND THAT SENTENCE WAS FALSE ANYWAY, FOR A DIFFERENT REASON, UNTIL 28-8-2026. The suite read one
plan, from modules/identity. modules/events produces two more documents and neither was ever
linted, so a claim of the form "every policy these modules create" was covering half of them.
Both plans are read now.

Reading the second one turned up the real limit, which is better than the claim it replaced.
`aws_iam_policy.consume_and_announce.policy` interpolates the ARNs of a queue and a topic that
do not exist yet, so at plan time it has no body: Terraform reports it `(known after apply)`.
Nothing can lint it there. `unknown_in_plan` names those documents rather than passing over
them, because the difference between "checked and clean" and "never visible" is the whole
subject of this repository.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = [
    "Document",
    "Finding",
    "Kind",
    "documents_in_plan",
    "lint",
    "unknown_in_plan",
]


class Kind(StrEnum):
    """What sort of policy document this is, because they are not linted the same way."""

    IDENTITY = "identity"
    TRUST = "trust"


# The plan attribute each kind arrives under. Named rather than discovered by pattern, because
# an attribute that happened to be called `policy` and held something else would otherwise be
# handed to a policy linter and reported as unparseable.
ATTRIBUTE_KINDS: dict[str, Kind] = {
    "policy": Kind.IDENTITY,
    "assume_role_policy": Kind.TRUST,
}

# What a trust policy must look like, since parliament will not tell us. Deliberately short: it
# checks the things that are actually dangerous rather than reimplementing a linter.
# The full assume-role family, because a check that reports a legitimate policy is worse than
# no check: it puts a false finding into committed evidence, which is the outcome this module's
# docstring says it refuses. Two were missing until 28-8-2026, so a SAML federation trust policy
# and any policy allowing a caller to set a source identity were both reported as granting
# something other than assuming the role.
ASSUME_ACTIONS = {
    "sts:assumerole",
    "sts:assumerolewithsaml",
    "sts:assumerolewithwebidentity",
    "sts:setsourceidentity",
    "sts:tagsession",
}


@dataclass(frozen=True, slots=True)
class Document:
    """One policy document a module would create, with where it came from."""

    address: str
    attribute: str
    body: dict[str, Any]

    @property
    def origin(self) -> str:
        return f"{self.address}.{self.attribute}"

    @property
    def kind(self) -> Kind:
        return ATTRIBUTE_KINDS[self.attribute]


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing parliament objects to, without a severity it does not supply."""

    origin: str
    issue: str
    title: str
    detail: str


def _written_attributes(plan: dict[str, Any]) -> set[str]:
    """Every `{address}.{attribute}` the configuration itself wrote, shared by both functions
    below so they cannot quietly disagree about what counts as a document this repository wrote.

    ONLY ATTRIBUTES THE CONFIGURATION ACTUALLY SETS COUNT. `aws_sqs_queue` and `aws_sns_topic`
    both carry a `policy` attribute that Terraform marks unknown, or fills in from AWS, whenever
    the configuration is silent about it, because AWS may return one on its own. An attribute
    named `policy` that arrived that way is not a document this repository wrote, and treating it
    as one would hand something the modules never authored to a policy linter.
    """
    return {
        f"{resource['address']}.{attribute}"
        for resource in plan.get("configuration", {}).get("root_module", {}).get("resources", [])
        for attribute in ATTRIBUTE_KINDS
        if attribute in resource.get("expressions", {})
    }


def documents_in_plan(plan: dict[str, Any]) -> list[Document]:
    """Every policy document the planned resources would create.

    Raises on a policy attribute that is present and not parseable JSON, rather than skipping
    it. A document the linter cannot read is not a document that passed. Until 29-8-2026 the
    guard here was `if not raw: continue`, which is true of `None` AND of `""`, so an empty
    string was silently dropped instead of reaching `json.loads` and raising as a whitespace
    string already did. `raw is None` is the only shape that means "nothing planned here": a
    policy Terraform cannot show yet is `null` in `after` and is `unknown_in_plan`'s to name.

    Filtered by `_written_attributes`, the same filter `unknown_in_plan` uses, so the two
    functions cannot disagree about what a "document the modules write" means. Before 29-8-2026
    this function had no such filter, so a `policy` attribute AWS populated on a resource whose
    configuration never set one would be collected here and reported as an identity document
    nobody wrote, while `unknown_in_plan` correctly ignored the same attribute.
    """
    written = _written_attributes(plan)
    out: list[Document] = []
    for change in plan.get("resource_changes", []):
        after = (change.get("change") or {}).get("after") or {}
        for attribute in ATTRIBUTE_KINDS:
            if f"{change['address']}.{attribute}" not in written:
                continue
            raw = after.get(attribute)
            if raw is None:
                continue
            try:
                body = json.loads(raw)
            except (TypeError, ValueError) as broken:
                raise ValueError(
                    f"{change['address']}.{attribute} is not parseable JSON, so it cannot be "
                    f"linted and must not be reported as clean: {broken}"
                ) from None
            out.append(Document(address=change["address"], attribute=attribute, body=body))
    return out


def unknown_in_plan(plan: dict[str, Any]) -> list[str]:
    """Policy attributes the plan marks `(known after apply)`, so nothing can lint them.

    THIS IS THE LIMIT OF PLAN-TIME POLICY LINTING AND IT IS WORTH STATING RATHER THAN SKIPPING.
    A policy whose body interpolates the ARN of a resource that does not exist yet has no body
    at plan time. Terraform reports the whole attribute as unknown, `documents_in_plan` finds
    nothing there, and a suite that only counted what it found would report every policy clean
    while never having seen this one.

    modules/events has exactly this shape: its trust policy names a service and is fully known,
    and its permission policy is assembled from the queue and topic ARNs and is not. Linting at
    plan time buys correctness for the first and can say nothing at all about the second.

    Returning the addresses, rather than a count, so a test can name which ones are unreadable
    and fail when that set changes.

    ONLY ATTRIBUTES THE CONFIGURATION ACTUALLY SETS COUNT; see `_written_attributes`.
    """
    written = _written_attributes(plan)
    out: list[str] = []
    for change in plan.get("resource_changes", []):
        unknown = (change.get("change") or {}).get("after_unknown") or {}
        for attribute in ATTRIBUTE_KINDS:
            origin = f"{change['address']}.{attribute}"
            if unknown.get(attribute) is True and origin in written:
                out.append(origin)
    return sorted(out)


def lint(document: Document) -> list[Finding]:
    """Check one document by the standard appropriate to its kind.

    Exhaustive by name and raising on an unhandled kind. A catch-all here would return an empty
    finding list for a document nobody examined, which reads on a report as clean.
    """
    match document.kind:
        case Kind.IDENTITY:
            return _lint_identity(document)
        case Kind.TRUST:
            return _lint_trust(document)
        case unreachable:  # pragma: no cover
            raise AssertionError(f"policy kind not handled by this match: {unreachable!r}")


def _lint_identity(document: Document) -> list[Finding]:
    """parliament, which is what it is for."""
    import parliament

    analysed = parliament.analyze_policy_string(json.dumps(document.body))
    return [
        Finding(
            origin=document.origin,
            issue=str(finding.issue),
            # parliament's title is an empty string on this API, exactly as its severity is.
            # Storing the blank would put a field the rest of this module treats as meaningful
            # into every identity finding with nothing in it, which is the reporting-layer
            # invention the module docstring warns about.
            title=str(finding.title) or str(finding.issue),
            detail=str(finding.detail)[:300],
        )
        for finding in analysed.findings
    ]


def _identifiers(principal: object) -> list[str]:
    """Every identifier named by a Principal, whatever shape it arrived in.

    THIS EXISTS BECAUSE THE CHECK ABOVE USED TO READ `"*" in principal.values()`, which compares
    the dict's VALUES to the string "*". It therefore caught {"AWS": "*"} and missed
    {"AWS": ["*"]}, and the second is not a hypothetical: the aws provider emits the scalar form
    for a principals block with one identifier and a JSON array the moment it has two. Adding a
    second principal to modules/identity, the ordinary way such a configuration grows, would
    have silently disarmed the only check in this repository for a role the whole internet can
    assume, while the test named "every policy the modules create is clean" went on passing.

    An unrecognised shape RAISES rather than returning nothing. A guard that quietly accepts what
    it does not understand reports clean for documents it never examined, which is the failure
    this whole module is written against.
    """
    if isinstance(principal, str):
        return [principal]
    if isinstance(principal, list):
        return [item for entry in principal for item in _identifiers(entry)]
    if isinstance(principal, dict):
        return [item for value in principal.values() for item in _identifiers(value)]
    raise TypeError(
        f"a Principal of type {type(principal).__name__} is a shape this check has not been "
        f"taught: {principal!r}. Teach it rather than letting the document through unchecked."
    )


def _lint_trust(document: Document) -> list[Finding]:
    """The checks parliament cannot make, because it reads every document as an identity policy.

    Seven checks now, not five. Three are ways to give a role away: an unrestricted Principal, an
    Action outside the assume-role family, and NotAction, which was not read at all until
    29-8-2026 and inverts the set the other two exist to constrain, so a statement excluding only
    `iam:*` grants everything else in AWS. The other four refuse to call a document clean when
    this checker cannot reason about what it grants: no statements, no Principal, no Action and
    no NotAction either, or an Effect other than Allow. This is not a linter and does not pretend
    to be one. The count is pinned by a test, so an eighth cannot arrive without a test arriving
    with it.

    The wildcard check reads every shape a Principal can take. It did not until 28-8-2026, when
    it compared dict values against the string "*" and so missed the array form the aws provider
    emits as soon as a principals block has two identifiers. See `_identifiers`.
    """
    out: list[Finding] = []
    statements = document.body.get("Statement") or []
    if isinstance(statements, dict):
        statements = [statements]

    if not statements:
        # Returning [] here would be an empty finding list for a document nobody examined, which
        # is precisely what this module argues against everywhere else. A trust policy with no
        # statements is not a clean trust policy.
        return [
            Finding(
                document.origin,
                "TRUST_NO_STATEMENT",
                "trust policy has no statements",
                "the document parses and grants nothing, so it is either dead or truncated. "
                "Reporting it clean would be an empty finding list for a document that was "
                "never examined",
            )
        ]

    for index, statement in enumerate(statements):
        where = f"{document.origin}[{index}]"
        principal = statement.get("Principal")
        if not principal:
            out.append(
                Finding(
                    where,
                    "TRUST_NO_PRINCIPAL",
                    "trust policy names nobody",
                    "a trust policy with no Principal cannot be assumed by anything, "
                    "so it is either dead or a mistake",
                )
            )
        elif "*" in _identifiers(principal):
            out.append(
                Finding(
                    where,
                    "TRUST_PRINCIPAL_STAR",
                    "any account may assume this role",
                    f"Principal is {principal!r}, which is the whole internet",
                )
            )

        action = statement.get("Action")
        not_action = statement.get("NotAction")
        if not action and not not_action:
            # `actions = statement.get("Action") or []` used to make this indistinguishable from
            # a statement whose actions all happen to be inside ASSUME_ACTIONS: both produced an
            # empty `outside` and no finding. NotAction was never read at all, so this branch was
            # unreachable by any name and a statement with neither key was reported clean.
            out.append(
                Finding(
                    where,
                    "TRUST_NO_ACTION",
                    "trust statement names no action",
                    "the statement has neither Action nor NotAction, so nothing here says what "
                    "it grants. Reporting it clean would be an empty finding list for a "
                    "statement that was never examined",
                )
            )
        elif not_action:
            out.append(
                Finding(
                    where,
                    "TRUST_NOTACTION",
                    "trust statement uses NotAction, which inverts the allowed set",
                    f"NotAction is {not_action!r}; every action it does not name is implicitly "
                    f"allowed. This checker does not reason about what that leaves in and will "
                    f"not pass it silently",
                )
            )
        else:
            actions = action if isinstance(action, list) else [action]
            outside = [a for a in actions if str(a).lower() not in ASSUME_ACTIONS]
            if outside:
                out.append(
                    Finding(
                        where,
                        "TRUST_UNEXPECTED_ACTION",
                        "a trust policy grants something other than assuming the role",
                        f"actions outside the assume-role family: {outside}",
                    )
                )

        if statement.get("Effect") != "Allow":
            out.append(
                Finding(
                    where,
                    "TRUST_NOT_ALLOW",
                    "trust statement is not an Allow",
                    f"Effect is {statement.get('Effect')!r}, which this checker does "
                    f"not reason about and will not pass silently",
                )
            )
    return out
