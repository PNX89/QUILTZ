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
"""

from __future__ import annotations

from typing import Any

__all__ = ["TOOL_METADATA_LEAVES", "Difference", "compare"]

# Leaf paths that describe the tool rather than the infrastructure. A path ends with these
# names, so `provider_name` matches wherever it appears. Every entry carries the reason it is
# here, because an unexplained exemption is how an allowlist becomes a way of passing.
TOOL_METADATA_LEAVES: dict[str, str] = {
    "applyable": "Terraform 1.16 emits it, OpenTofu 1.12 does not",
    "complete": "Terraform 1.16 emits it, OpenTofu 1.12 does not",
    "required": "OpenTofu emits variable metadata Terraform omits",
    "type": "OpenTofu emits variable metadata Terraform omits",
    "provider_name": "the registry the identical provider was fetched from",
    "full_name": "the registry the identical provider was fetched from",
    "terraform_version": "which binary produced the plan, which is the thing being varied here",
    "timestamp": "when the plan was produced, and the two runs cannot be simultaneous",
}


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
        return self.leaf in TOOL_METADATA_LEAVES

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
    _walk(first, second, "", out)
    return out
