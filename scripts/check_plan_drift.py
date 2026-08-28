#!/usr/bin/env python3
"""Fail if a committed plan no longer matches what the configuration produces today.

Run scripts/regenerate_plans.sh first, then this. CI does exactly that, which is what makes
docs/evidence/plans evidence rather than decoration: a file that nothing regenerates is a
claim about the past that quietly stops being true.

WHY THIS IS NOT `git diff --exit-code`. Every plan carries a `timestamp` of the moment it was
produced, so two runs of the same configuration are never byte identical and a plain diff
would fail on every single run. The obvious fix, normalising the timestamp before committing,
was rejected: this repository's argument is that evidence is what the tool actually printed,
and a file edited to be convenient is no longer that.

So exactly one leaf is forgiven, `timestamp`, and it is named here with its reason.

`terraform_version` is deliberately NOT forgiven, although it is forgiven by
`planparity.TOOL_METADATA_LEAVES` when comparing the two binaries to each other. Those are
different questions. There, the version differing is the experiment. Here, it means the binary
that produced this run is not the pinned one, and reporting that as "no drift" would hide a
version bump inside a green check.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from quiltz.planparity import compare

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLANS = ROOT / "docs" / "evidence" / "plans"

FORGIVEN = {
    "timestamp": "when the plan was produced, and two runs cannot be simultaneous",
}


def committed(relative: str) -> dict[str, object]:
    """The file as HEAD has it, read from git rather than from disk.

    Reading from disk would compare the regenerated file with itself.
    """
    blob = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    result: dict[str, object] = json.loads(blob)
    return result


def main() -> int:
    plans = sorted(PLANS.glob("*.json"))
    if not plans:
        print("no plans found, which is itself the failure", file=sys.stderr)
        return 1

    drifted = False
    for path in plans:
        relative = path.relative_to(ROOT).as_posix()
        differences = compare(committed(relative), json.loads(path.read_text()))
        real = [d for d in differences if d.leaf not in FORGIVEN]
        if not real:
            print(f"  {relative}: unchanged ({len(differences)} forgiven)")
            continue
        drifted = True
        print(f"  {relative}: {len(real)} DRIFTED", file=sys.stderr)
        for difference in real[:20]:
            print(f"      {difference.path}: {difference.detail}", file=sys.stderr)
        if len(real) > 20:
            print(f"      ... and {len(real) - 20} more", file=sys.stderr)

    if drifted:
        print(
            "\nA committed plan no longer describes what the configuration produces.\n"
            "If the configuration changed on purpose, commit the regenerated plans with it.\n"
            "If terraform_version is in the list above, the binary is not the pinned one and\n"
            "the plans should NOT be committed until the pin and the workflow agree.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
