"""Read a batch off the queue and announce it on the topic.

Deliberately small. The point of this repository is the module set and the emulator boundary,
not the function, and a handler with logic in it would invite claims about a runtime nobody
here has operated.
"""

import json
import os

import boto3


def handler(event, context):
    endpoint = os.environ.get("QUILTZ_ENDPOINT")
    sns = boto3.client("sns", endpoint_url=endpoint, region_name=os.environ["AWS_REGION"])
    records = event.get("Records", [])
    for record in records:
        sns.publish(
            TopicArn=os.environ["QUILTZ_TOPIC_ARN"],
            Subject="evidence-arrived",
            Message=json.dumps({"body": record.get("body"), "source": "quiltz-lambda"}),
        )
    return {"published": len(records)}
