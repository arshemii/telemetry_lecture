"""Simulated Smart Collar MCU with independent MQTT publishing frequencies."""

import json
import logging
import os
import random
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


# ==========================================================
# 1. CONFIGURATION
# ==========================================================

BROKER = os.getenv("MQTT_HOST", "mosquitto")
DEVICE_ID = os.getenv("DEVICE_ID", "collar-001")

MQTT_PORT = 1883

# Publishing intervals in seconds
INTERVALS = {
    "motion": 1.8,
    "environment": 60.0,
    "location": 30.0,
}

# Battery publishing rules
BATTERY_THRESHOLD = 20.0
BATTERY_NORMAL_INTERVAL = 60.0
BATTERY_LOW_INTERVAL = 30.0

# Starting battery level (configurable for testing)
battery = float(os.getenv("SIM_INITIAL_BATTERY", "95.0"))

if not 0 <= battery <= 100:
    raise ValueError("SIM_INITIAL_BATTERY must be between 0 and 100")


# ==========================================================
# 2. LOGGING
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

connected = threading.Event()


# ==========================================================
# 3. MQTT CALLBACKS
# ==========================================================

def on_connect(client, userdata, flags, reason_code, properties):

    if reason_code.is_failure:
        logging.error(
            "MQTT authentication/connection rejected: %s",
            reason_code
        )
        connected.clear()

    else:
        connected.set()
        logging.info(
            "MCU connected to Mosquitto at %s:%s",
            BROKER,
            MQTT_PORT
        )


def on_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties
):

    connected.clear()

    logging.warning(
        "MCU disconnected from Mosquitto: %s",
        reason_code
    )


# ==========================================================
# 4. GENERATE SIMULATED SENSOR DATA
# ==========================================================

def generate_sample(kind):
    """
    Generate one simulated measurement for a specific topic.
    """

    global battery

    if kind == "motion":

        return {
            "averageSpeed": round(random.uniform(0, 3), 2),
            "averageAcceleration": round(random.uniform(0, 2), 2),
            "numberOfJumps": random.randint(0, 3),
            "highAccelerationDetected": random.choice(
                [False, False, False, True]
            ),
        }

    elif kind == "environment":

        return {
            "temperature": round(random.uniform(18, 32), 1),
            "co2": random.randint(420, 1100),
            "moisture": round(random.uniform(30, 80), 1),
        }

    elif kind == "location":

        return {
            "latitude": round(
                45.4642 + random.uniform(-0.001, 0.001),
                6
            ),
            "longitude": round(
                9.1900 + random.uniform(-0.001, 0.001),
                6
            ),
        }

    elif kind == "battery":

        # Artificial battery consumption for simulation.
        # Decrease by 0.02 percentage points per battery update.
        battery = max(0.0, battery - 0.02)

        return {
            "battery": round(battery, 2)
        }

    raise ValueError(f"Unknown telemetry type: {kind}")


# ==========================================================
# 5. DETERMINE PUBLISHING INTERVAL
# ==========================================================

def get_interval(kind):
    """
    Return the correct interval for each MQTT topic.
    """

    if kind == "battery":

        if battery <= BATTERY_THRESHOLD:
            return BATTERY_LOW_INTERVAL

        return BATTERY_NORMAL_INTERVAL

    return INTERVALS[kind]


# ==========================================================
# 6. PUBLISH A SINGLE MQTT MESSAGE
# ==========================================================

def publish_sample(client, kind):

    # Generate values for this telemetry category.
    fields = generate_sample(kind)

    # Each message gets its own timestamp.
    timestamp = datetime.now(timezone.utc).isoformat()

    topic = f"smartCollar/{DEVICE_ID}/{kind}"

    payload = {
        "timestamp": timestamp,
        **fields
    }

    # Send through MQTT.
    info = client.publish(
        topic,
        json.dumps(payload),
        qos=1
    )

    if info.rc == mqtt.MQTT_ERR_SUCCESS:

        logging.info(
            "MQTT publish queued | %s | %s",
            topic,
            payload
        )

    else:

        logging.error(
            "MQTT publish failed | %s | rc=%s",
            topic,
            info.rc
        )


# ==========================================================
# 7. CONFIGURE MQTT CLIENT
# ==========================================================

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"{DEVICE_ID}-simulator"
)

client.username_pw_set(
    os.environ["MQTT_USER"],
    os.environ["MQTT_PASSWORD"]
)

client.on_connect = on_connect
client.on_disconnect = on_disconnect


# ==========================================================
# 8. CONNECT TO MOSQUITTO
# ==========================================================

logging.info(
    "Connecting simulated MCU to %s:%s",
    BROKER,
    MQTT_PORT
)

client.connect(
    BROKER,
    port=MQTT_PORT,
    keepalive=60
)

# MQTT network processing runs in a separate thread.
client.loop_start()


# ==========================================================
# 9. INDEPENDENT PUBLISHING SCHEDULER
# ==========================================================

TOPICS = [
    "motion",
    "environment",
    "location",
    "battery",
]

# Stores the next scheduled publishing time for each topic.
next_publish = None


try:

    while True:

        # If MQTT is disconnected, do not generate messages.
        if not connected.is_set():

            # Reset schedules when reconnecting.
            next_publish = None

            connected.wait(timeout=1.0)
            continue

        # Initialize independent timers after connecting.
        if next_publish is None:

            now = time.monotonic()

            next_publish = {
                kind: now
                for kind in TOPICS
            }

            logging.info(
                "Telemetry scheduling started"
            )

        now = time.monotonic()

        # Check the timer of each topic independently.
        for kind in TOPICS:

            if now >= next_publish[kind]:

                # Publish only the category whose timer expired.
                publish_sample(client, kind)

                # Calculate the next publishing time.
                interval = get_interval(kind)

                next_publish[kind] = (
                    time.monotonic() + interval
                )

        # Sleep until the next check, without busy-waiting.
        remaining = min(next_publish.values()) - time.monotonic()

        time.sleep(
            max(0.01, min(remaining, 0.5))
        )


except KeyboardInterrupt:

    logging.info("Stopping simulated MCU")


finally:

    client.disconnect()
    client.loop_stop()

    logging.info("Simulated MCU stopped")
