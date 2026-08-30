"""The published card, checked against the two files it is generated from.

WHY THIS FILE EXISTS. The note under the terminal block on `site/index.html` says the output is
committed and that a test fails when it stops matching a live run. Nothing read that file. The
suite compared `docs/evidence/demo.txt` with a live run and `docs/evidence/facts.json` with a
collected test count, and the card was a hand-pasted copy of both with nothing tying it back to
either. So the one artefact that is actually served to a reader was the one artefact with an
enforcement described in prose and never built, which is the defect this repository spends the
rest of its README congratulating itself on finding elsewhere.

Rewriting the card in a scratch copy to say 4200 tests, "9000 leaves differ", and to relabel the
honest `UNREADABLE` policy line as `linted ... clean` left the suite green. That last one would
have published a claim that all four policies are clean, which is the exact overclaim this
repository corrected on 28-8-2026.

The comparison is against the evidence files rather than against a live run: `test_capture.py`
already holds those to a live run, so chaining the card to them puts the card the same distance
from the code. Two links, each of them checked, rather than one link asserted twice.
"""

from __future__ import annotations

import html
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
CARD = REPO / "site" / "index.html"
EVIDENCE = REPO / "docs" / "evidence"

# The card splits one captured run across two <pre> blocks, the second behind a <details>, so the
# terminal panel is a screenful rather than a scroll. Both are the same run and are compared as
# one text: where the split falls is a layout decision and is not this test's business.
PRE = re.compile(r"<pre\b[^>]*>(.*?)</pre>", re.S)
FACT = re.compile(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", re.S)
CAPTURED = re.compile(r"Output captured on (\d{4}-\d{2}-\d{2})")


def card() -> str:
    return CARD.read_text(encoding="utf-8")


def terminal_text() -> str:
    """Every <pre> block on the card, unescaped and joined back into one transcript."""
    blocks = PRE.findall(card())
    assert blocks, "the card shows no terminal output at all, so this test is checking nothing"
    return "\n".join(html.unescape(block) for block in blocks)


def facts() -> dict[str, object]:
    return dict(json.loads((EVIDENCE / "facts.json").read_text(encoding="utf-8")))


def test_the_terminal_block_on_the_card_is_the_captured_run() -> None:
    """Byte for byte against `docs/evidence/demo.txt`, which is itself held to a live run.

    Only newlines at the very edges are forgiven, because a newline immediately after a `<pre>`
    start tag is dropped by the HTML parser and so is written or not written by the generator
    rather than by the run. Everything a reader can see is compared exactly.
    """
    committed = (EVIDENCE / "demo.txt").read_text(encoding="utf-8")
    assert terminal_text().strip("\n") == committed.strip("\n"), (
        "site/index.html no longer shows what docs/evidence/demo.txt records. Regenerate the "
        "card from the evidence rather than editing it, or the page states a run that never "
        "happened."
    )


def test_the_card_shows_the_policy_line_that_admits_one_document_is_unreadable() -> None:
    """Named separately, because it is the line most worth quietly deleting.

    The other assertion here compares the whole transcript, so this one cannot fail on its own
    while that passes. It is written out because a reader of this file should be able to see
    which single line the repository would most like to be caught losing: the fourth policy has
    no body at plan time, and a card listing only the three clean ones would read as four of four.
    """
    assert "UNREADABLE aws_iam_policy.consume_and_announce.policy" in terminal_text(), (
        "the card no longer names the policy a plan cannot show, so it reads as though every "
        "document these modules write was linted and found clean"
    )


def test_every_figure_in_the_strip_is_the_one_the_evidence_records() -> None:
    """Each figure compared inside its own cell, and the set of cells pinned by name.

    Searching the page for the value would prove nothing: a page this long contains any short
    string somewhere. The label is read with the value it labels.
    """
    stated = {label.strip(): value.strip() for label, value in FACT.findall(card())}
    assert set(stated) == {"Tests", "Python", "Release"}, (
        f"the strip of figures on the card is now {sorted(stated)}. Add the comparison with the "
        f"cell, or this test goes on checking the cells that are left."
    )

    recorded = facts()
    assert stated["Tests"] == str(recorded["tests"])
    assert stated["Python"] == recorded["python"]
    assert stated["Release"] == recorded["release"]


def test_the_card_dates_the_capture_the_day_the_evidence_says() -> None:
    """The fourth figure on the card, which is prose rather than a cell.

    A card that says it was captured today from evidence captured in March is making the
    strongest claim on the page and the easiest one to leave behind.
    """
    dated = CAPTURED.search(card())
    assert dated, "the card does not say when its output was captured"
    assert dated.group(1) == facts()["captured"]
