# QUILTZ

**Infrastructure code can be proved wrong without a cloud account. The honest form of that
sentence names what the proof does not cover, in the same breath, and this repository puts that
on its first screenful rather than in a footnote.**

[![CI](https://github.com/PNX89/QUILTZ/actions/workflows/ci.yml/badge.svg)](https://github.com/PNX89/QUILTZ/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Terraform 1.16 BUSL](https://img.shields.io/badge/terraform-1.16.0%20BUSL--1.1-844fba)](https://github.com/hashicorp/terraform)
[![OpenTofu 1.12 MPL](https://img.shields.io/badge/opentofu-1.12.6%20MPL--2.0-ffda18)](https://opentofu.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Six modules, a chart and a playbook, every one of them applied to `moto` and none of them to an
account. That buys real things and it does not buy everything, and the difference is the subject
here rather than an afterthought. If you open one file, open [`src/quiltz/boundary.py`]: the
right-hand column below is that file, and three of its four entries were wrong when they were
finally measured.

<!-- boundary:start -->

| What this proves | What it cannot tell you |
| --- | --- |
| the configuration parses and plans under two independent binaries, and applying it twice under each of them leaves nothing to do the second time | **IAM condition evaluation** whether a Condition would permit or deny. |
| the same configuration produces the same plan under Terraform and under OpenTofu | **S3 consistency** that the sequence in this repository has a race at AWS. |
| every IAM policy document the modules write is either linted or named as one a plan cannot show, with nothing falling between the two | **request cost** that a module which converges here would be expensive at AWS. |
| a second concurrent apply is refused by a lock and exits, rather than waiting or corrupting shared state | **service quotas** that a plan exceeding an account limit will fail at apply. |
| a Helm chart renders and lints without any cluster existing |  |

Generated from `src/quiltz/boundary.py` by `scripts/readme_block.py`. The list is declared once,
in code, and this table is regenerated from it, because a boundary kept in prose drifts until
the README and the tests say different things.

<!-- boundary:end -->

```console
$ uv run python examples/apply_and_bound.py
```

## Two binaries, thirteen differences, none about what would be built

Terraform is BUSL 1.1 until its change date and OpenTofu is MPL-2.0, which is the whole reason
for running both rather than a nicety. A matrix that ran two binaries and never compared their
answers would be theatre, so [`src/quiltz/planparity.py`] compares the JSON plans leaf by leaf.

Measured with Terraform 1.16.0 and OpenTofu 1.12.6: **13 leaves differ and not one of them
concerns what would be created**. Two fields Terraform emits and OpenTofu does not, two the
other way, four recording which registry the identical provider came from, and the version and
timestamp of the run itself.

The exemptions are anchored to the exact path each difference was measured at. They were leaf
names matched anywhere until they were attacked, and `type` is on the list to admit OpenTofu's
variable metadata: as a bare name it also forgave `.resource_changes[0].type`, the kind of
resource the plan would create. Rewriting one plan's bucket into a DynamoDB table produced
sixteen differences and none of them counted.

```console
$ uv run pytest tests/test_plan_parity.py
```

## Apply it yourself

Everything except the two marked suites runs with nothing installed but Python.

```console
$ uv sync --dev
$ uv run pytest
```

The rest needs binaries, and each is in its own CI job so the boundary of the test rig is drawn
rather than blurred.

```console
$ uv run python -m moto.server -p 5599 --host 0.0.0.0 &
$ scripts/regenerate_plans.sh http://127.0.0.1:5599
$ scripts/prove_convergence.sh terraform http://127.0.0.1:5599 quiltz-converge-terraform
$ uv run pytest -m emulator
```

Convergence is the claim worth checking and the one that was missing longest. An apply that
succeeds tells you it ran. An apply that succeeds and then finds nothing left to do tells you
the configuration describes a fixed point, and that is the property that makes it safe to run
again. Both binaries apply twice, and the second run must report nothing.

## The policy a plan cannot show you

Policies are extracted from the plan, so they are the exact JSON the modules would send rather
than a fixture that passes forever while the module drifts. They are linted by kind: identity
policies through `parliament`, trust policies through a purpose-built check, because parliament
reads every document as an identity policy and answers `MALFORMED` on a perfectly valid trust
policy.

Three of the four documents these modules write are linted. The fourth is not, and saying so is
the point:

```
linted     aws_iam_policy.read_one_bucket.policy        clean
linted     aws_iam_role.reader.assume_role_policy       clean
linted     aws_iam_role.consumer.assume_role_policy     clean
UNREADABLE aws_iam_policy.consume_and_announce.policy   (known after apply)
```

That policy interpolates the ARNs of a queue and a topic that do not exist yet, so at plan time
it has no body at all. Nothing can lint it there. Plan-time policy linting has a hard edge at
computed values, and a suite that counted only what it found would have reported four of four
clean while never having seen this one.

## What two engineers applying at once actually get

Not what this repository said for most of a day. The five facts in [`src/quiltz/statelock.py`]
are re-derived by `scripts/measure_statelock.sh` against a real PostgreSQL in CI, and each
transcript records the command that produced it.

- An apply with work to do takes a PostgreSQL advisory `ExclusiveLock` and gives it back.
- A second apply is **refused and exits 1**. It does not block, does not wait and does not
  proceed, and the difference decides whether a pipeline can safely overlap two applies.
- **An apply with nothing to do takes the lock too.** The lock is acquired before the state is
  read, so Terraform cannot yet know there is nothing to do. It holds it for a fraction of a
  second, which is why two no-op applies usually miss each other and look like proof that
  nothing is serialised at all.
- `SIGKILL` leaves nothing behind. An advisory lock is held on a session, so the lock goes when
  the connection goes. With state in S3 and a DynamoDB lock table the killed process leaves a
  row and the next apply is refused until somebody clears it.
- `force-unlock` works, contrary to the specification that said it does not, and has nothing to
  do, which is the more useful half.

## The one leg that needs a container

`moto` executes Lambda handlers inside Docker. Five of this repository's six legs need no
runtime and this one does, and calling the whole thing container-free would be exactly the
over-reading it exists to refuse. So the Lambda leg is one job, required where Docker exists and
deselected by default, and the handler reaches the emulator by a different address from the one
Terraform uses because inside the container `127.0.0.1` is the container.

```console
$ uv run pytest -m container
```

A message on the queue reaches the topic in about two seconds with nothing invoked by hand.

## Claims that moved when they were checked

Every one of these was written from the specification, sounded obviously true, and was wrong.
They are listed rather than quietly fixed, because otherwise nobody can tell which claims were
checked.

| The claim | What measuring it showed |
| --- | --- |
| moto provisions the event source mapping and never fires it | It fires it. The handler was being invoked and dying on the container's loopback, and twelve seconds of silence had been read as a mechanism. |
| moto cannot evaluate IAM policies | It can. With its opt-in access control on, an explicit `Deny` is refused and `Resource` is honoured. What it ignores is the `Condition`, which is how a policy narrows itself. |
| An apply with nothing to do takes no lock | It takes one. Sent at a lock that is definitely held, a no-op apply is refused. |
| Every IAM policy the modules create is linted | Three of four. The fourth has no body at plan time. |
| The emulator cannot show S3 consistency between writers | True but pointed at the wrong thing. Object reads have been strongly consistent since 2020. Bucket configuration has not, and this repository's own playbook writes into a bucket seconds after Terraform enables versioning on it. |

## Limitations

- Nothing here has ever touched an AWS account, by design. The right-hand column of the table
  above is the complete statement of what that costs.
- One host, `localhost`, and no inventory. Ansible against a fleet is a different subject and
  this is not evidence about it.
- The Helm chart is linted and rendered and never installed. No cluster is involved anywhere,
  so nothing here says a pod would start.
- The state lock facts are PostgreSQL. An S3 and DynamoDB backend behaves differently on
  exactly the point that makes these interesting, and that difference is described rather than
  measured.

## Development

```console
$ uv sync --dev
$ uv run ruff check . && uv run ruff format --check .
$ uv run mypy
$ uv run pytest
```

Five CI jobs: the offline suite across three Python versions, the chart with no cluster, both
binaries against the emulator, the queue-to-topic path that needs a runtime, and the state lock
against a real PostgreSQL. Every committed artefact is regenerated in one of them and the job
fails if it has drifted.

Every figure and every block on this page is checked by `tests/test_readme.py` against the thing
it describes. The boundary table is generated from `src/quiltz/boundary.py` rather than typed
beside it, because every number that went wrong here went wrong by being written twice.

<!-- toolset:start -->

Part of the Q...Z toolset, all of it designing for the failure that does not announce itself:

- [QUACKZ](https://github.com/PNX89/QUACKZ), deflating a backtest that only looks good because
  it was picked out of two hundred.
- [QUOTEZ](https://github.com/PNX89/QUOTEZ), market data an agent can read and cannot act on.
- [QUELLZ](https://github.com/PNX89/QUELLZ), measuring what prompt-injection containment costs
  in utility as well as in attack rate.
- [QUIDZ](https://github.com/PNX89/QUIDZ), refusing the outbound payment that would have gone
  out twice.
- [QUESTZ](https://github.com/PNX89/QUESTZ), stopping a scraper before it writes a CSV from a
  page that changed shape.
- [QUIZZ](https://github.com/PNX89/QUIZZ), answering what a statistic said at the time, and
  refusing when it cannot.
- [QUARANTINEZ](https://github.com/PNX89/QUARANTINEZ), treating an outcome the venue never
  confirmed as terminal rather than as a retry.
- [QUENCHZ](https://github.com/PNX89/QUENCHZ), deciding in the open what a tool server gets free
  while it is still somebody's subprocess.
- QUILTZ, this one: proving infrastructure code wrong without a cloud account, and saying what
  that cannot show.
- [QUAYZ](https://github.com/PNX89/QUAYZ), telling a crash loop from an OOMKill, and naming the
  failure that no single field finds.
- [QUARRYZ](https://github.com/PNX89/QUARRYZ), keeping every version a statistical office
  published, and failing the build when it quietly issues another.
- [QUASHZ](https://github.com/PNX89/QUASHZ), refusing a row whose outcome had not been decided
  yet when the decision would have been made.

<!-- toolset:end -->

## Licence

MIT. See [LICENSE](LICENSE).

Terraform is used as a tool at version 1.16.0 under BUSL 1.1, OpenTofu at 1.12.6 under MPL-2.0,
Ansible as a command under GPL-3.0-or-later, and none of them is vendored into this tree.

[`src/quiltz/boundary.py`]: src/quiltz/boundary.py
[`src/quiltz/planparity.py`]: src/quiltz/planparity.py
[`src/quiltz/statelock.py`]: src/quiltz/statelock.py
