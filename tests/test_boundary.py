"""The boundary is one list, and everything that states it renders from that list.

This is the first test in the repository on purpose. The claim QUILTZ makes is not that an
emulator is good enough; it is that an emulator result plus an honest boundary is worth
something. That makes the boundary the load-bearing artefact, and the way a boundary rots is by
being written down three times.
"""

from __future__ import annotations

from quiltz.boundary import NOT_REPRODUCED, PROVED, Limit


def test_the_four_limits_the_specification_named_are_all_here() -> None:
    names = {limit.name for limit in NOT_REPRODUCED}
    assert names == {
        "IAM policy evaluation",
        "S3 consistency behaviour",
        "request cost",
        "service quotas",
    }


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
