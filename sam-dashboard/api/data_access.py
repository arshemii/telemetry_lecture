"""Read Smart Collar telemetry from DynamoDB Local."""

import os
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key, Attr


DYNAMO_ENDPOINT = os.getenv(
    "DYNAMO_ENDPOINT",
    "http://collar-dynamo:8000"
)

DYNAMO_TABLE = os.getenv(
    "DYNAMO_TABLE",
    "SmartCollarTelemetry"
)


# Create the DynamoDB connection.
dynamodb = boto3.resource(
    "dynamodb",
    endpoint_url=DYNAMO_ENDPOINT,
    region_name="eu-west-1",
    aws_access_key_id="local",
    aws_secret_access_key="local"
)

table = dynamodb.Table(DYNAMO_TABLE)


def get_measurements(device_id, data_type, minutes):
    """
    Retrieve measurements for one device and sensor category,
    within the requested number of minutes.
    """

    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes)

    # Our DynamoDB timestamps use UTC ISO 8601 strings.
    start_time = start.isoformat(timespec="microseconds")
    end_time = now.isoformat(timespec="microseconds")

    records = []
    last_key = None

    while True:

        query = {
            "KeyConditionExpression": (
                Key("device_id").eq(device_id)
                & Key("timestamp").between(start_time, end_time)
            ),
            "FilterExpression": Attr("type").eq(data_type),
            "ScanIndexForward": True
        }

        if last_key:
            query["ExclusiveStartKey"] = last_key

        response = table.query(**query)

        records.extend(response.get("Items", []))

        # DynamoDB may return results in multiple pages.
        last_key = response.get("LastEvaluatedKey")

        if not last_key:
            break

    return records
