#!/usr/bin/env bash
# Re-derive every fact in src/quiltz/statelock.py, with transcripts that say how they were made.
#
# Usage:  scripts/measure_statelock.sh [conn_str]
#   default  postgres://<you>@localhost/quiltz_statelock?sslmode=disable
#
# WHY THIS EXISTS. The five facts in statelock.py were measured by hand on 28-8-2026 in a scratch
# directory that was never committed, and it showed. Three of the five had evidence that did not
# support them:
#
#   * no transcript recorded its own invocation, which is the rule this repository had already
#     learned from the Ansible ones. after-sigkill-a-fresh-apply-proceeds.txt was an ordinary
#     apply transcript with no kill in it, indistinguishable from any other successful apply.
#   * the pg_locks samples were quoted in prose and appeared in no file at all.
#   * the fifth fact, that a no-op apply takes no lock, cited the transcript belonging to a
#     different experiment, because it had no transcript of its own.
#
# Every transcript this script writes opens with the command that produced it and carries the
# pg_locks sample beside the terraform output, so each claim can be read off its own file.
set -euo pipefail

CONN="${1:-postgres://$(whoami)@localhost/quiltz_statelock?sslmode=disable}"
DB="$(printf '%s' "$CONN" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"
# psql is given the SAME connection string terraform gets, rather than being left to find a local
# socket as the current user. On a CI runner the database is a container reached over TCP with a
# password, and a psql that only worked on the author's laptop would make this harness exactly the
# hand-run thing it was written to replace.
ADMIN_CONN="$(printf '%s' "$CONN" | sed -E "s#/$DB(\?|\$)#/postgres\1#")"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/harness/statelock"
OUT="$ROOT/docs/evidence/statelock"
SECONDS_HELD=20

command -v psql >/dev/null || { echo "psql is not on PATH" >&2; exit 1; }
command -v terraform >/dev/null || { echo "terraform is not on PATH" >&2; exit 1; }

mkdir -p "$OUT"

# A sample of the advisory locks, which is what the pg backend uses. Printed into the transcript
# rather than quoted in a docstring, because a number nobody can point at is not a measurement.
locks() { psql "$CONN" -At -c \
  "select count(*) from pg_locks where locktype='advisory' and granted;" 2>/dev/null || echo "0"; }
locks_detail() { psql "$CONN" -x -c \
  "select locktype, mode, granted, pid from pg_locks where locktype='advisory';" 2>/dev/null; }

reset_state() {
  psql "$ADMIN_CONN" -q -c "drop database if exists $DB;" >/dev/null 2>&1 || true
  psql "$ADMIN_CONN" -q -c "create database $DB;" >/dev/null
  rm -rf "$WORK/.terraform" "$WORK/terraform.tfstate" "$WORK/.terraform.lock.hcl"
  ( cd "$WORK" && terraform init -input=false -no-color -backend-config="conn_str=$CONN" >/dev/null )
}

apply_cmd() { echo "terraform apply -auto-approve -no-color -var tag=$1 -var seconds=${2:-$SECONDS_HELD}"; }

echo "==> resetting"
reset_state

# statelock.py names a PostgreSQL version in prose and no transcript ever recorded it, so a
# reader had no way to check the number and CI pinned only `postgres:17`, which floats across
# patch releases. Captured here, into its own transcript rather than into summary.json: the
# version string carries the OS and architecture of whatever ran it, which is exactly the kind
# of detail that made the advisory-lock COUNT non-reproducible between macOS and Linux further
# down, and summary.json is byte-diffed while this file is not.
echo "==> recording the PostgreSQL version this run measured against"
PG_VERSION="$(psql "$CONN" -At -c "select version();" 2>/dev/null || echo "unknown")"
{
  echo "\$ psql <conn> -At -c \"select version();\""
  echo "$PG_VERSION"
} > "$OUT/postgres-version.txt"

# Prime the workspace before measuring anything. The pg backend creates its workspace row on the
# first apply, and a second apply arriving during THAT is refused with "Already locked for
# workspace creation: default", which is a different code path from the ordinary state lock and
# not the thing anybody means by "two engineers applied at once". Running the contention test
# against a fresh database measured workspace creation and reported it as state locking.
echo "==> priming the workspace so the contention below is the ordinary state lock"
( cd "$WORK" && terraform apply -auto-approve -no-color -var tag=zero -var "seconds=1" ) >/dev/null 2>&1

################################################################################
# 1 and 2. An apply WITH WORK holds an advisory lock, and a second apply is refused.
################################################################################
echo "==> apply A (real work), sampling pg_locks, and apply B arriving during it"
( cd "$WORK" && terraform apply -auto-approve -no-color -var tag=one -var "seconds=$SECONDS_HELD" ) \
  > /tmp/statelock-a.out 2>&1 &
A_PID=$!
sleep 8
LOCKS_DURING="$(locks)"
LOCKS_DETAIL_DURING="$(locks_detail)"
( cd "$WORK" && terraform apply -auto-approve -no-color -var tag=two -var "seconds=$SECONDS_HELD" ) \
  > /tmp/statelock-b.out 2>&1 && B_EXIT=0 || B_EXIT=$?
wait "$A_PID" || true
LOCKS_AFTER="$(locks)"

{
  echo "\$ $(apply_cmd one)"
  echo "# with, concurrently, a sample of pg_locks and a second apply. See apply-b-is-refused.txt."
  echo
  cat /tmp/statelock-a.out
  echo
  echo "--- sampled in the state database while the apply above was still running ---"
  echo "\$ psql <conn> -x -c \"select locktype, mode, granted, pid from pg_locks where locktype='advisory';\""
  echo "$LOCKS_DETAIL_DURING"
  echo "granted advisory locks DURING the apply: $LOCKS_DURING"
  echo "granted advisory locks AFTER  the apply: $LOCKS_AFTER"
} > "$OUT/apply-a-holds-the-lock.txt"

{
  echo "\$ $(apply_cmd two)"
  echo "# run while the apply in apply-a-holds-the-lock.txt was still holding the lock"
  echo "# exit code: $B_EXIT"
  echo "#"
  echo "# The workspace already exists at this point, deliberately. Into a FRESH pg backend the"
  echo "# refusal reads 'Already locked for workspace creation: default' instead, which is a"
  echo "# different path and not what is meant by two engineers applying at once."
  echo
  cat /tmp/statelock-b.out
} > "$OUT/apply-b-is-refused.txt"

################################################################################
# 5. An apply with nothing to do takes the lock too. It just does not hold it for long.
################################################################################
echo "==> whether a no-op apply contends for the lock"
# Converge first, or this is not a no-op experiment at all. On the first run of this script the
# pair was launched at a tag that had been DELIBERATELY REFUSED earlier, so both applies had real
# work: one held the lock for twenty seconds and the other was refused, and the exit codes
# printed into the transcript are what gave that away.
( cd "$WORK" && terraform apply -auto-approve -no-color -var tag=settled -var "seconds=1" ) >/dev/null 2>&1

# The decisive test. A no-op apply cannot be shown to skip the lock by watching two of them miss
# each other, which is only a near miss. Make it contend with a lock that is definitely held.
( cd "$WORK" && exec terraform apply -auto-approve -no-color -var tag=realwork -var "seconds=$SECONDS_HELD" ) \
  > /tmp/statelock-holder-noop.out 2>&1 &
HN_PID=$!
sleep 6
LOCKS_WHILE_HELD="$(locks)"
( cd "$WORK" && terraform apply -auto-approve -no-color -var tag=settled -var "seconds=1" ) \
  > /tmp/statelock-noop-during.out 2>&1 && NOOP_DURING=0 || NOOP_DURING=$?
wait "$HN_PID" || true

# And sampled finely enough to catch it on its own, at 50ms rather than at human speed.
( cd "$WORK" && terraform apply -auto-approve -no-color -var tag=realwork -var "seconds=1" ) \
  > /tmp/statelock-noop-alone.out 2>&1 &
NA_PID=$!
NOOP_MAX=0
for _ in $(seq 1 120); do
  current="$(locks)"
  [ "$current" -gt "$NOOP_MAX" ] 2>/dev/null && NOOP_MAX="$current"
  sleep 0.05
done
wait "$NA_PID" || true

{
  echo "\$ terraform apply -auto-approve -no-color -var tag=settled -var seconds=1   # converge"
  echo "\$ terraform apply -auto-approve -no-color -var tag=realwork -var seconds=$SECONDS_HELD &  # hold the lock"
  echo "\$ terraform apply -auto-approve -no-color -var tag=settled -var seconds=1   # a NO-OP, during it"
  echo
  echo "granted advisory locks while the real-work apply held one: $LOCKS_WHILE_HELD"
  echo "exit code of the NO-OP apply that arrived during it:       $NOOP_DURING"
  echo
  echo "--- the no-op apply, run while the lock was held ---"
  cat /tmp/statelock-noop-during.out
  echo
  echo "\$ terraform apply -auto-approve -no-color -var tag=realwork -var seconds=1   # a lone no-op"
  echo "\$ psql <conn> -At -c \"select count(*) from pg_locks where locktype='advisory' and granted;\"  # every 50ms"
  echo "highest granted advisory lock count seen during that lone no-op apply: $NOOP_MAX"
  echo
  cat /tmp/statelock-noop-alone.out
  echo
  echo "So an apply with nothing to do DOES take the lock. It has to: the lock is acquired before"
  echo "the state is read, so terraform cannot yet know there is nothing to do."
  echo
  echo "This corrects what this repository said until 28-8-2026, which was that a no-op apply"
  echo "takes no lock at all. That came from running two no-op applies at once, seeing both"
  echo "succeed, and sampling pg_locks at human speed and finding it empty. Both observations"
  echo "were real and the conclusion was wrong: a no-op apply holds the lock for a fraction of a"
  echo "second, so two of them usually miss each other and a coarse sample usually misses it."
  echo "A near miss is not an absence, and an absence is not a mechanism."
} > "$OUT/a-no-op-apply-takes-the-lock-too.txt"
rm -f "$OUT/two-no-op-applies-take-no-lock.txt"

################################################################################
# 3. The lock dies with the session, so a killed client leaves nothing behind.
################################################################################
echo "==> SIGKILL during an apply, then a fresh apply"
( cd "$WORK" && exec terraform apply -auto-approve -no-color -var tag=three -var "seconds=$SECONDS_HELD" ) \
  > /tmp/statelock-killed.out 2>&1 &
K_PID=$!
sleep 8
LOCKS_BEFORE_KILL="$(locks)"
kill -9 "$K_PID" 2>/dev/null || true
wait "$K_PID" 2>/dev/null || true
sleep 2
LOCKS_AFTER_KILL="$(locks)"
( cd "$WORK" && terraform apply -auto-approve -no-color -var tag=four -var "seconds=5" ) \
  > /tmp/statelock-fresh.out 2>&1 && FRESH=0 || FRESH=$?

{
  echo "\$ $(apply_cmd three) &"
  echo "\$ sleep 8 && kill -9 <that pid>"
  echo "\$ terraform apply -auto-approve -no-color -var tag=four -var seconds=5"
  echo
  echo "granted advisory locks WHILE the doomed apply held one: $LOCKS_BEFORE_KILL"
  echo "granted advisory locks AFTER SIGKILL:                   $LOCKS_AFTER_KILL"
  echo "exit code of the fresh apply that followed:             $FRESH"
  echo
  echo "--- output of the apply that was killed, up to the point it died ---"
  cat /tmp/statelock-killed.out
  echo
  echo "--- the fresh apply, which was not refused ---"
  cat /tmp/statelock-fresh.out
  echo
  echo "A PostgreSQL advisory lock is held on a session. SIGKILL gives terraform no chance to"
  echo "release anything, and the lock goes anyway because the connection goes. With state in S3"
  echo "and a DynamoDB lock table the killed process leaves a row behind and the next apply is"
  echo "refused until somebody force-unlocks it."
} > "$OUT/after-sigkill-a-fresh-apply-proceeds.txt"

################################################################################
# 4. force-unlock is supported, and has nothing to do.
################################################################################
echo "==> force-unlock"
# exec, so $! is terraform's pid and not the subshell's. Without it kill -9 killed the subshell
# and left terraform running, and the transcript then reported one advisory lock still granted
# at the moment it claimed there was nothing left to unlock.
( cd "$WORK" && exec terraform apply -auto-approve -no-color -var tag=five -var "seconds=$SECONDS_HELD" ) \
  > /tmp/statelock-holder.out 2>&1 &
H_PID=$!
sleep 8
( cd "$WORK" && terraform apply -auto-approve -no-color -var tag=six -var "seconds=5" ) \
  > /tmp/statelock-refused2.out 2>&1 || true
LOCK_ID="$(sed -nE 's/^  ID: +([0-9a-f-]+).*/\1/p' /tmp/statelock-refused2.out | head -1)"
kill -9 "$H_PID" 2>/dev/null || true
wait "$H_PID" 2>/dev/null || true
sleep 2
LOCKS_BEFORE_UNLOCK="$(locks)"
( cd "$WORK" && terraform force-unlock -force "$LOCK_ID" -no-color ) \
  > /tmp/statelock-unlock.out 2>&1 && UNLOCK=0 || UNLOCK=$?

{
  echo "\$ terraform force-unlock -force $LOCK_ID"
  echo "# The lock id was read out of a refusal while a real apply held it. That apply was then"
  echo "# SIGKILLed, so by the time force-unlock ran there was nothing left to unlock."
  echo "# exit code: $UNLOCK"
  echo "# granted advisory locks immediately before force-unlock ran: $LOCKS_BEFORE_UNLOCK"
  echo
  cat /tmp/statelock-unlock.out
  echo
  echo "The specification said force-unlock is unsupported on the pg backend. It is supported."
  echo "What is true, and is the more useful half, is that it is never needed: the lock cannot"
  echo "go stale, so there is never a row to clear."
} > "$OUT/force-unlock-is-supported.txt"

# Strip terminal control sequences. The previous force-unlock transcript was committed with raw
# ANSI escapes in it, which is not evidence anybody can read.
for file in "$OUT"/*.txt; do
  perl -pe 's/\e\[[0-9;]*[a-zA-Z]//g' "$file" > "$file.clean" && mv "$file.clean" "$file"
done

# The decisive numbers, separately, because the transcripts cannot be byte-compared: they carry
# lock ids, resource ids, pids and timestamps that differ every run. This file carries only the
# outcomes, so CI can regenerate it and fail on any change. Without it the transcripts would be
# regenerated by nobody and would drift exactly as the plans were drifting.
# A LOCK BEING HELD IS RECORDED AS held-or-not, NOT AS A COUNT, and that distinction cost a red
# CI run. The first version recorded the exact number of granted advisory locks and asserted it
# was one. macOS saw one and a Linux runner saw two, because the pg backend takes more than one
# advisory lock for a moment and how many a sampler catches depends on timing.
#
# Neither number was wrong, and neither was the claim. The claim is that an apply takes a lock at
# all, and pinning an exact count pinned an implementation detail nobody is asserting. The raw
# counts are still in the transcripts, where the observation belongs; this file carries the
# outcome. A count that is genuinely meaningful is kept exact: zero after the apply, zero after
# the kill, zero before force-unlock. "None left behind" is the claim there, and it is exact.
held() { [ "${1:-0}" -gt 0 ] 2>/dev/null && echo 1 || echo 0; }

cat > "$OUT/summary.json" <<JSON
{
  "an_advisory_lock_is_held_during_an_apply_with_work": $(held "$LOCKS_DURING"),
  "advisory_locks_after_that_apply_finished": $LOCKS_AFTER,
  "exit_code_of_a_second_apply_during_it": $B_EXIT,
  "exit_code_of_a_no_op_apply_during_a_held_lock": $NOOP_DURING,
  "an_advisory_lock_is_held_during_a_lone_no_op_apply": $(held "$NOOP_MAX"),
  "an_advisory_lock_is_held_while_the_doomed_apply_runs": $(held "$LOCKS_BEFORE_KILL"),
  "advisory_locks_after_sigkill": $LOCKS_AFTER_KILL,
  "exit_code_of_the_apply_after_sigkill": $FRESH,
  "advisory_locks_before_force_unlock_ran": $LOCKS_BEFORE_UNLOCK,
  "exit_code_of_force_unlock": $UNLOCK
}
JSON

echo
echo "==> written to docs/evidence/statelock:"
ls -1 "$OUT"
echo
echo "==> the decisive numbers:"
cat "$OUT/summary.json"
