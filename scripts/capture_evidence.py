"""Capture the demo's real output and the numbers the Pages card states.

WHY THIS EXISTS. The card at pnx89.github.io/QUILTZ shows the output of a real run and four
numbers about this repository. Both are committed, which means both can go stale, and a stale
number on a public page is exactly the failure this repository is about.

    docs/evidence/demo.txt    stdout of the demo command, byte for byte
    docs/evidence/facts.json  test total, supported Python range, release tag, capture date

Every number comes from a command rather than from a memory: the test total is collected by
pytest in a subprocess, the Python range is read out of the CI matrix, and the release is the
package version cross-checked against the newest tag.

`tests/test_capture.py` re-runs the demo and fails when the committed output stops matching,
so staleness is a red build rather than a quiet lie. That sentence is worth writing carefully:
the sibling this file was adapted from makes the same claim about a test file that does not
exist, which is how a docstring ends up describing an enforcement nobody built.

    uv run python scripts/capture_evidence.py
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "docs" / "evidence"
DEMO = [sys.executable, "examples/apply_and_bound.py"]


def run(*args: str, cwd: pathlib.Path = REPO) -> str:
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd, timeout=600)
    if result.returncode:
        raise SystemExit(f"{args[0]} failed: {result.stderr.strip()[:400]}")
    return result.stdout


def test_total() -> int:
    """Collected rather than counted, and it is the OFFLINE total.

    `-o addopts=` neutralises this repository's own deselection so pytest reports one figure.
    That figure includes the marked suites, so they are subtracted: the card's number is what a
    reader gets by cloning this and running pytest with nothing installed, and folding in nine
    tests that need Docker, helm or an emulator would make it a suite they cannot run.
    """
    out = run(sys.executable, "-m", "pytest", "-o", "addopts=", "--collect-only", "-q")
    match = re.search(r"^(\d+) tests? collected", out, re.MULTILINE)
    if not match:
        raise SystemExit(f"could not read a collection total from:\n{out[-400:]}")
    every = int(match.group(1))

    marked = 0
    for marker in ("emulator", "container", "helm"):
        listed = run(
            sys.executable, "-m", "pytest", "-o", "addopts=", "--collect-only", "-q", "-m", marker
        )
        found = re.search(r"^(\d+)/(\d+) tests collected", listed, re.MULTILINE)
        marked += (
            int(found.group(1))
            if found
            else len([line for line in listed.splitlines() if "::" in line])
        )
    if marked == 0:
        raise SystemExit("no marked tests found at all, which cannot be right: check the markers")
    return every - marked


def python_range() -> str:
    """Read from the CI matrix, so the card cannot claim support CI does not test."""
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    versions = sorted({v for v in re.findall(r'"(3\.\d+)"', workflow)}, key=lambda v: int(v[2:]))
    if not versions:
        raise SystemExit("no Python versions found in the CI matrix")
    return f"{versions[0]} to {versions[-1]}"


def release() -> str:
    """The package version, cross-checked against the newest tag where tags are reachable.

    `git describe` alone would be wrong: a shallow checkout has no tags, and a version bumped
    without tagging would still report the old one. The version is the claim and the tag is the
    check, so a mismatch stops the capture instead of reaching a published page.
    """
    from quiltz import __version__

    tag = f"v{__version__}"
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"], capture_output=True, text=True, cwd=REPO
    )
    described = result.stdout.strip()
    if result.returncode == 0 and described and described != tag:
        raise SystemExit(
            f"the newest tag is {described} and the package version is {__version__}. "
            "Tag the release or fix the version before publishing a card that names one."
        )
    return tag


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    output = run(*DEMO)
    if not output.strip():
        raise SystemExit("the demo produced no output, refusing to write empty evidence")
    (EVIDENCE / "demo.txt").write_text(output, encoding="utf-8")

    # GITHUB_RUN_ID is set only inside Actions. Locally the card says "captured on <date>" with
    # no link rather than inventing one.
    run_id = os.environ.get("GITHUB_RUN_ID")
    slug = os.environ.get("GITHUB_REPOSITORY", "PNX89/QUILTZ")
    facts = {
        "tests": test_total(),
        "python": python_range(),
        "release": release(),
        "captured": datetime.date.today().isoformat(),
        "runUrl": f"https://github.com/{slug}/actions/runs/{run_id}" if run_id else None,
    }
    (EVIDENCE / "facts.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {EVIDENCE / 'demo.txt'} ({len(output.splitlines())} lines)")
    print(f"wrote {EVIDENCE / 'facts.json'} {facts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
