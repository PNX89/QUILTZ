"""Every claim the README makes, checked against the repository it describes.

Written before the README, which is the only order that works. A test written afterwards is
written to pass, and the first one here failed for a real reason: the boundary table did not
exist yet, and neither did the generator that the boundary module's own docstring claimed was
rendering it.

When one of these fails the first question is whether the TEST is wrong. Twice in this
repository it was: a test that banned a phrase rather than a claim failed against the paragraph
explaining the phrase was wrong, and a test that asserted an exact lock count failed on a
platform where the count was different and the claim was not.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
README = REPO / "README.md"

sys.path.insert(0, str(REPO / "scripts"))


def readme() -> str:
    return README.read_text(encoding="utf-8")


def test_the_readme_boundary_table_matches_the_declared_limits() -> None:
    """The generated block, regenerated and compared.

    boundary.py's docstring said the README rendered from the list long before either the README
    or the generator existed. This is the test that makes the sentence true rather than
    aspirational, and it is why the table is generated at all: every number that went wrong in
    this repository went wrong by being typed twice.
    """
    from readme_block import block

    text = readme()
    start, end = "<!-- boundary:start -->", "<!-- boundary:end -->"
    assert start in text and end in text, "the README has no generated boundary block"
    committed = text[text.index(start) : text.index(end) + len(end)]
    assert committed == block(), (
        "the README's boundary table is not what boundary.py declares. Regenerate it:\n"
        "  uv run python scripts/readme_block.py --write"
    )


def test_the_boundary_table_is_above_the_fold() -> None:
    """A boundary a reader has to scroll for is a boundary stated for the author's benefit.

    Forty lines is the bar the portfolio checker uses for the headline file, and the same bar
    is applied here to the thing this repository exists to say.
    """
    lines = readme().splitlines()
    position = next(i for i, line in enumerate(lines) if "<!-- boundary:start -->" in line)
    assert position < 40, f"the boundary table starts at line {position + 1}, below the fold"


def test_every_command_the_readme_shows_is_one_this_repository_runs() -> None:
    """Every fenced shell command, checked against what is actually here.

    Not by running them: several need an emulator, a container or a PostgreSQL. What is checked
    is that the thing each one invokes exists, which is the failure that actually happens. A
    README telling a reader to run a script that was renamed is the most ordinary way for one
    to become false.
    """
    commands = []
    for fence in re.findall(r"```(?:bash|console|sh)\n(.*?)```", readme(), re.S):
        for line in fence.splitlines():
            line = line.strip().removeprefix("$ ").strip()
            if line and not line.startswith("#"):
                commands.append(line)
    assert commands, "the README shows no commands at all"

    for command in commands:
        words = command.split()
        for word in words:
            if word.startswith(("scripts/", "examples/", "modules/", "harness/", "charts/")):
                assert (REPO / word).exists(), f"{command!r} names {word}, which does not exist"
        if "pytest" in words and "-m" in words:
            marker = words[words.index("-m") + 1].strip("\"'")
            declared = (REPO / "pyproject.toml").read_text(encoding="utf-8")
            assert f'"{marker}:' in declared, f"{command!r} uses marker {marker!r}, undeclared"


def test_the_readme_plan_output_is_the_one_both_binaries_produce() -> None:
    """Any figure the README gives about the two plans, recomputed from the plans.

    The number of differing leaves is the repository's headline measurement and the easiest
    thing in it to leave behind after a version bump. It is computed here rather than read.
    """
    import json

    from quiltz.planparity import compare

    plans = REPO / "docs" / "evidence" / "plans"
    terraform = json.loads((plans / "terraform.json").read_text())
    opentofu = json.loads((plans / "opentofu.json").read_text())
    differences = compare(terraform, opentofu)
    real = [d for d in differences if not d.is_tool_metadata]

    text = readme()
    assert str(len(differences)) in text, (
        f"the two plans differ on {len(differences)} leaves and the README does not say so"
    )
    assert not real, "the plans disagree about infrastructure, which the README cannot claim"
    assert terraform["terraform_version"] in text, "the README does not name the Terraform version"
    assert opentofu["terraform_version"] in text, "the README does not name the OpenTofu version"

    # And the versions in the README must be the ones the plans were made with, not any two
    # version-shaped strings that happen to appear.
    for version in (terraform["terraform_version"], opentofu["terraform_version"]):
        assert re.search(rf"\b{re.escape(version)}\b", text), version


def test_every_path_and_link_in_the_readme_resolves() -> None:
    """Every repository-relative path, and every link target inside the repository.

    External URLs are not fetched: a test that reaches the network fails for reasons that have
    nothing to do with this repository, and a reviewer running the suite on a train would see a
    red result about somebody else's outage.
    """
    text = readme()
    missing = []

    for path in re.findall(r"\[`([^`\]]+)`\]", text):
        if not (REPO / path).exists():
            missing.append(f"backticked reference [{path}]")

    for target in re.findall(r"\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (REPO / target.split("#")[0]).exists():
            missing.append(f"link target {target}")

    for target in re.findall(r"^\[[^\]]+\]:\s*(\S+)\s*$", text, re.M):
        if target.startswith(("http://", "https://", "#")):
            continue
        if not (REPO / target.split("#")[0]).exists():
            missing.append(f"reference definition {target}")

    assert not missing, "the README points at things that are not here:\n  " + "\n  ".join(missing)


def test_the_readme_names_the_headline_file_the_defence_card_names() -> None:
    """N36 in the portfolio checker, asserted here so it fails in this repository's own CI.

    The vault check runs from outside and a reviewer never sees it. This one runs on every push.
    """
    lines = readme().splitlines()[:40]
    assert any("src/quiltz/boundary.py" in line for line in lines), (
        "the first forty lines do not send a reader to src/quiltz/boundary.py, which is the "
        "file this repository asks to be judged on"
    )


def test_the_readme_does_not_claim_the_whole_repository_is_container_free() -> None:
    """The must-never-claim list, enforced rather than remembered.

    moto executes Lambda handlers inside Docker. Five of the six legs here need no runtime and
    one does, and rounding that to "container-free" would be exactly the over-reading this
    repository exists to refuse.
    """
    text = readme().lower()
    for banned in ("entirely container-free", "no containers anywhere", "container-free by design"):
        assert banned not in text, (
            f"the README claims {banned!r}, which is not true of the Lambda leg"
        )
    if "container-free" in text:
        assert "lambda" in text, (
            "the README says container-free without anywhere naming the leg that is not"
        )


def test_the_readme_does_not_call_terraform_open_source() -> None:
    """Terraform is BUSL 1.1 until its change date. OpenTofu is MPL-2.0.

    That difference is the reason the two-binary matrix exists at all, so getting it wrong in
    the README would undercut the repository's own headline decision.
    """
    text = readme()
    assert not re.search(
        r"open[- ]source\s+Terraform|Terraform,?\s+(?:an?\s+)?open[- ]source", text, re.I
    ), "Terraform is BUSL 1.1, not open source"
    if "BUSL" in text:
        assert "MPL" in text, "the README names one licence of the pair and not the other"


def test_the_generator_is_idempotent() -> None:
    """Generating twice gives the same block, so a diff always means something changed.

    This was marked `helm` at first, with the reasoning that it needed somewhere a write was
    safe. That was a misuse of the marker, which means "needs the helm binary" and nothing else:
    a suite whose markers describe when a test is convenient rather than what it requires stops
    being a description of the test rig. Nothing here needs helm, so nothing here is marked.

    The function is compared with itself rather than the file being rewritten, which is the
    same check without touching the working tree at all.
    """
    from readme_block import block

    assert block() == block()


def test_the_inventory_on_the_front_page_is_the_one_on_disk() -> None:
    """The first fact on the page said six modules. There are three.

    A reader who counts is a reader the whole repository is written for: its argument is that
    infrastructure code can be proved wrong without a cloud account, and the first sentence they
    can check was wrong by a factor of two. That is the cheapest possible thing to get right and
    the most expensive to be caught on.

    Counted from the tree rather than pinned, and the resource total is counted too, because a
    module count alone would still be satisfied by three empty directories.
    """
    modules = sorted(p for p in (REPO / "modules").iterdir() if p.is_dir())
    resources = 0
    for module in modules:
        for tf in module.rglob("*.tf"):
            resources += len(re.findall(r'^resource\s+"', tf.read_text(encoding="utf-8"), re.M))

    words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven"}
    numbers = {
        11: "eleven",
        12: "twelve",
        13: "thirteen",
        14: "fourteen",
        15: "fifteen",
        16: "sixteen",
        17: "seventeen",
        18: "eighteen",
    }
    prose = " ".join(README.read_text(encoding="utf-8").split())

    assert modules, "no modules found at all, so this test is checking nothing"
    assert f"{words[len(modules)]} modules" in prose, (
        f"there are {len(modules)} modules on disk and the front page does not say so"
    )
    assert f"{numbers[resources]} resources" in prose, (
        f"the modules declare {resources} resources and the front page does not say so"
    )

    # The chart and the playbook are named in the same sentence, so they are counted too.
    assert len(list((REPO / "charts").iterdir())) == 1
    assert len(list((REPO / "playbooks").glob("*.yml"))) == 1
