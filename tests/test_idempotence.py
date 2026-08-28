"""The playbook can tell in advance that it has nothing to do.

That is a stronger statement than "running it twice is harmless", and it is the one an operator
has before a change window. The second pass is `--check` for exactly that reason: an ordinary
second run would also report zero changed while proving only that the second run did no damage.

The offline half reads the committed transcripts. The `emulator` marked half re-runs the whole
sequence against moto and re-derives them.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "ansible"
ADR = REPO / "docs" / "adr" / "0002-which-tool-owns-which-lifecycle-stage.md"

RECAP = re.compile(r"ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)")


def recap(name: str) -> tuple[int, int, int, int]:
    """The ok, changed, unreachable and failed counts out of a playbook transcript."""
    text = (EVIDENCE / name).read_text(encoding="utf-8")
    found = RECAP.search(text)
    assert found, f"{name} has no play recap line, so nothing can be read from it"
    return tuple(int(g) for g in found.groups())  # type: ignore[return-value]


def test_terraform_provisioned_the_bucket_before_ansible_touched_it() -> None:
    """The order is the claim. Configuring something nothing provisioned proves nothing."""
    text = (EVIDENCE / "terraform-provisioned-it-first.txt").read_text(encoding="utf-8")
    assert "Apply complete!" in text
    assert "2 added" in text


def test_the_first_run_changes_things() -> None:
    """Without this the zero on the second run could mean the playbook does nothing at all.

    This is the direction that is easy to leave out, and leaving it out would make the
    idempotence proof satisfiable by an empty playbook.
    """
    ok, changed, unreachable, failed = recap("run-1-changes-things.txt")
    assert changed == 2, f"the first run changed {changed} things, so it is not doing the work"
    assert ok == 2
    assert (unreachable, failed) == (0, 0)


def test_the_second_run_in_check_mode_changes_nothing() -> None:
    """The proof itself."""
    ok, changed, unreachable, failed = recap("run-2-check-mode-changes-nothing.txt")
    assert changed == 0, f"check mode reported {changed} pending changes, so it is not idempotent"
    assert ok == 2, "and it still examined both tasks rather than skipping them"
    assert (unreachable, failed) == (0, 0)


def test_the_second_run_really_was_check_mode() -> None:
    """A transcript from an ordinary second run would prove the weaker thing.

    This test was written first and it failed, which is the reason the transcripts look the way
    they do. It originally looked for a DRY RUN banner, on the assumption that ansible-playbook
    prints one in check mode. Core 2.21 does not: the play recap is byte-identical either way,
    so nothing in the captured output distinguished the two runs and the evidence could not
    support the claim being made about it.

    The test was right and the evidence was wrong. Each transcript now records the command that
    produced it on its first line, so the file itself says which run it was.
    """
    first_line = (
        (EVIDENCE / "run-2-check-mode-changes-nothing.txt")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert first_line.startswith("$ "), "the transcript does not record its own invocation"
    assert "--check" in first_line, (
        f"the recorded command is {first_line!r}, which is not a check-mode run, so this "
        f"transcript demonstrates only that running twice is harmless"
    )

    ordinary = (EVIDENCE / "run-1-changes-things.txt").read_text(encoding="utf-8").splitlines()[0]
    assert "--check" not in ordinary, "both transcripts are check-mode runs, so neither did work"


def test_the_boundary_decision_names_what_it_rejected_and_why() -> None:
    """An ADR with no rejected alternative is a description wearing a decision's clothes."""
    text = ADR.read_text(encoding="utf-8")
    assert "Rejected alternatives" in text
    assert "ignore_changes" in text, "the obvious workaround has to be addressed by name"
    assert "What this does not establish" in text
    for claim in ("moto", "one host", "localhost"):
        assert claim in text, f"the ADR does not admit the limit about {claim}"


@pytest.mark.emulator
def test_the_playbook_is_idempotent_against_a_live_emulator() -> None:
    """Needs moto_server and the amazon.aws collection. Re-derives both transcripts."""
    import subprocess

    collections = REPO / "collections"
    assert collections.exists(), "the amazon.aws collection is not fetched; see scripts/"
    env = {
        "PATH": "/usr/bin:/bin",
        "ANSIBLE_COLLECTIONS_PATH": str(collections),
        "QUILTZ_ENDPOINT": "http://127.0.0.1:5599",
        "QUILTZ_BUCKET": "quiltz-evidence",
    }
    playbook = str(REPO / "playbooks" / "configure_evidence_bucket.yml")
    first = subprocess.run(
        ["ansible-playbook", playbook], capture_output=True, text=True, env=env, timeout=300
    )
    assert first.returncode == 0, first.stdout + first.stderr
    second = subprocess.run(
        ["ansible-playbook", "--check", playbook],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    found = RECAP.search(second.stdout)
    assert found and int(found.group(2)) == 0, (
        f"check mode reported changes: {second.stdout[-400:]}"
    )
