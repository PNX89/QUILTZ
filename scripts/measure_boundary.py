#!/usr/bin/env python3
"""Measure two of the four limits in quiltz.boundary, and write the transcripts.

Run from the repository root:  uv run scripts/measure_boundary.py

This exists because the boundary entry it feeds was wrong. It said the emulator accepts a
policy document and stores it, and cannot tell you whether the policy would permit or deny.
The first half is true by default and the second half is not true at all: moto ships an opt-in
access control mode, and with it enabled a user carrying an explicit Deny is refused.

The transcript records its own commands, for the reason the Ansible ones do: a captured output
that does not say how it was produced cannot support a claim about how it was produced.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import socket
import subprocess
import sys
import time
from typing import Any

import boto3
import botocore.exceptions

REGION = "eu-west-1"
OUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "evidence" / "iam"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


@contextlib.contextmanager
def emulator(no_auth_actions: int | None) -> Any:
    """A moto_server of its own, so the setting under test cannot leak into other tests.

    `no_auth_actions` is moto's INITIAL_NO_AUTH_ACTION_COUNT: the number of requests served
    without checking credentials before enforcement begins. It exists because enforcement is
    otherwise unreachable, there being no way to create the first user without permission to
    create it. That bootstrap window is itself part of why this is a test affordance rather
    than an account model.
    """
    import os

    port = free_port()
    env = dict(os.environ)
    if no_auth_actions is None:
        env.pop("INITIAL_NO_AUTH_ACTION_COUNT", None)
    else:
        env["INITIAL_NO_AUTH_ACTION_COUNT"] = str(no_auth_actions)
    process = subprocess.Popen(
        [sys.executable, "-m", "moto.server", "-p", str(port), "--host", "127.0.0.1"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    endpoint = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            with (
                contextlib.suppress(OSError),
                socket.create_connection(("127.0.0.1", port), timeout=0.2),
            ):
                break
            time.sleep(0.1)
        else:  # pragma: no cover
            raise RuntimeError("the emulator never came up")
        yield endpoint
    finally:
        process.terminate()
        process.wait(timeout=10)


def client(service: str, endpoint: str, key: str = "test", secret: str = "test") -> Any:
    return boto3.client(
        service,
        endpoint_url=endpoint,
        region_name=REGION,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
    )


DENY_ALL = {
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Deny", "Action": "*", "Resource": "*"}],
}


# What an authorization refusal looks like coming back. moto answers one with HTTP 403, and for
# SQS it puts the literal string 403 in the error Code where IAM and S3 put AccessDenied, so the
# status is the test that holds across services and the codes are here for anything that refuses
# with a name and a status this does not expect.
REFUSAL_CODES = frozenset({"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"})


def allowed(call: Any) -> bool:
    """Whether a call went through, with a policy refusal told apart from every other failure.

    ANY ClientError used to count as a refusal, and `not allowed(...)` is how measure() records
    that a policy denied something. So a plain 400 from the service, an InvalidAttributeName on
    the queue the policy DOES permit for instance, was written down as the Resource element
    being evaluated and honoured. The probe gave the right answer and could not tell you why.

    That is the reasoning boundary.py's docstring exists to warn against: an absence is not a
    mechanism, and the one probe in this repository allowed to conclude from a failure was the
    one that never asked what the failure was. Anything that is not a refusal is re-raised, so
    it stops the measurement rather than being scored as a denial.
    """
    try:
        call()
    except botocore.exceptions.ClientError as refused:
        response = refused.response
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = response.get("Error", {}).get("Code")
        if status == 403 or code in REFUSAL_CODES:
            return False
        raise
    return True


def measure() -> dict[str, bool]:
    """The three facts. Returned as data so a test can assert on them without re-reading prose."""
    results: dict[str, bool] = {}

    # 1. Default. No enforcement at all.
    with emulator(None) as endpoint:
        iam = client("iam", endpoint)
        iam.create_user(UserName="denied")
        iam.put_user_policy(
            UserName="denied", PolicyName="deny", PolicyDocument=json.dumps(DENY_ALL)
        )
        key = iam.create_access_key(UserName="denied")["AccessKey"]
        s3 = client("s3", endpoint, key["AccessKeyId"], key["SecretAccessKey"])
        results["by_default_a_deny_all_user_is_allowed"] = allowed(
            lambda: s3.create_bucket(
                Bucket="made-by-a-denied-user",
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
        )

    # 2. Enforcement on. Action and Resource are both honoured.
    with emulator(5) as endpoint:
        iam, sqs = client("iam", endpoint), client("sqs", endpoint)
        one = sqs.create_queue(QueueName="allowed-queue")["QueueUrl"]
        two = sqs.create_queue(QueueName="other-queue")["QueueUrl"]
        scoped = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "sqs:*",
                    "Resource": f"arn:aws:sqs:{REGION}:123456789012:allowed-queue",
                }
            ],
        }
        iam.create_user(UserName="scoped")
        iam.put_user_policy(
            UserName="scoped", PolicyName="one-queue", PolicyDocument=json.dumps(scoped)
        )
        key = iam.create_access_key(UserName="scoped")["AccessKey"]
        caller = client("sqs", endpoint, key["AccessKeyId"], key["SecretAccessKey"])
        # The SAME operation on both queues, so the resource is the only thing that varies.
        # An earlier version of this probe used create_bucket for one and list for the other,
        # which would have credited the resource element for a refusal about the action.
        results["with_enforcement_the_named_resource_is_allowed"] = allowed(
            lambda: caller.get_queue_attributes(QueueUrl=one, AttributeNames=["QueueArn"])
        )
        results["with_enforcement_an_unnamed_resource_is_refused"] = not allowed(
            lambda: caller.get_queue_attributes(QueueUrl=two, AttributeNames=["QueueArn"])
        )

    # 3. Enforcement on. The Condition is ignored.
    with emulator(4) as endpoint:
        iam, sqs = client("iam", endpoint), client("sqs", endpoint)
        url = sqs.create_queue(QueueName="q")["QueueUrl"]
        impossible = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "sqs:*",
                    "Resource": "*",
                    "Condition": {"IpAddress": {"aws:SourceIp": "203.0.113.7/32"}},
                }
            ],
        }
        iam.create_user(UserName="cond")
        iam.put_user_policy(
            UserName="cond", PolicyName="impossible", PolicyDocument=json.dumps(impossible)
        )
        key = iam.create_access_key(UserName="cond")["AccessKey"]
        caller = client("sqs", endpoint, key["AccessKeyId"], key["SecretAccessKey"])
        results["with_enforcement_an_impossible_condition_is_ignored"] = allowed(
            lambda: caller.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])
        )

    return results


# How many are asked for. A number rather than a literal in the loop, because the transcript and
# the guards below both need to know whether the count that came back is a limit the emulator
# imposed or simply the point at which this stopped asking.
ATTEMPTS = 130


def measure_quotas() -> int:
    """How many buckets the emulator will make before it objects. AWS stops at 100.

    Measured rather than asserted, because "every quota is infinite here" is the kind of
    sentence that sounds obviously true and is checked by nobody.

    THE REFUSAL IS CAUGHT, and that is the difference between this returning a measurement and
    returning its own loop bound. `made` was incremented only after a successful create_bucket
    and nothing caught the error, so the single return was reachable only when every call
    succeeded: the function could answer ATTEMPTS or raise, and never the number its name
    promises. Both guards that print "the emulator refused after N buckets", the one in main()
    and the one in tests/test_iam_boundary.py, were unreachable as written.
    """
    with emulator(None) as endpoint:
        s3 = client("s3", endpoint)
        made = 0
        for number in range(1, ATTEMPTS + 1):
            try:
                s3.create_bucket(
                    Bucket=f"quota-probe-{number:03d}",
                    CreateBucketConfiguration={"LocationConstraint": REGION},
                )
            except botocore.exceptions.ClientError:
                break
            made += 1
    return made


EXPECTED = {
    "by_default_a_deny_all_user_is_allowed": True,
    "with_enforcement_the_named_resource_is_allowed": True,
    "with_enforcement_an_unnamed_resource_is_refused": True,
    "with_enforcement_an_impossible_condition_is_ignored": True,
}


def main() -> int:
    import moto

    results = measure()
    buckets = measure_quotas()
    # The transcript has to say which of the two numbers this is. It reads as a measurement of
    # the emulator either way, and only one of the two readings is true on any given run.
    stopped_by = "without a single refusal" if buckets == ATTEMPTS else "before the first refusal"
    lines = [
        "$ uv run scripts/measure_boundary.py",
        f"moto {moto.__version__}, boto3 {boto3.__version__}",
        "",
        "Each server below is started by this script with the setting named beside it, so the",
        "setting cannot leak between measurements.",
        "",
        "1. INITIAL_NO_AUTH_ACTION_COUNT unset, which is the default and the mode this",
        "   repository's own suite runs in.",
        "   A user carrying an explicit Deny on every action and every resource created a",
        f"   bucket: {results['by_default_a_deny_all_user_is_allowed']}",
        "   The policy is stored and reads back correctly. It is simply never consulted.",
        "",
        "2. INITIAL_NO_AUTH_ACTION_COUNT=5. Enforcement is on after the bootstrap window.",
        "   Policy: Allow sqs:* on arn:aws:sqs:eu-west-1:123456789012:allowed-queue only.",
        "   The same operation, GetQueueAttributes, against each of two existing queues:",
        f"     allowed-queue  allowed: {results['with_enforcement_the_named_resource_is_allowed']}",
        f"     other-queue    refused: "
        f"{results['with_enforcement_an_unnamed_resource_is_refused']}",
        "   So Action and Resource are both evaluated. moto's own access_control.py carries a",
        "   module-level TODO saying Resource is unsupported; measured here, it is supported.",
        "",
        "3. INITIAL_NO_AUTH_ACTION_COUNT=4. Enforcement on, and a Condition that cannot hold.",
        "   Policy: Allow sqs:* on * only when aws:SourceIp is 203.0.113.7/32.",
        "   The caller's address is not that. The call was allowed anyway:",
        f"     condition ignored: {results['with_enforcement_an_impossible_condition_is_ignored']}",
        "",
        "That last line is the boundary. Conditions are how a policy narrows itself, by source",
        "address, by MFA, by tag, by VPC endpoint. Here they are absent from the decision, so a",
        "policy that is only safe because of its condition passes exactly as one without it.",
        "",
        "4. Service quotas, on a default server.",
        f"   Buckets created one after another {stopped_by}: {buckets}",
        "   An AWS account stops at 100 by default and needs a quota increase for more. Nothing",
        "   here counts, so no test in this repository can ever meet a limit that a real account",
        "   would meet.",
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "what-moto-evaluates.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if buckets < 101:
        print(
            f"\nthe emulator refused after {buckets} buckets, so it does enforce a quota",
            file=sys.stderr,
        )
        return 1
    if results != EXPECTED:
        print(f"\nMEASURED {results}\nEXPECTED {EXPECTED}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
