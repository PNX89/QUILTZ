"""What the PostgreSQL state backend actually does about two engineers applying at once.

Every fact below was measured on 28-8-2026 against PostgreSQL 17.10 and Terraform 1.16.0, and
the transcripts are in `docs/evidence/statelock/`. Two of them contradict what this repository's
own specification said, which is the reason they are written down as data rather than prose.

THE TRAP, AND IT CAUGHT THIS FILE TWICE. Run the same no-op apply twice at once and you see no
conflict, both processes reporting success, and nothing in `pg_locks`. The obvious conclusion is
that the backend does not serialise anything. The next conclusion, which this file carried until
28-8-2026, is that an apply with nothing to do takes no lock at all.

Both are wrong, and the second is the more embarrassing because it was written down as a measured
fact. A no-op apply DOES take the lock: hold the lock with a real apply and send a no-op at it,
and the no-op is refused, exit 1, "Workspace is already locked". It cannot be otherwise, since
the lock is acquired before the state is read and terraform does not yet know there is nothing to
do. Sampled every fifty milliseconds a lone no-op apply shows one granted advisory lock.

What is true is that a no-op holds it for a fraction of a second. Two of them usually miss each
other, and a sample taken at human speed usually misses it too. A near miss is not an absence,
and an absence is not a mechanism. The transcript is
`a-no-op-apply-takes-the-lock-too.txt`.

ALL FIVE WERE RE-DERIVED ON 28-8-2026 BY `scripts/measure_statelock.sh`, AND THREE OF THEM HAD
EVIDENCE THAT DID NOT SUPPORT THEM. The originals were produced by hand in a scratch directory
nobody could re-run. No transcript recorded its own invocation, which is the rule this repository
had already learned from the Ansible ones, so `after-sigkill-a-fresh-apply-proceeds.txt` was an
ordinary apply transcript with no kill in it and nothing to distinguish it from any other success.
The `pg_locks` samples were quoted in prose and appeared in no file. The fifth fact cited the
transcript belonging to a different experiment, because it had none of its own, and re-deriving it
is what showed the fact itself was wrong.

The harness is committed at `harness/statelock/` so the numbers can be produced again by somebody
who is not the author. Three of its own bugs were caught by the transcripts printing their exit
codes: a no-op pair launched at a tag that had been deliberately refused, so both had real work; a
`kill -9` aimed at a subshell rather than at terraform, leaving the process alive; and a contention
test run against a fresh database, which measures workspace creation and reports a different error.

WHAT THE SPECIFICATION GOT WRONG. It said `force-unlock` is unsupported on the pg backend
because the lock dies with the session. The first half is false: `terraform force-unlock -force`
exits 0 and prints "Terraform state has been successfully unlocked!". The second half is true
and is the more interesting fact, because it makes the first half beside the point: a PostgreSQL
advisory lock is held on a session, so killing the client releases it immediately and the lock
cannot go stale. `force-unlock` works and has nothing to do.

That is a real difference from the arrangement most people have met. With state in S3 and a
DynamoDB lock table, a killed process leaves a row behind, the next apply refuses, and
`force-unlock` is the only way out. Here there is no row to leave behind.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["MEASURED", "Measurement"]


@dataclass(frozen=True, slots=True)
class Measurement:
    """One measured fact, with the transcript that shows it."""

    question: str
    answer: str
    evidence: str
    detail: str


MEASURED: tuple[Measurement, ...] = (
    Measurement(
        question="Does an apply with work to do take a lock?",
        answer="yes, a PostgreSQL advisory ExclusiveLock held for the whole operation",
        evidence="apply-a-holds-the-lock.txt",
        detail=(
            "Sampled in pg_locks while the apply ran, and the sample is in the transcript "
            "rather than quoted here: locktype advisory, mode ExclusiveLock, granted t. One "
            "granted advisory lock during the apply and zero after it"
        ),
    ),
    Measurement(
        question="What happens to a second apply that arrives while it is held?",
        answer="it is refused, and does not wait, corrupt or proceed",
        evidence="apply-b-is-refused.txt",
        detail=(
            "Exit code 1, 'Error acquiring the state lock', 'Workspace is already locked: "
            "default'. The first apply completed normally, replacing one resource"
        ),
    ),
    Measurement(
        question="Does the lock survive the client being killed?",
        answer="no, and that is the point",
        evidence="after-sigkill-a-fresh-apply-proceeds.txt",
        detail=(
            "SIGKILL to the terraform process, which cannot clean up: the postgres session ends "
            "with the connection, pg_locks drops to zero advisory locks, and the next apply "
            "proceeds with no intervention. An advisory lock is session-scoped, so there is no "
            "row left behind to become stale"
        ),
    ),
    Measurement(
        question="Is force-unlock supported here?",
        answer="yes, and it has nothing to do",
        evidence="force-unlock-is-supported.txt",
        detail=(
            "Exit code 0 and 'Terraform state has been successfully unlocked!'. The "
            "specification said it was unsupported and that is simply wrong. What is true is "
            "that it is unnecessary, because the lock cannot outlive the connection that took it"
        ),
    ),
    Measurement(
        question="Does an apply with NOTHING to do take a lock?",
        answer="yes, briefly, which is what makes a naive concurrency test useless",
        evidence="a-no-op-apply-takes-the-lock-too.txt",
        detail=(
            "A no-op apply sent at a lock held by a real one is refused, exit 1, 'Workspace is "
            "already locked'. Sampled every 50ms, a lone no-op apply shows one granted advisory "
            "lock. It holds it for a fraction of a second, so two no-op applies usually miss "
            "each other and a coarse sample sees nothing, which is what this file recorded as "
            "'no lock at all' until it was checked against a lock that was definitely held"
        ),
    ),
)
