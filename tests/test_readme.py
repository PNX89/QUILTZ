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

# The words this page spells out rather than writing in digits. Prose counts are written as words
# in English and as digits in a measurement, and both appear here, so both are compared.
NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
}


def readme() -> str:
    return README.read_text(encoding="utf-8")


def prose() -> str:
    """The README with its hard wrapping collapsed, so a sentence can be matched as a sentence.

    Every claim on this page is wrapped at a hundred columns, and the sentence carrying the
    headline measurement breaks in the middle. A check that searched the raw text would then
    pass or fail on where the line happened to break, which is a guard with a coin in it.
    """
    return " ".join(readme().split())


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


# The sentence that carries the headline measurement, located by the two phrases that make it
# that sentence. Everything between them is free to be reworded; the figures inside it are not.
MEASURED_WITH = r"Measured with (?P<binaries>[^:*]{0,120}):\s*\*\*(?P<leaves>\d+) leaves differ"


def one_match(pattern: str) -> re.Match[str]:
    """The single place on the page making this claim, or a failure that says how many there are.

    Two matches mean the figure is stated in two sentences and this compares whichever came
    first, which is the hole it was written to close one level further down. Zero means the
    sentence was reworded past its anchor, and that has to fail rather than pass vacuously.
    """
    found = re.findall(pattern, prose())
    assert len(found) == 1, (
        f"{pattern!r} matches {len(found)} places on the page and this test compares one of "
        f"them. Re-anchor it on the sentence that now carries the figure."
    )
    match = re.search(pattern, prose())
    assert match is not None
    return match


def test_the_readme_plan_output_is_the_one_both_binaries_produce() -> None:
    """Any figure the README gives about the two plans, recomputed and compared IN ITS SENTENCE.

    The number of differing leaves is the repository's headline measurement and the easiest
    thing in it to leave behind after a version bump.

    THIS USED TO ASK WHETHER THE DIGITS APPEARED ANYWHERE IN THE FILE, and the Python badge
    answers yes on its own: it reads python-3.11 | 3.12 | 3.13, so 11, 12 and 13 are on the page
    before the measurement is written. Each binary version is up there twice as well, in its own
    badge and in the licence note. The sentence could be rewritten to say Terraform 9.9.9 and
    OpenTofu 8.8.8 measured 99 leaves and this passed. A guard a badge satisfies is a guard
    about the badge.
    """
    import json

    from quiltz.planparity import compare

    plans = REPO / "docs" / "evidence" / "plans"
    terraform = json.loads((plans / "terraform.json").read_text())
    opentofu = json.loads((plans / "opentofu.json").read_text())
    differences = compare(terraform, opentofu)
    real = [d for d in differences if not d.is_tool_metadata]
    assert not real, "the plans disagree about infrastructure, which the README cannot claim"

    claim = one_match(MEASURED_WITH)
    assert int(claim.group("leaves")) == len(differences), (
        f"the two plans differ on {len(differences)} leaves and the sentence says "
        f"{claim.group('leaves')}"
    )
    for binary, version in (
        ("Terraform", terraform["terraform_version"]),
        ("OpenTofu", opentofu["terraform_version"]),
    ):
        assert f"{binary} {version}" in claim.group("binaries"), (
            f"the plans were made with {binary} {version} and the sentence claiming the "
            f"measurement says {claim.group('binaries')!r}"
        )


def test_the_heading_over_that_sentence_counts_the_same_differences() -> None:
    """The figure is on the page twice, once as a word, and a fix to one is a fix to neither.

    Written as its own test because it is its own claim: a heading a reader skims is the figure
    they carry away, and it is one line further from the measurement than the sentence under it.
    """
    import json

    from quiltz.planparity import compare

    plans = REPO / "docs" / "evidence" / "plans"
    differences = compare(
        json.loads((plans / "terraform.json").read_text()),
        json.loads((plans / "opentofu.json").read_text()),
    )
    heading = one_match(r"## Two binaries, (?P<count>[a-z]+) differences")
    assert heading.group("count") == NUMBER_WORDS[len(differences)], (
        f"the plans differ on {len(differences)} leaves and the heading says "
        f"{heading.group('count')}"
    )


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

    assert modules, "no modules found at all, so this test is checking nothing"
    assert f"{NUMBER_WORDS[len(modules)].capitalize()} modules" in prose(), (
        f"there are {len(modules)} modules on disk and the front page does not say so"
    )
    assert f"{NUMBER_WORDS[resources]} resources" in prose(), (
        f"the modules declare {resources} resources and the front page does not say so"
    )

    # The chart and the playbook are named in the same sentence, so they are counted too.
    assert len(list((REPO / "charts").iterdir())) == 1
    assert len(list((REPO / "playbooks").glob("*.yml"))) == 1


def test_the_front_page_does_not_say_the_chart_is_applied_to_the_emulator() -> None:
    """The other half of that sentence, which was wrong for longer than the count was.

    It read "every one of them applied to `moto`", counting the chart and the playbook in with
    the modules. The chart is rendered and linted and never installed, which this page says
    itself four sections further down under Limitations, and nothing had ever compared the two
    statements. An opening sentence contradicted by the repository's own limitations section is
    the cheapest possible thing for a reader to catch.

    Written as a ban on the claim rather than on the words: the page has to be free to say what
    the chart IS, and it says so twice.
    """
    text = prose()
    assert "chart is rendered and linted" in text or "chart is linted and rendered" in text, (
        "the page no longer says what is actually done to the chart, which is the sentence "
        "that keeps the opening paragraph honest"
    )
    assert not re.search(r"chart[^.]{0,60}applied to `?moto", text), (
        "the page says the chart is applied to the emulator. It is rendered and linted with no "
        "cluster anywhere, which is what the Limitations section says."
    )


def test_the_policy_tally_on_the_page_is_the_one_the_plans_produce() -> None:
    """Three of four linted, counted from the committed plans rather than from the sentence.

    This is the figure the repository is proudest of, because the fourth document is the one it
    admits it cannot read. A page that drifted to four of four would be claiming exactly the
    thing the whole section exists to refuse, and until now nothing compared the sentence with
    the plans at all.
    """
    import json

    from quiltz.policies import documents_in_plan, unknown_in_plan

    plans = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((REPO / "docs" / "evidence" / "plans").glob("*.json"))
    ]
    linted = {d.origin for plan in plans for d in documents_in_plan(plan)}
    unreadable = {u for plan in plans for u in unknown_in_plan(plan)}

    tally = one_match(r"(?P<linted>[A-Za-z]+) of the (?P<written>[a-z]+) documents these modules")
    assert tally.group("linted").lower() == NUMBER_WORDS[len(linted)], (
        f"{len(linted)} documents are linted and the sentence says {tally.group('linted')}"
    )
    assert tally.group("written") == NUMBER_WORDS[len(linted | unreadable)], (
        f"the modules write {len(linted | unreadable)} documents and the sentence says "
        f"{tally.group('written')}"
    )


def test_the_block_under_that_sentence_lists_the_documents_by_name_and_verdict() -> None:
    """The four lines a reader actually reads, each one against the verdict it reports.

    Counting alone would pass on a block that named the unreadable document and then labelled it
    linted, which is the single edit that would turn this section from an admission into a
    claim of four clean policies.
    """
    import json

    from quiltz.policies import documents_in_plan, unknown_in_plan

    plans = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((REPO / "docs" / "evidence" / "plans").glob("*.json"))
    ]
    linted = {d.origin for plan in plans for d in documents_in_plan(plan)}
    unreadable = {u for plan in plans for u in unknown_in_plan(plan)}
    assert linted and unreadable, (
        "no documents were found in the plans at all, so the loops below would check nothing "
        "and report a pass"
    )

    text = readme()
    for document in linted:
        assert re.search(rf"^linted\s+{re.escape(document)}\s+clean$", text, re.M), (
            f"{document} is linted and clean and the block does not report it that way"
        )
    for document in unreadable:
        named = rf"^UNREADABLE {re.escape(document)}\s+\(known after apply\)$"
        assert re.search(named, text, re.M), (
            f"{document} has no body at plan time and the block does not say so"
        )


def test_the_page_counts_both_columns_of_the_boundary_table() -> None:
    """The sizes of the two lists in `src/quiltz/boundary.py`, in the sentence that cites them.

    The opening paragraph sends a reader to that file and then counts its entries for them, and
    a reader who takes one figure on trust takes the file on trust. The counts of the lists
    themselves are pinned in `tests/test_boundary.py`; what is compared here is the page.
    """
    from quiltz.boundary import NOT_REPRODUCED, PROVED

    limits = one_match(r"of its (?P<entries>[a-z]+) entries")
    assert limits.group("entries") == NUMBER_WORDS[len(NOT_REPRODUCED)], (
        f"there are {len(NOT_REPRODUCED)} limits and the page says {limits.group('entries')}"
    )
    claims = one_match(r"of the (?P<claims>[a-z]+) claims in the left-hand column")
    assert claims.group("claims") == NUMBER_WORDS[len(PROVED)], (
        f"there are {len(PROVED)} proved claims and the page says {claims.group('claims')}"
    )


def test_the_page_counts_the_ci_jobs_the_workflow_declares() -> None:
    """Both figures in the sentence about CI, against the workflow file itself.

    A page that promises five jobs and a workflow that runs four is a reader discovering, at the
    worst moment, that the leg they cared about is the one nobody runs.
    """
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    jobs = re.findall(r"^  ([A-Za-z0-9_-]+):", workflow[workflow.index("\njobs:") :], re.M)
    pythons = sorted({v for v in re.findall(r'"(3\.\d+)"', workflow)})
    assert jobs and pythons, "the workflow declares no jobs or no Python versions to compare"

    stated = one_match(r"(?P<jobs>[A-Za-z]+) CI jobs: the offline suite across (?P<pythons>[a-z]+)")
    assert stated.group("jobs").lower() == NUMBER_WORDS[len(jobs)], (
        f"the workflow declares {len(jobs)} jobs {sorted(jobs)} and the page says "
        f"{stated.group('jobs')}"
    )
    assert stated.group("pythons") == NUMBER_WORDS[len(pythons)], (
        f"the matrix runs {len(pythons)} Python versions {pythons} and the page says "
        f"{stated.group('pythons')}"
    )


def test_the_page_counts_the_state_lock_facts_the_module_declares() -> None:
    """The one figure on the page whose section is otherwise entirely prose."""
    from quiltz.statelock import MEASURED

    stated = one_match(r"The (?P<count>[a-z]+) facts in \[`src/quiltz/statelock\.py`\]")
    assert stated.group("count") == NUMBER_WORDS[len(MEASURED)], (
        f"the module declares {len(MEASURED)} facts and the page says {stated.group('count')}"
    )
