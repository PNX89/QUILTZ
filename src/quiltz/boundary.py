"""What the emulator does not reproduce, as data rather than as a paragraph.

This module exists from the first commit because it is the repository's whole thesis. An
emulator result is worth something only when its boundary is stated, and a boundary that lives
in prose gets copied, drifts, and ends up saying different things in the README, the ADR and
the tests.

So it is declared once here, and every consumer reads this list rather than restating it.

THAT PARAGRAPH USED TO CLAIM MORE, AND IT WAS CORRECTED ON 28-8-2026. It said the README's first
screenful renders from this list, that the ADR renders from it, and that a test asserts all three
agree. None of the three was true. The README did not exist yet, nothing rendered from anything,
and no such test had been written. A file whose entire subject is the gap between what is claimed
and what is established had a paragraph of its own on the wrong side of that gap, which is the
most expensive kind of error this repository can make.

What is true today: the list is declared here, `tests/test_boundary.py` pins the names and the
count so nothing is added or renamed quietly, and each entry that could be measured cites the
transcript that measured it. When the README is written its boundary table must be generated
from this list rather than typed beside it, and the test that asserts they agree belongs in the
same commit as the generator.

Each is a thing moto does not do rather than a thing it does badly. That distinction matters:
"slower than AWS" is a performance note, while "does not evaluate IAM policies" means a test can
pass here and the same policy can deny in production.

A FIFTH LIMIT WAS ADDED HERE ON 28-8-2026 AND THEN REMOVED THE SAME DAY, AND THE EPISODE IS
WORTH MORE THAN THE ENTRY WOULD HAVE BEEN. While wiring SQS to Lambda to SNS, a message put on
the arrivals queue produced no announcement in twelve seconds, so "moto creates the event source
mapping and never fires it" went in as a limit.

It was false. The handler was being invoked the whole time and dying, because moto runs handlers
in a container where `127.0.0.1` is the container's own loopback: the invocation returned
`EndpointConnectionError` against `http://127.0.0.1:5599/`. Nothing arrived because the function
could not reach the emulator, not because nothing ran. Once the handler was given
`host.docker.internal`, a message on the queue produced an announcement in about two seconds with
no manual invocation at all.

THE IAM ENTRY WAS ALSO WRONG, IN THE OTHER DIRECTION, AND WAS REWRITTEN ON 28-8-2026 RATHER
THAN REMOVED. It said the emulator accepts a policy document and stores it, and cannot tell you
whether that policy would permit or deny. The first half is true by default. The second half is
not true at all: moto ships an opt-in access control mode, and with it on, a user carrying an
explicit Deny is refused, a policy naming one queue does not reach another, and moto's own
module-level TODO claiming Resource is unsupported is out of date. Anyone who knows moto would
have said so, and the entry would have cost more credibility than the limit was worth.

The real limit is narrower and more useful: conditions are ignored. That is worth knowing,
because a condition is precisely how a policy is made safe. The measurement is committed at
docs/evidence/iam/what-moto-evaluates.txt and re-derived by scripts/measure_boundary.py.

The lesson is not about moto. **An absence is not a mechanism.** Reading "nothing arrived" as
"nothing was triggered" skipped over a second explanation that was sitting in the invocation
response, and it would have shipped a false limitation in the one file this repository asks a
reader to trust. What caught it was the test written to guard the entry, which said that if the
emulator ever started polling the limit must be deleted rather than left standing.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["NOT_REPRODUCED", "PROVED", "Limit"]


@dataclass(frozen=True, slots=True)
class Limit:
    """One thing the emulator does not reproduce, and what that costs a reader."""

    name: str
    what_the_emulator_does: str
    what_it_therefore_cannot_tell_you: str


NOT_REPRODUCED: tuple[Limit, ...] = (
    Limit(
        name="IAM condition evaluation",
        what_the_emulator_does=(
            "store every policy and, by default, consult none of them: a user carrying an "
            "explicit Deny on every action and every resource created a bucket. Its opt-in "
            "access control does evaluate, and it gets Action and Resource right"
        ),
        what_it_therefore_cannot_tell_you=(
            "whether a Condition would permit or deny. With enforcement switched on, a policy "
            "allowing sqs:* only from a source address the caller does not have permitted the "
            "call anyway. A condition is how a policy narrows itself, by source address, by "
            "MFA, by tag, by VPC endpoint, so the element a policy most often relies on to be "
            "safe is simply absent from the decision here. "
            "Measured in docs/evidence/iam/what-moto-evaluates.txt"
        ),
    ),
    Limit(
        name="S3 consistency",
        what_the_emulator_does=(
            "answer every read from local state at once, including a read of a bucket "
            "configuration that was changed a moment earlier"
        ),
        what_it_therefore_cannot_tell_you=(
            "that the sequence in this repository has a race at AWS. Object reads are not the "
            "issue and have not been since 2020: S3 is strongly read-after-write consistent for "
            "PUT and DELETE in every region. BUCKET CONFIGURATION is not, and AWS says so in the "
            "same document, recommending a wait of about fifteen minutes after enabling "
            "versioning before issuing writes. modules/storage enables versioning and the "
            "playbook puts objects into that bucket seconds later, which the emulator will "
            "never once complain about. Nor can it show two writers to one key, where AWS is "
            "last-writer-wins with no object locking and no predictable order"
        ),
    ),
    Limit(
        name="request cost",
        what_the_emulator_does="charge nothing and count nothing",
        what_it_therefore_cannot_tell_you=(
            "that a module which converges here would be expensive at AWS. A loop that lists a "
            "bucket a thousand times is free in this suite"
        ),
    ),
    Limit(
        name="service quotas",
        what_the_emulator_does=(
            "accept as many resources as are asked for: 130 buckets in a row without one "
            "refusal, where an AWS account stops at 100 and needs an increase to go further"
        ),
        what_it_therefore_cannot_tell_you=(
            "that a plan exceeding an account limit will fail at apply. Every quota is infinite "
            "here, so no test in this repository can meet one that a real account would meet. "
            "Measured in docs/evidence/iam/what-moto-evaluates.txt"
        ),
    ),
)

# What the emulator DOES establish, stated beside the above rather than under it, because a
# boundary printed alone reads as an apology and a boundary printed in two columns reads as a
# measurement.
# THREE OF THE FIVE SENTENCES HERE WERE NARROWED ON 28-8-2026, BECAUSE THEY CLAIMED MORE THAN
# ANYTHING ESTABLISHED. The other two were left exactly as written, and this comment said EVERY
# sentence had been narrowed until 30-8-2026, which is a number overstated in the file that
# exists to stop numbers being overstated. This is the column a reader is most likely to take at
# face value, so it is the one that had to be checked hardest, and it had never been checked at
# all: the only test guarding it asserted a length.
#
#   "converges, under two independent binaries" was a word rather than a measurement. OpenTofu
#   planned and never applied anything anywhere in the repository, and nothing asserted that a
#   repeat apply changes nothing under either binary. Both are now applied twice, and the second
#   run is required to report nothing to do: scripts/prove_convergence.sh.
#
#   "every IAM policy document the modules create" covered three of the four the modules write.
#   The suite read one plan and modules/events was never linted at all.
#
#   "blocks on a lock" is contradicted by this repository's own transcript. A second apply is
#   refused and exits 1 immediately. It does not block, and the difference matters to anybody
#   deciding whether a CI pipeline can safely run two applies at once.
PROVED: tuple[str, ...] = (
    "the configuration parses and plans under two independent binaries, and applying it twice "
    "under each of them leaves nothing to do the second time",
    "the same configuration produces the same plan under Terraform and under OpenTofu",
    "every IAM policy document the modules write is either linted or named as one a plan "
    "cannot show, with nothing falling between the two",
    "a second concurrent apply is refused by a lock and exits, rather than waiting or "
    "corrupting shared state",
    "a Helm chart renders and lints without any cluster existing",
)
