"""Read Smart Collar telemetry from MQTT; store it in MongoDB for three days."""
import json
import logging
import os
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from pymongo import MongoClient, ASCENDING, DESCENDING

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
DEVICE_ID = os.getenv("DEVICE_ID", "collar-001")
BROKER = os.getenv("MQTT_HOST", "mosquitto")
DB_HOST = os.getenv("MONGO_HOST", "collar-mongo")
CATEGORIES = {"environment", "motion", "location", "battery"}

mongo = MongoClient(
    host=DB_HOST,
    port=27017,
    username=os.environ["MONGO_ROOT_USER"],
    password=os.environ["MONGO_ROOT_PASSWORD"],
    authSource="admin",
    serverSelectionTimeoutMS=5000,
)
mongo.admin.command("ping")
logging.info("MongoDB connection OK (%s:27017)", DB_HOST)
telemetry = mongo["smartcollar"]["telemetry"]
telemetry.create_index([("device_id", ASCENDING), ("received_at", DESCENDING)])
telemetry.create_index("received_at", expireAfterSeconds=3 * 24 * 60 * 60)
logging.info("MongoDB TTL index configured: 3 days")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logging.error("MQTT connection refused: %s", reason_code)
        return
    topic_filter = f"smartCollar/{DEVICE_ID}/+"
    client.subscribe(topic_filter, qos=1)
    logging.info("MQTT connected and subscribed to %s", topic_filter)


def on_message(client, userdata, message):
    try:
        parts = message.topic.split("/")
        if len(parts) != 3 or parts[2] not in CATEGORIES or parts[1] != DEVICE_ID:
            return
        payload = json.loads(message.payload.decode("utf-8"))
        if not isinstance(payload, dict):
            logging.warning("Ignoring non-object JSON on %s", message.topic)
            return
        telemetry.insert_one({
            "device_id": DEVICE_ID,
            "type": parts[2],
            "received_at": datetime.now(timezone.utc),
            "payload": payload,
        })
        logging.info("Stored %s for %s", parts[2], DEVICE_ID)
    except (ValueError, UnicodeDecodeError):
        logging.warning("Ignoring invalid JSON on %s", message.topic)
    except Exception:
        logging.exception("Unable to store message from %s", message.topic)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smartcollar-db-worker")
client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASSWORD"])
client.on_connect = on_connect
client.on_message = on_message
logging.info("Connecting to MQTT broker %s:1883", BROKER)
client.connect(BROKER, 1883, 60)
client.loop_forever()
