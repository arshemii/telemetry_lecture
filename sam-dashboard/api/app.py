import os
import json
import logging

from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key


logger = logging.getLogger()
logger.setLevel(logging.INFO)

DYNAMO_ENDPOINT = os.environ["DYNAMO_ENDPOINT"]
DYNAMO_TABLE = os.environ["DYNAMO_TABLE"]

def json_converter(value):
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    raise TypeError("Unsupported JSON data type")


def handler(event, context):
    device_id = event["pathParameters"]["device_id"]

    logger.info("Request received for device: %s", device_id)

    try:
        dynamodb = boto3.resource("dynamodb",
            endpoint_url=DYNAMO_ENDPOINT,
            region_name="eu-west-1",
            aws_access_key_id="local",
            aws_secret_access_key="local")

        table = dynamodb.Table(DYNAMO_TABLE)
        response = table.query(
            KeyConditionExpression=Key("device_id").eq(device_id),
            ScanIndexForward=False,
            Limit=1)

        records = response.get("Items", [])
        latest = records[0] if records else None

        logger.info("DynamoDB query completed")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "device_id": device_id,
                    "latest": latest},
                default=json_converter)}

    except Exception:
        logger.exception("Unable to retrieve telemetry")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json"},

            "body": json.dumps(
                {"error": "Unable to retrieve telemetry"})}
