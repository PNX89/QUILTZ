"""The boundary is one list, and everything that states it renders from that list.

This is the first test in the repository on purpose. The claim QUILTZ makes is not that an
emulator is good enough; it is that an emulator result plus an honest boundary is worth
something. That makes the boundary the load-bearing artefact, and the way a boundary rots is by
being written down three times.
"""

from __future__ import annotations

from quiltz.boundary import NOT_REPRODUCED, PROVED, Limit


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
    assert len(PROVED) >= 4
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
