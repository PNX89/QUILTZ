#!/usr/bin/env python3
"""Generate the README's boundary table from quiltz.boundary, and check it has not drifted.

    uv run python scripts/readme_block.py --check    exit 1 if README.md disagrees
    uv run python scripts/readme_block.py --write    rewrite the block in place

WHY THIS EXISTS. boundary.py's docstring said the README's first screenful rendered from the
list, and it did not: the README had not been written and no generator existed. That paragraph
was corrected rather than left standing, and this file is the other half of the correction.

The alternative was to type the table beside the list and trust the two to stay equal. Every
number in this repository that went wrong went wrong that way, so the table is generated and a
test fails when it drifts.

Only the block between the markers is generated. The prose around it is written, because a
README entirely produced by a program reads like one.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import textwrap

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from quiltz.boundary import NOT_REPRODUCED, PROVED

README = pathlib.Path(__file__).resolve().parents[1] / "README.md"
START = "<!-- boundary:start -->"
END = "<!-- boundary:end -->"


def cell(text: str) -> str:
    """One table cell. Pipes escaped, and no newlines, because a table row is one line."""
    return " ".join(text.split()).replace("|", "\\|")


def consequence(text: str) -> str:
    """The first sentence, which is the consequence itself.

    Each entry in `NOT_REPRODUCED` opens with a complete statement of what the emulator cannot
    tell you and then explains it. The table takes the statement and leaves the explanation in
    the file, because a first screenful with four-hundred-character cells is a first screenful
    nobody reads, and a reader who wants the rest is one click away from it.

    Truncation was the alternative and was rejected: a sentence cut mid-clause can say something
    its author did not, which is a strange risk to run in a table about honest claims.
    """
    first, separator, _ = " ".join(text.split()).partition(". ")
    return first + "." if separator else first


def block() -> str:
    """The two columns, side by side, longest column padded with empty cells.

    Side by side rather than one list after the other. A boundary printed under a list of
    achievements reads as a disclaimer; printed beside it, it reads as the measurement it is.
    """
    left = [
        f"**{limit.name}** {cell(consequence(limit.what_it_therefore_cannot_tell_you))}"
        for limit in NOT_REPRODUCED
    ]
    right = [cell(claim) for claim in PROVED]
    height = max(len(left), len(right))
    left += [""] * (height - len(left))
    right += [""] * (height - len(right))

    lines = [
        START,
        "",
        "| What this proves | What it cannot tell you |",
        "| --- | --- |",
    ]
    lines += [f"| {proved} | {limit} |" for proved, limit in zip(right, left, strict=True)]
    lines += [
        "",
        textwrap.fill(
            "Generated from `src/quiltz/boundary.py` by `scripts/readme_block.py`. The list is "
            "declared once, in code, and this table is regenerated from it, because a boundary "
            "kept in prose drifts until the README and the tests say different things.",
            width=96,
        ),
        "",
        END,
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print(f"README.md has no {START} / {END} block", file=sys.stderr)
        return 1
    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    rebuilt = head + block() + tail

    if args.write:
        README.write_text(rebuilt, encoding="utf-8")
        print("README.md boundary block rewritten")
        return 0

    if rebuilt != text:
        print(
            "README.md's boundary table is not what boundary.py declares. Regenerate it:\n"
            "  uv run python scripts/readme_block.py --write",
            file=sys.stderr,
        )
        return 1
    print("README.md boundary table matches boundary.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
