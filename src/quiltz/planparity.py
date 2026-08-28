"""Whether two independently licensed binaries agree about what they would build.

The two-binary matrix is the repository's headline decision and the licence is why it exists:
Terraform is BUSL 1.1 until its change date, OpenTofu is MPL-2.0. A matrix that ran both and
never compared their answers would be theatre, so this compares them.

WHAT A NAIVE COMPARISON GETS WRONG. The human-readable plans differ on the first line, because
one says "Terraform used the selected providers" and the other says "OpenTofu". Diffing those
byte for byte fails for a reason that is not a disagreement, and the obvious next move, diffing
loosely, would pass a plan that genuinely disagreed.

So the JSON plans are compared instead, with an EXHAUSTIVE, DECLARED allowlist of the leaves
that are about the tools rather than the infrastructure. Measured on 28-8-2026 with Terraform
1.16.0 and OpenTofu 1.12.6 there were thirteen such leaves and not one of them concerned what
would be created:

  applyable, complete                     fields Terraform 1.16 emits and OpenTofu 1.12 does not
  variables.*.required, variables.*.type  fields OpenTofu emits and Terraform does not
  provider_name, full_name                the registry the IDENTICAL provider was fetched from,
                                          registry.terraform.io against registry.opentofu.org
  terraform_version, timestamp            which tool ran, and when

The allowlist is the point. Anything outside it is a real disagreement and fails, so the day a
version bump introduces a fourteenth difference this stops rather than absorbing it.

AND THE ALLOWLIST IS BY PATH, NOT BY LEAF NAME. It was by leaf name until 28-8-2026, which meant
the entry admitting OpenTofu's variable metadata also forgave `.resource_changes[0].type`: the
kind of resource the plan would build. Changing one plan's bucket to a DynamoDB table produced
sixteen differences and none of them counted. Every exemption is now anchored to the place it
was measured in, and `test_a_changed_resource_type_is_not_forgiven` is the test that keeps it
that way.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = [
    "ORDER_INSENSITIVE",
    "TOOL_METADATA_PATHS",
    "Difference",
    "Exemption",
    "canonical",
    "compare",
]

# Lists in a plan whose ELEMENT ORDER carries no meaning, so two plans that list the same things
# in a different sequence agree.
#
# Found the hard way on 28-8-2026: the identity plan regenerated on a Linux runner listed the
# same four relevant_attributes as the one committed from macOS, with two of them swapped. The
# comparison walks lists positionally, so that read as four disagreements about infrastructure.
#
# The tempting fix was to exempt `relevant_attributes` in TOOL_METADATA_PATHS, which would have
# stopped the failure and also stopped the check from ever noticing that the set of attributes
# had changed. Sorting instead keeps every element under comparison and gives up only the
# sequence, which is the thing that was never meaningful.
ORDER_INSENSITIVE: dict[str, str] = {
    ".relevant_attributes": (
        "a set of attributes the plan depends on. Terraform emits it in an order that differs "
        "between machines: the same four entries came back with two swapped on a Linux runner"
    ),
}


def canonical(plan: Any) -> Any:
    """A copy of the plan with order-insensitive lists sorted, so a reordering is not a diff.

    Applied to both sides before comparing. Sorting is by the JSON text of each element, which
    is stable and needs no knowledge of what the elements mean.
    """

    def walk(node: Any, path: str) -> Any:
        if isinstance(node, dict):
            return {key: walk(value, f"{path}.{key}") for key, value in node.items()}
        if isinstance(node, list):
            items = [walk(value, f"{path}[{index}]") for index, value in enumerate(node)]
            if path in ORDER_INSENSITIVE:
                return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
            return items
        return node

    return walk(plan, "")


# Paths that describe the tool rather than the infrastructure.
#
# THESE ARE PATHS, NOT LEAF NAMES, AND THE DIFFERENCE IS THE WHOLE POINT. They were leaf names
# until 28-8-2026, matched wherever they appeared, and that was a hole big enough to drive the
# headline claim through. `type` is on this list to forgive the variable metadata OpenTofu emits
# at `.configuration.root_module.variables.<name>.type`. As a bare leaf name it also forgave
# `.resource_changes[0].type`, which is the kind of resource the plan would create. Rewriting one
# plan's `aws_s3_bucket` to `aws_dynamodb_table` produced sixteen differences and zero of them
# were counted as real. A guard that forgives the single most important field in the document it
# is guarding is worse than no guard, because it reads as one.
#
# Each entry is anchored against the full path, so an exemption cannot travel. Every one carries
# the reason it exists, because an unexplained exemption is how an allowlist becomes a way of
# passing.


class Exemption:
    """One place where the two tools may differ, and why."""

    __slots__ = ("leaf", "reason", "where")

    def __init__(self, leaf: str, where: str, reason: str) -> None:
        self.leaf, self.where, self.reason = leaf, where, reason

    def covers(self, path: str) -> bool:
        return re.fullmatch(self.where, path) is not None

    def __repr__(self) -> str:  # pragma: no cover
        return f"Exemption({self.leaf!r}, {self.where!r})"


TOOL_METADATA_PATHS: tuple[Exemption, ...] = (
    Exemption(
        "applyable",
        r"\.applyable",
        "Terraform 1.16 emits it at the root, OpenTofu 1.12 does not",
    ),
    Exemption(
        "complete",
        r"\.complete",
        "Terraform 1.16 emits it at the root, OpenTofu 1.12 does not",
    ),
    Exemption(
        "required",
        r"\.configuration\.root_module\.variables\.[^.]+\.required",
        "OpenTofu records whether a variable is required and Terraform omits it",
    ),
    Exemption(
        "type",
        r"\.configuration\.root_module\.variables\.[^.]+\.type",
        "OpenTofu records a variable's declared type and Terraform omits it. Scoped to "
        "variables: a type anywhere else is the kind of resource being created",
    ),
    Exemption(
        "provider_name",
        r"\.(planned_values\.root_module\.resources\[\d+\]|resource_changes\[\d+\])"
        r"\.provider_name",
        "the registry the identical provider was fetched from, "
        "registry.terraform.io against registry.opentofu.org",
    ),
    Exemption(
        "full_name",
        r"\.configuration\.provider_config\.[^.]+\.full_name",
        "the same registry difference, recorded once more in the provider configuration",
    ),
    Exemption(
        "terraform_version",
        r"\.terraform_version",
        "which binary produced the plan, which is the thing being varied here",
    ),
    Exemption(
        "timestamp",
        r"\.timestamp",
        "when the plan was produced, and the two runs cannot be simultaneous",
    ),
)


class Difference:
    """One leaf on which the two plans disagree."""

    __slots__ = ("detail", "path")

    def __init__(self, path: str, detail: str) -> None:
        self.path, self.detail = path, detail

    @property
    def leaf(self) -> str:
        return self.path.rsplit(".", 1)[-1].split("[")[0]

    @property
    def is_tool_metadata(self) -> bool:
        """Whether this exact path is exempt. Matched against the path, never the leaf alone."""
        return any(e.covers(self.path) for e in TOOL_METADATA_PATHS)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Difference({self.path!r}, {self.detail!r})"


def _walk(left: Any, right: Any, path: str, out: list[Difference]) -> None:
    if type(left) is not type(right):
        out.append(Difference(path, f"type {type(left).__name__} against {type(right).__name__}"))
        return
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            here = f"{path}.{key}"
            if key not in left:
                out.append(Difference(here, "present only in the second plan"))
            elif key not in right:
                out.append(Difference(here, "present only in the first plan"))
            else:
                _walk(left[key], right[key], here, out)
    elif isinstance(left, list):
        if len(left) != len(right):
            out.append(Difference(path, f"length {len(left)} against {len(right)}"))
            return
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            _walk(a, b, f"{path}[{index}]", out)
    elif left != right:
        out.append(Difference(path, f"{left!r} against {right!r}"))


def compare(first: dict[str, Any], second: dict[str, Any]) -> list[Difference]:
    """Every leaf on which two JSON plans disagree, tool metadata included.

    Nothing is filtered here. The caller decides what to forgive, and it does so against
    `TOOL_METADATA_LEAVES`, so the exemptions are readable in one place rather than buried in a
    comparison function that quietly skips things.
    """
    out: list[Difference] = []
    _walk(canonical(first), canonical(second), "", out)
    return out
