"""The committed demo output and the card's numbers, checked against this repository.

Both files are published: `docs/evidence/demo.txt` is the terminal block on
pnx89.github.io/QUILTZ and `docs/evidence/facts.json` supplies the figures beside it. Committed
evidence with nothing regenerating it is the defect this repository keeps finding in itself, so
it is not left as one here.

This file exists because the script it guards was adapted from a sibling whose own docstring
promised a `tests/test_docs.py` that had never been written. The claim was three months of
commits old and nothing had ever run it. Writing the guard was cheaper than the sentence.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence"
DEMO = EVIDENCE / "demo.txt"
FACTS = EVIDENCE / "facts.json"


def facts() -> dict[str, object]:
    return dict(json.loads(FACTS.read_text(encoding="utf-8")))


def test_the_committed_demo_output_is_what_the_demo_prints_now() -> None:
    """Byte for byte, against a live run.

    The demo reads only committed artefacts, so it is deterministic and this comparison is
    exact rather than approximate. If it ever stops being deterministic the right answer is to
    make it so, not to loosen this.
    """
    result = subprocess.run(
        [sys.executable, "examples/apply_and_bound.py"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == DEMO.read_text(encoding="utf-8"), (
        "docs/evidence/demo.txt is not what the demo prints. It is published on the Pages card, "
        "so regenerate it deliberately:\n  uv run python scripts/capture_evidence.py"
    )


def test_the_demo_output_is_not_empty_or_an_error() -> None:
    """A separate assertion, because a comparison of two empty files also passes."""
    text = DEMO.read_text(encoding="utf-8")
    assert len(text.splitlines()) > 40, "the captured demo is too short to be the real thing"
    assert "Traceback" not in text, "the captured demo output contains a traceback"
    assert "What it cannot tell you" in text, (
        "the captured output does not contain the boundary, which is the point of the demo"
    )


def test_the_card_states_the_offline_test_total() -> None:
    """Collected in a subprocess, and the marked suites subtracted.

    The number on the card is what a reader gets by cloning this and running pytest with
    nothing installed. Folding in the tests that need Docker, helm or an emulator would make
    the card claim a suite the reader cannot run.
    """
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=300,
    )
    total = re.search(r"^(\d+) tests? collected", collected.stdout, re.M)
    assert total, f"pytest reported no collection total:\n{collected.stdout[-400:]}"
    every = int(total.group(1))

    marked = 0
    for marker in ("emulator", "container", "helm"):
        listed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-o",
                "addopts=",
                "--collect-only",
                "-q",
                "-m",
                marker,
            ],
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=300,
        )
        marked += len([line for line in listed.stdout.splitlines() if "::" in line])

    assert marked > 0, "no marked tests were found, so the subtraction below proves nothing"
    assert facts()["tests"] == every - marked, (
        f"the card says {facts()['tests']} tests and there are {every - marked} offline. "
        f"Regenerate with scripts/capture_evidence.py"
    )


def test_the_card_claims_only_the_python_versions_ci_tests() -> None:
    """Read from the matrix, so the card cannot advertise support nothing runs."""
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    versions = sorted({v for v in re.findall(r'"(3\.\d+)"', workflow)}, key=lambda v: int(v[2:]))
    assert versions, "no Python versions in the CI matrix"
    assert facts()["python"] == f"{versions[0]} to {versions[-1]}"


def test_the_card_names_the_version_this_package_declares() -> None:
    """A card naming a release that does not match the package is a card about another build."""
    from quiltz import __version__

    assert facts()["release"] == f"v{__version__}"


def test_every_fact_the_card_needs_is_present_and_the_count_is_asserted() -> None:
    """Five keys. The count is asserted so a sixth cannot arrive unchecked by the tests above."""
    recorded = facts()
    assert set(recorded) == {"tests", "python", "release", "captured", "runUrl"}
    assert isinstance(recorded["tests"], int) and recorded["tests"] > 0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(recorded["captured"])), recorded["captured"]
