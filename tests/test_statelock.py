"""Every measured claim about the state lock is checked against its own transcript.

The facts in `statelock.MEASURED` are the answer to "two engineers ran apply at the same time,
what happened", which is one of the interviewer questions this repository is built around. A
fact with no transcript behind it is a memory, and two of these corrected the specification, so
they are the last thing that should be taken on trust.
"""

from __future__ import annotations

import pathlib

import pytest

from quiltz.statelock import MEASURED

EVIDENCE = pathlib.Path(__file__).resolve().parents[1] / "docs" / "evidence" / "statelock"


@pytest.mark.parametrize("measurement", MEASURED, ids=lambda m: m.evidence)
def test_every_measured_fact_has_the_transcript_it_names(measurement: object) -> None:
    """A named transcript that is not there makes the fact unverifiable."""
    path = EVIDENCE / measurement.evidence  # type: ignore[attr-defined]
    assert path.exists(), f"{path.name} is named as evidence and is not committed"
    assert path.read_text(encoding="utf-8").strip(), f"{path.name} is empty"


def test_the_transcripts_say_what_the_facts_claim() -> None:
    """The specific strings, because a transcript that exists is not a transcript that agrees."""
    refused = (EVIDENCE / "apply-b-is-refused.txt").read_text(encoding="utf-8")
    assert "Error acquiring the state lock" in refused
    assert "Workspace is already locked" in refused

    held = (EVIDENCE / "apply-a-holds-the-lock.txt").read_text(encoding="utf-8")
    assert "Apply complete!" in held, "the apply that held the lock must have finished normally"

    after_kill = (EVIDENCE / "after-sigkill-a-fresh-apply-proceeds.txt").read_text(encoding="utf-8")
    assert "Apply complete!" in after_kill
    assert "Error acquiring the state lock" not in after_kill, (
        "if this transcript shows a lock error then the lock DID survive the kill, and the "
        "claim that it cannot go stale is false"
    )

    unlock = (EVIDENCE / "force-unlock-is-supported.txt").read_text(encoding="utf-8")
    assert "successfully unlocked" in unlock.lower()


def test_the_two_corrections_to_the_specification_are_recorded_as_corrections() -> None:
    """Not quietly fixed. The specification said force-unlock was unsupported and it is not.

    A repository whose subject is honest boundaries cannot silently overwrite a claim it found
    to be wrong, because then nobody can tell which claims were checked.
    """
    from quiltz import statelock

    source = pathlib.Path(statelock.__file__).read_text(encoding="utf-8")
    assert "WHAT THE SPECIFICATION GOT WRONG" in source
    assert "THE TRAP" in source

    force = next(m for m in MEASURED if "force-unlock" in m.question)
    assert force.answer.startswith("yes"), "force-unlock is supported, contrary to the spec"
    assert "unnecessary" in force.detail

    noop = next(m for m in MEASURED if "NOTHING to do" in m.question)
    assert noop.answer.startswith("no")
    assert "opposite of the truth" in noop.detail


def test_no_fact_is_stated_without_a_detail_that_could_be_checked() -> None:
    """An answer with no method behind it is an assertion wearing a measurement's clothes."""
    for measurement in MEASURED:
        assert len(measurement.detail) > 80, f"{measurement.question} has no checkable method"
        assert measurement.question.endswith("?")
