"""The boundary is one list, and everything that states it renders from that list.

This is the first test in the repository on purpose. The claim QUILTZ makes is not that an
emulator is good enough; it is that an emulator result plus an honest boundary is worth
something. That makes the boundary the load-bearing artefact, and the way a boundary rots is by
being written down three times.
"""

from __future__ import annotations

import pathlib
import re

from quiltz.boundary import NOT_REPRODUCED, PROVED, Limit

CONVERGENCE = pathlib.Path(__file__).resolve().parents[1] / "docs" / "evidence" / "convergence"

# A transcript carries two result lines and the claim is about the second one, so both are read
# by their label. Reading them by label is the whole fix: the assertion here used to be a
# substring search for a no-op result anywhere in the file, and a file recording that the first
# apply did nothing and the second built two resources, which is the opposite of the claim,
# satisfied it.
RESULT = re.compile(r"^(?P<which>first|second)\s+run:\s*(?P<line>.*)$", re.M)
COUNTS = re.compile(r"(?P<added>\d+) added, (?P<changed>\d+) changed, (?P<destroyed>\d+) destroyed")


def result_lines(transcript: str) -> dict[str, str]:
    """The two Apply complete lines, keyed by which run produced them."""
    found = {match["which"]: match["line"].strip() for match in RESULT.finditer(transcript)}
    assert set(found) == {"first", "second"}, (
        f"a convergence transcript records the runs it made, and this one labels {sorted(found)}"
    )
    return found


def counts(line: str) -> tuple[int, int, int]:
    """Added, changed and destroyed, out of one Apply complete line."""
    counted = COUNTS.search(line)
    assert counted, f"no apply result to read in {line!r}"
    return int(counted["added"]), int(counted["changed"]), int(counted["destroyed"])


def converges(transcript: str) -> bool:
    """A first apply that built something, and a second that then found nothing to do.

    Both halves, because either on its own is satisfied by a transcript that proves nothing: a
    repeat apply changing nothing after a first apply that also changed nothing describes a
    configuration that was never applied. scripts/prove_convergence.sh makes exactly this pair
    of checks in the shell before it writes the file, and the offline suite made neither.
    """
    lines = result_lines(transcript)
    return counts(lines["first"])[0] > 0 and counts(lines["second"]) == (0, 0, 0)


def test_every_limit_that_has_been_found_is_here_and_the_count_is_asserted() -> None:
    """Four, and the count is asserted so a fifth has to be added on purpose.

    All four came from the specification. A fifth was added on 28-8-2026 and removed the same
    day: see the module docstring. Asserting the count is what made both the addition and the
    removal deliberate rather than quiet edits, which is the whole reason the number is here.
    """
    names = {limit.name for limit in NOT_REPRODUCED}
    assert names == {
        "IAM condition evaluation",
        "S3 consistency",
        "request cost",
        "service quotas",
    }
    assert len(NOT_REPRODUCED) == 4
    assert "IAM policy evaluation" not in names, (
        "the IAM entry was renamed on 28-8-2026 because it claimed the emulator cannot evaluate "
        "policies at all, which is false: with its opt-in access control on it evaluates Action "
        "and Resource correctly. What it ignores is the Condition. See the module docstring."
    )
    assert "event source polling" not in names, (
        "this was added as a fifth limit on 28-8-2026 and removed the same day, because it was "
        "false: moto does poll, and the handler had been failing to reach the emulator from "
        "inside its container. See the module docstring. Do not add it back without measuring."
    )


def test_every_limit_says_what_it_costs_the_reader_and_not_only_what_is_missing() -> None:
    """A limitation with no consequence is a disclaimer, and nobody reads disclaimers."""
    for limit in NOT_REPRODUCED:
        assert isinstance(limit, Limit)
        assert limit.what_the_emulator_does, f"{limit.name} does not say what the emulator does"
        assert len(limit.what_it_therefore_cannot_tell_you) > 60, (
            f"{limit.name} states a gap without stating what the gap costs, which is the "
            f"difference between a boundary and an apology"
        )


def test_the_proved_column_is_not_empty_and_does_not_overreach() -> None:
    """The other half of the table. A boundary printed alone reads as an apology."""
    assert len(PROVED) == 5
    forbidden = ("production", "at aws", "correct at", "guarantee")
    for claim in PROVED:
        lowered = claim.lower()
        for word in forbidden:
            assert word not in lowered, f"the proved column overreaches with {word!r}: {claim}"


def test_the_consistency_limit_names_the_race_in_this_repository() -> None:
    """It is easy to write "the emulator is consistent and AWS is not" and mean nothing by it.

    Since 2020 S3 has been strongly read-after-write consistent for PUT and DELETE in every
    region, so a limit phrased around object reads would be describing a problem AWS solved.
    What is still eventually consistent is bucket configuration, and AWS recommends waiting
    about fifteen minutes after enabling versioning before writing. This repository provisions
    a bucket with versioning and then configures its contents seconds later, so the limit is
    about this configuration rather than about S3 in the abstract.

    The test names the sequence, so the claim cannot be softened back into a generality.
    """
    limit = next(limit for limit in NOT_REPRODUCED if limit.name == "S3 consistency")
    said = limit.what_it_therefore_cannot_tell_you
    assert "fifteen minutes" in said, "the specific guidance is what makes the limit checkable"
    assert "modules/storage" in said, "the limit does not say which of this repository races"
    assert "2020" in said, (
        "without the date this reads as though object reads were still the problem, which "
        "would be describing S3 as it stopped being six years ago"
    )


def test_each_proved_claim_names_something_this_repository_actually_establishes() -> None:
    """The PROVED column, checked by content rather than by length.

    The only guard on this list used to be `len(PROVED) >= 4`, which passes on a list of five
    fabricated sentences and on a list with an entry removed. It is the column a reader is most
    likely to take at face value and it was the least defended thing in the file.

    Each claim is tied here to the specific artefact that establishes it. A claim that cannot be
    tied to one does not belong in this column.
    """
    claims = {claim[:40]: claim for claim in PROVED}
    assert len(claims) == len(PROVED), "two claims start with the same forty characters"

    joined = "\n".join(PROVED)

    # Convergence: both binaries apply twice, and the second run must find nothing to do. The
    # transcripts themselves are read by the two tests below this one.
    assert "applying it twice" in joined, (
        "the convergence claim no longer says what convergence means, and 'converges' on its "
        "own was a word rather than a measurement for as long as it stood alone"
    )

    # Policy coverage: linted or named, with nothing in between.
    assert "either linted or named" in joined, (
        "the policy claim has been widened back to 'every policy', which was false while the "
        "suite read one plan and modules/events was never linted"
    )

    # The lock refuses; it does not block.
    assert "is refused by a lock and exits" in joined
    assert "blocks on a lock" not in joined, (
        "this repository's own statelock transcript shows a second apply exiting 1 immediately "
        "rather than waiting, so 'blocks' was contradicted by evidence already committed"
    )


def test_both_convergence_transcripts_record_a_second_apply_with_nothing_to_do() -> None:
    """The claim, read off the line that carries it rather than off the file.

    Each half is asserted separately so a failure says which one went: a second apply that built
    something is a configuration that does not converge, and a first apply that built nothing is
    a measurement of nothing at all.
    """
    for binary in ("terraform", "tofu"):
        transcript = CONVERGENCE / f"{binary}.txt"
        assert transcript.exists(), f"{binary} is claimed to converge with no transcript"
        text = transcript.read_text(encoding="utf-8")
        assert text.splitlines()[0].startswith("$ "), f"{binary}.txt does not record its command"

        lines = result_lines(text)
        assert counts(lines["second"]) == (0, 0, 0), (
            f"the second apply under {binary} reported {lines['second']!r}, so the configuration "
            f"does not describe a fixed point and the PROVED column cannot say it does"
        )
        assert counts(lines["first"])[0] > 0, (
            f"the first apply under {binary} added nothing, so the second one changing nothing "
            f"proves nothing: {lines['first']!r}"
        )


def test_a_transcript_with_its_two_runs_the_other_way_round_is_refused() -> None:
    """The guard, run against the transcript it was written for rather than trusted.

    The swap is the one that was survived: the first apply does nothing and the second builds
    two resources, which is the opposite of convergence, and a no-op result line is still
    somewhere in the file for a substring search to find.
    """
    honest = (CONVERGENCE / "terraform.txt").read_text(encoding="utf-8")
    assert converges(honest), "the committed transcript no longer records what it claims"

    lines = result_lines(honest)
    swapped = (
        honest.replace(lines["first"], "SWAP")
        .replace(lines["second"], lines["first"])
        .replace("SWAP", lines["second"])
    )
    assert "0 added, 0 changed, 0 destroyed" in swapped, (
        "the swapped transcript no longer contains a no-op result, so it is not the file that "
        "used to pass and this test would be proving something else"
    )
    assert not converges(swapped), (
        "a transcript whose first apply did nothing and whose second built two resources was "
        "read as convergence"
    )
