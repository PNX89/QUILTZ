# ADR 0002: Terraform decides that a thing exists, Ansible decides what is in it

**Decided 28-8-2026.** Status: accepted.

## The question

Both tools can create an S3 bucket and both can put an object in one. `amazon.aws.s3_bucket`
would provision the bucket this repository's `modules/storage` provisions, and
`aws_s3_object` would upload the manifest this repository's playbook uploads. So the
question is not which tool is capable. It is which one owns which stage, and why.

## The decision

**Terraform owns existence and shape. Ansible owns contents.**

`modules/storage` decides that the bucket exists, that versioning is on, and what it is called.
`playbooks/configure_evidence_bucket.yml` decides what is inside it. Neither tool touches the
other's stage.

## Why, and it is not a matter of taste

**Terraform's model is a desired end state it owns completely.** Anything inside its state that
drifts becomes a diff on the next plan, and that is the feature. So a bucket's *contents* are
exactly the wrong thing to give it: evidence files arrive continuously and none of them was
asked for by a configuration, so every plan after the first would offer to delete things. The
usual workaround is `lifecycle { ignore_changes = [...] }`, which is a way of telling Terraform
to stop doing the one thing it is for.

**Ansible's model is a set of operations that converge.** It asserts a state now and does not
own what happens next, which is what makes it right for contents. It is also why the idempotence
proof matters: a playbook that reports `changed` on every run is one nobody can safely re-run,
and re-running is the only reason to write it in Ansible rather than in a shell script.

## The proof, measured on 28-8-2026

Transcripts in `docs/evidence/ansible/`.

| step | result |
|---|---|
| Terraform provisions the bucket | `Apply complete! Resources: 2 added, 0 changed, 0 destroyed` |
| Ansible, first run | `ok=2 changed=2 failed=0` |
| Ansible, second run in **check mode** | `ok=2 changed=0 failed=0` |

The second pass is `--check` on purpose. A second ordinary run would also report zero changed,
and it would prove less: it would show that running twice is harmless, not that the playbook can
tell in advance that it has nothing to do. Check mode asks the second question, which is the one
an operator actually has before a change window.

## What this does not establish

The whole of this runs against `moto`, so it says nothing about IAM permitting the upload at AWS,
nothing about S3 consistency between two writers, and nothing about cost. Those are three of the
four limits in `src/quiltz/boundary.py` and they apply here exactly as they apply everywhere else
in this repository.

It also says nothing about Ansible at scale. There is one host, it is `localhost`, and there is
no inventory. Ansible against a fleet is a different subject and this is not evidence about it.

And there is a race here that the emulator will never show, which is worth naming because it sits
exactly on the boundary this decision draws. Terraform enables versioning on the bucket; the
playbook writes objects into it seconds later. Object reads at AWS are strongly consistent and
have been since 2020, so that is not the concern. Bucket configuration is not: AWS recommends
waiting about fifteen minutes after enabling versioning before issuing writes, because the setting
takes time to propagate. An object written inside that window can land unversioned in a bucket
whose configuration says otherwise.

The emulator answers both immediately, so the whole sequence converges here every time and would
keep converging if the gap were a minute or a day. Handing the two stages to two tools is what
makes the gap visible at all, since it is the seam between them. Closing it means a wait or a
check on the propagated configuration before the first write, and this repository does neither:
it names the gap instead, because a fix nothing here can exercise would be a fix nobody can
verify.

## Rejected alternatives

**One tool for both stages.** Simpler to explain and it puts contents into a state file that
will fight the world. Rejected on the reasoning above.

**Ansible provisions too, Terraform absent.** Loses the plan, the two-binary parity check and the
state lock, which are three of the five entries in `boundary.PROVED`. That sentence said "four"
until 28-8-2026 and had said it since the first commit, while the list it refers to has always
had five.

**Terraform manages contents with `ignore_changes`.** Rejected because it is the answer that
looks like a decision and is actually a suppression: the diff is still computed and then hidden,
so the next person to read the module cannot tell what is managed.
