"""Every measured claim about the state lock is checked against its own transcript.

The facts in `statelock.MEASURED` are the answer to "two engineers ran apply at the same time,
what happened", which is one of the interviewer questions this repository is built around. A
fact with no transcript behind it is a memory, and two of these corrected the specification, so
they are the last thing that should be taken on trust.
"""

from __future__ import annotations

import json
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

    # This assertion used to read `noop.answer.startswith("no")`, because the fact did. Both
    # were corrected on 28-8-2026 when the claim was finally tested against a lock that was
    # definitely held rather than against a second no-op that happened to miss it.
    noop = next(m for m in MEASURED if "NOTHING to do" in m.question)
    assert noop.answer.startswith("yes"), (
        "a no-op apply does take the lock. The lock is acquired before the state is read, so "
        "terraform cannot yet know there is nothing to do"
    )
    assert "refused" in noop.detail, "the detail no longer says how it was established"
    assert "no lock at all" in noop.detail, (
        "the superseded claim has been dropped rather than marked as superseded, so a reader "
        "cannot tell this was checked"
    )


def test_no_fact_is_stated_without_a_detail_that_could_be_checked() -> None:
    """An answer with no method behind it is an assertion wearing a measurement's clothes."""
    for measurement in MEASURED:
        assert len(measurement.detail) > 80, f"{measurement.question} has no checkable method"
        assert measurement.question.endswith("?")


@pytest.mark.parametrize("measurement", MEASURED, ids=lambda m: m.evidence)
def test_every_transcript_records_the_command_that_produced_it(measurement: object) -> None:
    """The rule the Ansible transcripts taught, applied here where it had never been applied.

    Until 28-8-2026 not one of these files said how it was made. The worst of them was
    after-sigkill-a-fresh-apply-proceeds.txt, which was an ordinary successful apply with no kill
    visible anywhere in it: nothing in the file distinguished the interesting case from the
    boring one, which is precisely the defect that made a check-mode Ansible run and an ordinary
    one indistinguishable.
    """
    text = (EVIDENCE / measurement.evidence).read_text(encoding="utf-8")  # type: ignore[attr-defined]
    first = text.splitlines()[0]
    assert first.startswith("$ "), (
        f"{measurement.evidence} does not open with the command that produced it, "  # type: ignore[attr-defined]
        f"it opens with {first!r}"
    )


def test_the_kill_is_visible_in_the_transcript_that_claims_one() -> None:
    """Separately, because the parametrised test above only checks the first line.

    A transcript can open with a command and still not show the thing it is evidence for.
    """
    text = (EVIDENCE / "after-sigkill-a-fresh-apply-proceeds.txt").read_text(encoding="utf-8")
    assert "kill -9" in text, "the transcript for a SIGKILL does not show a SIGKILL"
    assert "AFTER SIGKILL" in text, "no count of advisory locks after the kill"
    assert "granted advisory locks WHILE" in text, (
        "no count of advisory locks before the kill, so zero afterwards proves nothing: it "
        "would also be zero if the apply had never taken one"
    )


def test_the_no_op_transcript_shows_a_refusal_rather_than_two_near_misses() -> None:
    """The distinction the corrected fact rests on.

    Two no-op applies that both succeed are consistent with a lock and with no lock, so that
    experiment cannot decide anything. Only contention with a lock that is definitely held can.
    """
    text = (EVIDENCE / "a-no-op-apply-takes-the-lock-too.txt").read_text(encoding="utf-8")
    assert "Error acquiring the state lock" in text, (
        "the no-op apply was not refused, so this transcript does not establish that a no-op "
        "apply contends for the lock"
    )
    assert "hold the lock" in text, "the transcript does not show that a lock was held first"
    assert "every 50ms" in text or "50ms" in text, "the fine-grained sample is not recorded"


def test_the_summary_numbers_say_what_the_facts_say() -> None:
    """Each measured fact, checked against the number the harness actually produced.

    The transcripts cannot be byte-compared: they carry lock ids, resource ids, pids and
    timestamps that differ every run. This file carries only outcomes, so it can be regenerated
    and diffed, which is what stops these five facts drifting the way the plans were drifting
    before anything regenerated them.

    Every number is asserted separately. One assertion over the whole dict would report a single
    failure for any of ten different regressions.
    """
    numbers = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))

    # An apply with work takes exactly one advisory lock, and gives it back.
    assert numbers["an_advisory_lock_is_held_during_an_apply_with_work"] == 1
    assert numbers["advisory_locks_after_that_apply_finished"] == 0

    # A second apply during it is refused rather than made to wait.
    assert numbers["exit_code_of_a_second_apply_during_it"] == 1

    # And so is a no-op apply, which is the fact this file had backwards until 28-8-2026.
    assert numbers["exit_code_of_a_no_op_apply_during_a_held_lock"] == 1, (
        "a no-op apply was NOT refused by a held lock. If that has become true the fifth "
        "measured fact needs rewriting again, and the module docstring with it"
    )
    assert numbers["an_advisory_lock_is_held_during_a_lone_no_op_apply"] == 1, (
        "sampled every 50ms, a lone no-op apply showed no lock at all. That is what a coarse "
        "sample used to show, and it is how the wrong conclusion was reached the first time. "
        "Held-or-not rather than a count: macOS saw one lock and a Linux runner saw two, and "
        "the claim was never about how many"
    )

    # The lock dies with the session, so the kill leaves nothing behind.
    assert numbers["an_advisory_lock_is_held_while_the_doomed_apply_runs"] == 1, (
        "the apply that was about to be killed held no lock, so zero afterwards would prove "
        "nothing at all"
    )
    assert numbers["advisory_locks_after_sigkill"] == 0
    assert numbers["exit_code_of_the_apply_after_sigkill"] == 0

    # force-unlock is supported and had nothing to do.
    assert numbers["advisory_locks_before_force_unlock_ran"] == 0
    assert numbers["exit_code_of_force_unlock"] == 0


def test_the_summary_covers_every_measured_fact() -> None:
    """Ten numbers for five facts, and the count is asserted so a fact cannot arrive unmeasured."""
    numbers = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    assert len(numbers) == 10, (
        f"the summary has {len(numbers)} numbers. If a measurement was added, assert it above "
        f"rather than letting it into the file unchecked"
    )
    assert len(MEASURED) == 5
    assert all(isinstance(value, int) for value in numbers.values())
