
"""
Smart Collar MQTT Router

Supported storage modes:
    mongo  - MongoDB only
    dynamo - DynamoDB Local only
    all    - Both databases
"""

import os
import json
import logging

from datetime import datetime, timezone
from decimal import Decimal

import paho.mqtt.client as mqtt

from pymongo import MongoClient, ASCENDING, DESCENDING

import boto3


# CONFIG

DEVICE_ID = os.getenv("DEVICE_ID", "collar-001")
MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MONGO_HOST = os.getenv("MONGO_HOST", "collar-mongo")

DYNAMO_ENDPOINT = os.getenv(
    "DYNAMO_ENDPOINT",
    "http://collar-dynamo:8000")

DYNAMO_TABLE = os.getenv(
    "DYNAMO_TABLE",
    "SmartCollarTelemetry")

STORAGE_MODE = os.getenv(
    "STORAGE_MODE",
    "mongo").lower()

VALID_MODES = ["mongo", "dynamo", "all"]

if STORAGE_MODE not in VALID_MODES:
    raise ValueError("STORAGE_MODE must be: mongo, dynamo, or all")

USE_MONGO = STORAGE_MODE in ["mongo", "all"]
USE_DYNAMO = STORAGE_MODE in ["dynamo", "all"]

RETENTION_SECONDS = 3 * 24 * 60 * 60

ALLOWED_TOPICS = ["environment", "motion", "location", "battery"]


# LOGS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s")

logging.info("Storage mode: %s", STORAGE_MODE)


# MongoDB

mongo_collection = None

if USE_MONGO:
    logging.info("Connecting to MongoDB...")

    mongo_client = MongoClient(
        host=MONGO_HOST,
        port=27017,
        username=os.environ["MONGO_ROOT_USER"],
        password=os.environ["MONGO_ROOT_PASSWORD"],
        authSource="admin",
        serverSelectionTimeoutMS=5000)

    mongo_client.admin.command("ping")

    mongo_collection = mongo_client["smartcollar"]["telemetry"]

    mongo_collection.create_index([
        ("device_id", ASCENDING),
        ("received_at", DESCENDING)])

    # Retain telemetry for three days.
    mongo_collection.create_index(
        "received_at",
        expireAfterSeconds=RETENTION_SECONDS)

    logging.info("MongoDB connected")


# DynamoDB

dynamo_table = None

if USE_DYNAMO:
    logging.info("Connecting to DynamoDB Local...")

    dynamo_resource = boto3.resource(
        "dynamodb",
        endpoint_url=DYNAMO_ENDPOINT,
        region_name="eu-west-1",
        aws_access_key_id="local",
        aws_secret_access_key="local")

    dynamo_table = dynamo_resource.Table(DYNAMO_TABLE)
    dynamo_table.load()
    logging.info("DynamoDB Local connected")


def convert_for_dynamo(value):

    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, dict):
        return {
            key: convert_for_dynamo(item)
            for key, item in value.items()}

    if isinstance(value, list):
        return [
            convert_for_dynamo(item)
            for item in value]

    return value


# MQTT callbacks

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties
):

    if reason_code.is_failure:

        logging.error(
            "MQTT connection refused: %s",
            reason_code
        )

        return

    topic = f"smartCollar/{DEVICE_ID}/+"

    client.subscribe(topic, qos=1)

    logging.info(
        "Connected to Mosquitto. Subscribed to %s",
        topic
    )


# MQTT process

def on_message(client, userdata, message):

    try:
        parts = message.topic.split("/")

        # topic: smartCollar/collar-001/environment

        if len(parts) != 3:
            return

        if parts[0] != "smartCollar":
            return

        device_id = parts[1]
        data_type = parts[2]

        if device_id != DEVICE_ID:
            return

        if data_type not in ALLOWED_TOPICS:
            return

        # MQTT JSON -> dict
        payload = json.loads(
            message.payload.decode("utf-8"))

        if not isinstance(payload, dict):
            logging.warning("Invalid JSON object")
            return

        received_at = datetime.now(timezone.utc)
        timestamp = received_at.isoformat(
            timespec="microseconds")
	
	# MongoDB
        if USE_MONGO:
            try:
                mongo_record = {
                    "device_id": device_id,
                    "type": data_type,
                    "timestamp": timestamp,
                    "received_at": received_at,
                    "payload": payload}

                mongo_collection.insert_one(mongo_record)

                logging.info(
                    "MONGO OK | %s",
                    data_type)

            except Exception:
                logging.exception(
                    "MONGO ERROR | %s",
                    data_type)

        # DynamoDB
        if USE_DYNAMO:
            try:
                dynamo_record = {
                    "device_id": device_id,
                    "timestamp": timestamp,
                    "type": data_type,
                    "payload": convert_for_dynamo(payload),

                    # 3 days TTL
                    "expires_at": (
                        int(received_at.timestamp())
                        + RETENTION_SECONDS)}

                dynamo_table.put_item(
                    Item=dynamo_record)

                logging.info(
                    "DYNAMO OK | %s",
                    data_type)

            except Exception:
                logging.exception(
                    "DYNAMO ERROR | %s",
                    data_type)

    except Exception:
        logging.exception(
            "Failed to process MQTT message")


# mqtt client

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id="smartcollar-router")

client.username_pw_set(
    os.environ["MQTT_USER"],
    os.environ["MQTT_PASSWORD"])

client.on_connect = on_connect
client.on_message = on_message


# start worker

logging.info(
    "Connecting to MQTT broker %s:1883",
    MQTT_HOST)

client.connect(
    MQTT_HOST,
    port=1883,
    keepalive=60
)

client.loop_forever()



