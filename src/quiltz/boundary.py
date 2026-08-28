"""What the emulator does not reproduce, as data rather than as a paragraph.

This module exists from the first commit because it is the repository's whole thesis. An
emulator result is worth something only when its boundary is stated, and a boundary that lives
in prose gets copied, drifts, and ends up saying different things in the README, the ADR and
the tests.

So it is declared once here. The README's first screenful renders from it, the architecture
decision record renders from it, and a test asserts all three agree. Adding a fifth limitation
means editing one list and watching two documents fail until they are regenerated.

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
        name="IAM policy evaluation",
        what_the_emulator_does="accepts a policy document and stores it",
        what_it_therefore_cannot_tell_you=(
            "whether the policy would actually permit or deny the call at AWS. A policy that is "
            "over-broad, contradictory or meaningless is applied here exactly as a correct one is"
        ),
    ),
    Limit(
        name="S3 consistency behaviour",
        what_the_emulator_does="answers reads from local state immediately",
        what_it_therefore_cannot_tell_you=(
            "anything about ordering or visibility between concurrent writers, which is the only "
            "reason S3 consistency is ever interesting"
        ),
    ),
    Limit(
        name="request cost",
        what_the_emulator_does="charges nothing and counts nothing",
        what_it_therefore_cannot_tell_you=(
            "that a module which converges here would be expensive at AWS. A loop that lists a "
            "bucket a thousand times is free in this suite"
        ),
    ),
    Limit(
        name="service quotas",
        what_the_emulator_does="accepts as many resources as are asked for",
        what_it_therefore_cannot_tell_you=(
            "that a plan exceeding an account limit will fail at apply. Every quota is infinite "
            "here, so no test can encounter one"
        ),
    ),
)

# What the emulator DOES establish, stated beside the above rather than under it, because a
# boundary printed alone reads as an apology and a boundary printed in two columns reads as a
# measurement.
PROVED: tuple[str, ...] = (
    "the configuration parses, plans and converges, under two independent binaries",
    "the same configuration produces the same plan under Terraform and under OpenTofu",
    "every IAM policy document the modules create is syntactically valid and passes an "
    "offline linter",
    "a second concurrent apply blocks on a lock rather than corrupting shared state",
    "a Helm chart renders and lints without any cluster existing",
)
