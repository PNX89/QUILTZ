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

import contextlib
import pathlib
import sys
from collections.abc import Iterator

import botocore.exceptions
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TRANSCRIPT = REPO / "docs" / "evidence" / "iam" / "what-moto-evaluates.txt"

sys.path.insert(0, str(REPO / "scripts"))


def client_error(code: str, status: int) -> botocore.exceptions.ClientError:
    """One botocore error, shaped the way a service hands one back."""
    return botocore.exceptions.ClientError(
        {"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "GetQueueAttributes",
    )


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


@pytest.mark.parametrize(
    ("code", "status"),
    [
        pytest.param("403", 403, id="what-moto-answers-for-sqs"),
        pytest.param("AccessDenied", 403, id="what-s3-and-iam-answer"),
        pytest.param("AccessDeniedException", 403, id="the-exception-suffixed-spelling"),
    ],
)
def test_a_policy_refusal_is_recorded_as_a_refusal(code: str, status: int) -> None:
    """Offline. The half of allowed() the measurement depends on being able to say yes to."""
    from measure_boundary import allowed

    def refused() -> None:
        raise client_error(code, status)

    assert allowed(refused) is False


def test_a_call_that_goes_through_is_recorded_as_allowed() -> None:
    """Offline. Said directly, so tightening the refusal test cannot make everything a refusal."""
    from measure_boundary import allowed

    assert allowed(lambda: None) is True


def test_a_failure_that_is_not_a_refusal_stops_the_measurement() -> None:
    """Offline, and this is the one that was wrong.

    measure() records `not allowed(...)` as the policy having denied the call, so every
    ClientError counting as a refusal meant an ordinary 400 was written into the transcript as
    evidence that Action and Resource are both evaluated. The probe happened to be right; it
    could not tell a policy decision from a malformed request.

    The error used here is the one that reproduced it: an InvalidAttributeName on the queue the
    policy DOES permit, which has nothing to do with any policy and returns HTTP 400.
    """
    from measure_boundary import allowed

    def broken() -> None:
        raise client_error("InvalidAttributeName", 400)

    with pytest.raises(botocore.exceptions.ClientError, match="InvalidAttributeName"):
        allowed(broken)


class RefusingS3:
    """An emulator that objects at a given bucket, which is the shape a quota has."""

    def __init__(self, refuse_at: int) -> None:
        self.refuse_at = refuse_at
        self.asked = 0

    def create_bucket(self, **_: object) -> None:
        self.asked += 1
        if self.asked >= self.refuse_at:
            raise client_error("TooManyBuckets", 400)


def test_the_quota_probe_returns_the_count_the_emulator_stopped_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offline, with no server at all, because the defect is in the loop rather than in moto.

    measure_quotas() could only ever return its own loop bound or raise: nothing caught the
    refusal and `made` was incremented after the call. So the two guards that report "the
    emulator refused after N buckets" could not run, and a real quota would have surfaced as a
    traceback out of a function whose docstring promises a count.

    Fifty-one is deliberately below the hundred an AWS account allows, so the answer cannot be
    confused with the honest one.
    """
    import measure_boundary

    refusing = RefusingS3(refuse_at=51)

    @contextlib.contextmanager
    def no_server(_: int | None) -> Iterator[str]:
        yield "http://127.0.0.1:1"

    def fake_client(service: str, endpoint: str, key: str = "", secret: str = "") -> object:
        return refusing

    monkeypatch.setattr(measure_boundary, "emulator", no_server)
    monkeypatch.setattr(measure_boundary, "client", fake_client)
    assert measure_boundary.measure_quotas() == 50


def test_the_quota_probe_counts_every_bucket_when_nothing_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other direction, so catching the refusal cannot have turned into swallowing one.

    A break on the first call would also satisfy the test above, and would report a quota of
    zero on an emulator that has none.
    """
    import measure_boundary

    never = RefusingS3(refuse_at=measure_boundary.ATTEMPTS + 1)

    @contextlib.contextmanager
    def no_server(_: int | None) -> Iterator[str]:
        yield "http://127.0.0.1:1"

    def fake_client(service: str, endpoint: str, key: str = "", secret: str = "") -> object:
        return never

    monkeypatch.setattr(measure_boundary, "emulator", no_server)
    monkeypatch.setattr(measure_boundary, "client", fake_client)
    assert measure_boundary.measure_quotas() == measure_boundary.ATTEMPTS
