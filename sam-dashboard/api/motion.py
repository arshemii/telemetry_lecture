"""Lambda: calculate motion averages over the latest two minutes."""

import json
import logging
from statistics import mean

from data_access import get_measurements


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):

    device_id = event["pathParameters"]["device_id"]

    try:

        # Retrieve the latest two minutes of motion data.
        records = get_measurements(
            device_id=device_id,
            data_type="motion",
            minutes=2
        )

        # Collect speed and acceleration measurements.
        speeds = []
        accelerations = []

        for record in records:

            payload = record.get("payload", {})

            if payload.get("averageSpeed") is not None:
                speeds.append(
                    float(payload["averageSpeed"])
                )

            if payload.get("averageAcceleration") is not None:
                accelerations.append(
                    float(payload["averageAcceleration"])
                )

        # Calculate averages.
        average_speed = (
            round(mean(speeds), 3)
            if speeds else None
        )

        average_acceleration = (
            round(mean(accelerations), 3)
            if accelerations else None
        )

        result = {
            "device_id": device_id,
            "window_minutes": 2,
            "samples": len(records),
            "average_speed": average_speed,
            "average_acceleration": average_acceleration
        }

        logger.info("Motion analysis completed: %s", result)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(result)
        }

    except Exception:

        logger.exception("Motion analysis failed")

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "error": "Motion analysis failed"
            })
        }
