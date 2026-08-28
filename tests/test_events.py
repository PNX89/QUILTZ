"""The event path, and the exact difference between provisioned and exercised.

The specification bought this row on the promise of a path "exercised end to end on the
emulator". It cannot be, and finding out is what added the fifth entry to `boundary`. moto
creates the event source mapping, reports it enabled, and never fires it: a message on the
arrivals queue produced no invocation in twelve seconds.

So the claim is split, and both halves are checked.

  PROVISIONED  the queue, the topic, the subscription, the role, the policy, the function and
               the mapping, asserted to exist in the plan.
  EXERCISED    the handler, in a real container, publishing to the topic, with the notification
               read back off a subscribed queue.

The trigger is the part that is provisioned and not exercised, and the README says so.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import time

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
MODULE = REPO / "modules" / "events"
EVIDENCE = REPO / "docs" / "evidence" / "events"
ENDPOINT = "http://127.0.0.1:5599"


def test_the_module_provisions_every_piece_of_the_path() -> None:
    """Offline. Nine resources, read off the committed apply transcript."""
    text = (EVIDENCE / "terraform-provisioned-nine-resources.txt").read_text(encoding="utf-8")
    assert "Apply complete! Resources: 9 added, 0 changed, 0 destroyed." in text


def test_the_module_gives_the_lambda_a_different_endpoint_from_terraform() -> None:
    """Offline, and it is the defect that cost the most to find.

    The handler runs inside a container, so 127.0.0.1 there is the container's own loopback and
    reaches nothing: the first attempt returned EndpointConnectionError against
    http://127.0.0.1:5599/. Two variables, because it is genuinely two addresses.
    """
    source = (MODULE / "main.tf").read_text(encoding="utf-8")
    assert 'variable "endpoint_from_lambda"' in source
    assert "host.docker.internal" in source
    assert "EndpointConnectionError" in source, (
        "the reason for the second variable is not written down, so the next person to tidy it "
        "will merge them again"
    )
    assert "QUILTZ_ENDPOINT  = var.endpoint_from_lambda" in source


def test_the_handler_asks_for_nothing_it_was_not_granted() -> None:
    """Offline. The policy names the queue it reads and the topic it publishes to."""
    source = (MODULE / "main.tf").read_text(encoding="utf-8")
    assert "sqs:ReceiveMessage" in source and "sns:Publish" in source
    for over_broad in ('actions   = ["sqs:*"]', 'actions   = ["sns:*"]', 'resources = ["*"]'):
        assert over_broad not in source, f"the module grants {over_broad}"


@pytest.mark.container
def test_the_handler_runs_in_a_container_and_the_notification_arrives() -> None:
    """Needs Docker, because moto executes Lambda handlers in one. This is the one leg that does.

    Five of this repository's six legs are container-free and this is not one of them. Saying
    "container-free" without that qualifier would be exactly the over-reading the repository
    exists to refuse.
    """
    import boto3

    assert shutil.which("docker"), "the container marker is selected and docker is not present"
    kw = dict(
        endpoint_url=ENDPOINT,
        region_name="eu-west-1",
        aws_access_key_id="moto-demo",
        aws_secret_access_key="moto-demo",
    )
    lam = boto3.client("lambda", **kw)
    sqs = boto3.client("sqs", **kw)
    announced = f"{ENDPOINT}/123456789012/quiltz-announced"

    event = {
        "Records": [
            {
                "messageId": "m1",
                "body": "evidence-under-test",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:eu-west-1:123456789012:quiltz-arrivals",
            }
        ]
    }
    answer = lam.invoke(FunctionName="quiltz-consumer", Payload=json.dumps(event))
    payload = json.loads(answer["Payload"].read().decode())
    assert payload == {"published": 1}, f"the handler did not publish: {payload}"

    time.sleep(2)
    received = sqs.receive_message(
        QueueUrl=announced, MaxNumberOfMessages=10, WaitTimeSeconds=3
    ).get("Messages", [])
    assert received, "the notification never reached the subscribed queue"
    bodies = [json.loads(json.loads(m["Body"])["Message"]) for m in received]
    assert any(b["body"] == "evidence-under-test" for b in bodies), bodies

    # Deleted, not merely received. A received message is invisible rather than gone and comes
    # back when its visibility timeout expires, which is how this test made the next one fail.
    for message in received:
        sqs.delete_message(QueueUrl=announced, ReceiptHandle=message["ReceiptHandle"])


@pytest.mark.container
def test_a_message_on_the_queue_reaches_the_topic_with_no_manual_invocation() -> None:
    """The trigger fires. This is the assertion that made a false boundary limit collapse.

    It was written the other way round first, asserting that moto provisions the mapping and
    never fires it, because a message on the arrivals queue had produced nothing in twelve
    seconds. That absence had a different cause: the handler was being invoked and dying,
    unable to reach the emulator at 127.0.0.1 from inside its container. Given
    host.docker.internal it works, and an announcement arrives in about two seconds with
    nothing invoked by hand.
    """
    import boto3

    kw = dict(
        endpoint_url=ENDPOINT,
        region_name="eu-west-1",
        aws_access_key_id="moto-demo",
        aws_secret_access_key="moto-demo",
    )
    lam = boto3.client("lambda", **kw)
    sqs = boto3.client("sqs", **kw)
    announced = f"{ENDPOINT}/123456789012/quiltz-announced"
    arrivals = f"{ENDPOINT}/123456789012/quiltz-arrivals"

    # The FULL ARN, not the bare name. moto matches FunctionName against the ARN only, so
    # querying by name returns an empty list while the mapping plainly exists and is Enabled.
    # Real AWS accepts either form.
    arn = "arn:aws:lambda:eu-west-1:123456789012:function:quiltz-consumer"
    mappings = lam.list_event_source_mappings(FunctionName=arn)["EventSourceMappings"]
    assert mappings, "the mapping is not provisioned at all"
    assert mappings[0]["State"] in {"Enabled", "Creating"}
    assert mappings[0]["EventSourceArn"].endswith("quiltz-arrivals")

    def drain() -> int:
        """Receive AND DELETE, returning how many were removed.

        Receiving alone makes a message invisible rather than gone, so it returns when the
        visibility timeout expires. An earlier version drained by receiving and was then failed
        by a message the previous test had left in flight. Receiving is not removing.
        """
        removed = 0
        for _ in range(20):
            batch = sqs.receive_message(
                QueueUrl=announced, MaxNumberOfMessages=10, WaitTimeSeconds=1
            ).get("Messages", [])
            if not batch:
                return removed
            for message in batch:
                sqs.delete_message(QueueUrl=announced, ReceiptHandle=message["ReceiptHandle"])
                removed += 1
        return removed

    drain()
    sqs.send_message(QueueUrl=arrivals, MessageBody="triggered-by-the-mapping")

    for _ in range(10):
        time.sleep(2)
        batch = sqs.receive_message(
            QueueUrl=announced, MaxNumberOfMessages=10, WaitTimeSeconds=1
        ).get("Messages", [])
        if batch:
            bodies = [json.loads(json.loads(m["Body"])["Message"]) for m in batch]
            for message in batch:
                sqs.delete_message(QueueUrl=announced, ReceiptHandle=message["ReceiptHandle"])
            assert any(b["body"] == "triggered-by-the-mapping" for b in bodies), bodies
            return
    raise AssertionError(
        "twenty seconds and nothing reached the topic. Before concluding the mapping does not "
        "fire, check that the handler can reach the emulator: inside the container 127.0.0.1 is "
        "the container, and an invocation that dies looks exactly like one that never happened."
    )
