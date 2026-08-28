"""Linting the IAM policies the modules produce, not the ones somebody wrote for a slide.

The emulator applies a policy whether it is valid, over-broad or meaningless: that is the
first entry in `boundary.NOT_REPRODUCED`, and it is why this module exists. If the only check
on a policy is that moto accepted it, then nothing has been checked at all.

WHAT IS LINTED, AND WHY IT MATTERS THAT IT IS THIS AND NOT A FIXTURE. The documents come out of
the Terraform plan, so they are the exact JSON the modules would send. A suite that linted
hand-written examples would pass forever while the module drifted, which is the same shape of
defect as a README whose numbers were true once.

A NOTE ON SEVERITY, BECAUSE IT WOULD BE EASY TO REPORT A BLANK AS A RATING. `Finding.severity`
is an empty string on the objects `analyze_policy_string` returns; parliament fills it from its
own configuration only along its command-line path. So nothing here reports a severity. The
issue code and the title are real, and a blank field presented as "severity: LOW" would be a
number invented by the reporting layer.

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
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = ["Document", "Finding", "Kind", "documents_in_plan", "lint"]


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
ASSUME_ACTIONS = {"sts:assumerole", "sts:assumerolewithwebidentity", "sts:tagsession"}


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


def documents_in_plan(plan: dict[str, Any]) -> list[Document]:
    """Every policy document the planned resources would create.

    Raises on a policy attribute that is present and not parseable JSON, rather than skipping
    it. A document the linter cannot read is not a document that passed.
    """
    out: list[Document] = []
    for change in plan.get("resource_changes", []):
        after = (change.get("change") or {}).get("after") or {}
        for attribute in ATTRIBUTE_KINDS:
            raw = after.get(attribute)
            if not raw:
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
            title=str(finding.title),
            detail=str(finding.detail)[:300],
        )
        for finding in analysed.findings
    ]


def _lint_trust(document: Document) -> list[Finding]:
    """The checks parliament cannot make, because it reads every document as an identity policy.

    Three things, each of which is a real way to give a role away, and nothing else. This is
    not a linter and does not pretend to be one.
    """
    out: list[Finding] = []
    statements = document.body.get("Statement") or []
    if isinstance(statements, dict):
        statements = [statements]

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
        elif principal == "*" or (isinstance(principal, dict) and "*" in principal.values()):
            out.append(
                Finding(
                    where,
                    "TRUST_PRINCIPAL_STAR",
                    "any account may assume this role",
                    f"Principal is {principal!r}, which is the whole internet",
                )
            )

        actions = statement.get("Action") or []
        if isinstance(actions, str):
            actions = [actions]
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
