"""What the PostgreSQL state backend actually does about two engineers applying at once.

Every fact below was measured on 28-8-2026 against PostgreSQL 17.10 and Terraform 1.16.0, and
the transcripts are in `docs/evidence/statelock/`. Two of them contradict what this repository's
own specification said, which is the reason they are written down as data rather than prose.

THE TRAP, AND IT IS AN EASY ONE TO FALL INTO. An apply with nothing to do takes no lock at all.
Running the same no-op apply twice concurrently therefore shows no conflict, no advisory lock in
`pg_locks`, and both processes reporting success, from which the obvious and wrong conclusion is
that the backend does not serialise anything. Both applies have to have real work before the
question is even being asked. That is how this was measured wrongly the first time.

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
            "Sampled in pg_locks while the apply ran: locktype advisory, mode ExclusiveLock, "
            "granted true, held by the backend session serving that client"
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
        answer="no, which is what makes a naive concurrency test useless",
        evidence="apply-b-is-refused.txt",
        detail=(
            "Two concurrent no-op applies both report 'Apply complete! Resources: 0 added, 0 "
            "changed, 0 destroyed' and pg_locks stays empty throughout. Nothing is being "
            "serialised because nothing is being written. Measured this way first, and the "
            "conclusion it invites is the opposite of the truth"
        ),
    ),
)
