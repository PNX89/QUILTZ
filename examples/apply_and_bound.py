#!/usr/bin/env python3
"""What applying this to an emulator established, and what it cannot establish.

    uv run python examples/apply_and_bound.py

Runs anywhere, with no emulator, no cloud account and no container. Everything below is
computed from artefacts committed in this repository, and every one of those artefacts is
regenerated in CI, so nothing here is a number somebody typed once.

The point of printing both columns together is that the left one is worthless without the
right. An emulator result with no stated limit is a claim about production that nobody made.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
import warnings

# parliament 1.6.4 imports pkg_resources, which setuptools deprecates loudly. Filtered to that
# one module rather than globally, so nothing this repository writes has its warnings hidden.
warnings.filterwarnings("ignore", category=UserWarning, module="parliament")

# Imported after the filter above, deliberately: parliament emits its warning at import time,
# so an import placed before the filter would print it before anything could suppress it.
from quiltz.boundary import NOT_REPRODUCED, PROVED  # noqa: E402
from quiltz.planparity import compare  # noqa: E402
from quiltz.policies import documents_in_plan, lint, unknown_in_plan  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLANS = ROOT / "docs" / "evidence" / "plans"


def rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(text, width=94, initial_indent=indent, subsequent_indent=indent)


def main() -> None:
    rule("What the emulator established")
    for claim in PROVED:
        print(wrap(f"+ {claim}"))

    rule("What it cannot tell you, whatever the tests say")
    for limit in NOT_REPRODUCED:
        print(f"    - {limit.name}")
        print(wrap(f"it does: {limit.what_the_emulator_does}", indent="        "))
        print(wrap(f"so it cannot say: {limit.what_it_therefore_cannot_tell_you}", "        "))

    rule("Two binaries, one configuration")
    terraform = json.loads((PLANS / "terraform.json").read_text())
    opentofu = json.loads((PLANS / "opentofu.json").read_text())
    differences = compare(terraform, opentofu)
    about_infrastructure = [d for d in differences if not d.is_tool_metadata]
    print(
        f"    Terraform {terraform['terraform_version']} against "
        f"OpenTofu {opentofu['terraform_version']}"
    )
    print(
        f"    {len(differences)} leaves differ, {len(about_infrastructure)} of them about "
        f"what would be built"
    )
    for difference in differences:
        print(f"      {difference.leaf:<20} {difference.path}")

    rule("Every policy the modules write")
    for name in ("identity-terraform.json", "events-terraform.json"):
        plan = json.loads((PLANS / name).read_text())
        for document in documents_in_plan(plan):
            findings = lint(document)
            verdict = "clean" if not findings else ", ".join(f.issue for f in findings)
            print(f"    linted    {document.origin:<52} {verdict}")
        for origin in unknown_in_plan(plan):
            print(f"    UNREADABLE {origin:<51} (known after apply)")
    print()
    print(
        wrap(
            "The last line is the honest part. That policy interpolates the ARNs of a queue and a "
            "topic that do not exist yet, so at plan time it has no body and nothing can lint it. "
            "Naming it is the difference between a document that was checked and one that was "
            "never visible."
        )
    )


if __name__ == "__main__":
    main()
