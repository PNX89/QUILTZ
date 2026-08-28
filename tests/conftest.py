"""Consume parliament's own resource leak once, before any test can inherit it.

parliament 1.6.4 opens `iam_definition.json` at import and never closes it. The garbage
collector eventually raises a ResourceWarning for that handle, and because this repository runs
pytest with warnings as errors, whichever test happened to be running when the collector fired
would fail. Which test that is varies between runs, so the symptom is a suite that fails
somewhere different each time for a reason belonging to neither test.

The obvious fix, a `filterwarnings` entry, was tried and rejected. Matching by warning class
would have ignored `PytestUnraisableExceptionWarning` everywhere, hiding a leak in this
repository's own code, which is the one thing that warning is worth keeping for. Matching by
message meant a regex against text pytest assembles at runtime, which is brittle in exactly the
way the original problem was.

So the import is forced here and the collector is run immediately, at session scope, before any
test exists to be blamed. Warnings stay as errors everywhere else, and a leak this repository
introduces still fails the build.
"""

from __future__ import annotations

import gc
import warnings
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _absorb_parliaments_leaked_handle() -> Iterator[None]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import parliament  # noqa: F401

        gc.collect()
    yield
