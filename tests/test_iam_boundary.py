"""The IAM limit, re-derived rather than read.

This file exists because the entry it guards was wrong. `boundary.NOT_REPRODUCED` said the
emulator stores policies and cannot tell you whether one would permit or deny. moto ships an
opt-in access control mode that evaluates them, so the claim was an overstatement of the kind
anyone who has used moto would have caught, and it sat in the one file this repository asks a
reader to trust.

The replacement claim is narrower: conditions are ignored. It is committed as a transcript at
docs/evidence/iam/what-moto-evaluates.txt, and these tests re-run the measurement so the
transcript cannot quietly stop being true. Marked `emulator` because it starts servers, not
because it needs one already running: the measurement starts and stops its own, since the
setting under test is a server-level environment variable and would otherwise leak.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TRANSCRIPT = REPO / "docs" / "evidence" / "iam" / "what-moto-evaluates.txt"

sys.path.insert(0, str(REPO / "scripts"))


def test_the_transcript_records_the_command_that_produced_it() -> None:
    """Offline. The same rule the Ansible transcripts had to learn.

    A captured output that does not say how it was produced cannot support a claim about how
    it was produced, which is how a check-mode run and an ordinary one became indistinguishable
    in docs/evidence/ansible.
    """
    first = TRANSCRIPT.read_text(encoding="utf-8").splitlines()[0]
    assert first == "$ uv run scripts/measure_boundary.py", first


def test_the_transcript_names_the_versions_it_measured() -> None:
    """Offline. A measurement of "moto" without a version is a measurement of nothing."""
    text = TRANSCRIPT.read_text(encoding="utf-8")
    assert "moto 5." in text and "boto3 1." in text


def test_the_transcript_does_not_claim_policies_are_never_evaluated() -> None:
    """Offline. The specific overstatement that was removed, banned as a claim.

    Banning the claim rather than the vocabulary: the words "never consulted" appear in the
    transcript describing the DEFAULT server, which is accurate. What must not reappear is the
    unqualified version.
    """
    text = TRANSCRIPT.read_text(encoding="utf-8")
    assert "Action and Resource are both evaluated" in text, (
        "the transcript no longer records that moto does evaluate policies when asked to, "
        "which is the correction this file exists to preserve"
    )


@pytest.mark.emulator
def test_the_measurement_still_holds() -> None:
    """Starts its own servers and re-runs all four probes.

    If moto gains condition support this fails, and the limit should be rewritten again rather
    than left claiming something untrue. That is what happened to the entry this replaced.
    """
    from measure_boundary import EXPECTED, measure

    assert measure() == EXPECTED


@pytest.mark.emulator
def test_the_quota_probe_still_finds_no_quota() -> None:
    """Separately, because it is a different claim and a shared assertion hides which failed."""
    from measure_boundary import measure_quotas

    made = measure_quotas()
    assert made > 100, (
        f"the emulator refused after {made} buckets. An AWS account stops at 100, so if this "
        f"number has become a real limit the service quotas entry needs rewriting"
    )
