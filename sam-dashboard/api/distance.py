"""Lambda: calculate traveled-distance statistics using GNSS."""

import json
import logging
import math
from datetime import datetime

from data_access import get_measurements


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate distance in meters between two GPS coordinates.
    """

    EARTH_RADIUS = 6371000  # meters

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    delta_lat = lat2 - lat1
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    a = min(1.0, max(0.0, a))

    return (
        2 * EARTH_RADIUS
        * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    )


def handler(event, context):

    device_id = event["pathParameters"]["device_id"]

    try:

        # Retrieve up to two hours of location data.
        records = get_measurements(
            device_id=device_id,
            data_type="location",
            minutes=120
        )

        # Extract valid GNSS positions.
        points = []

        for record in records:

            payload = record.get("payload", {})

            lat = payload.get("latitude")
            lon = payload.get("longitude")

            if lat is None or lon is None:
                continue

            lat = float(lat)
            lon = float(lon)

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            points.append({
                "timestamp": record["timestamp"],
                "latitude": lat,
                "longitude": lon
            })

        # We need at least two points to calculate distance.
        if len(points) < 2:

            result = {
                "device_id": device_id,
                "window_hours": 2,
                "points_used": len(points),
                "status": "insufficient_data",
                "total_distance_m": None,
                "average_segment_distance_m": None,
                "average_speed_kmh": None
            }

        else:

            # Calculate distance between consecutive points.
            distances = []

            for index in range(1, len(points)):

                previous = points[index - 1]
                current = points[index]

                distance = haversine(
                    previous["latitude"],
                    previous["longitude"],
                    current["latitude"],
                    current["longitude"]
                )

                distances.append(distance)

            total_distance = sum(distances)

            average_segment_distance = (
                total_distance / len(distances)
            )

            # Calculate actual time covered by measurements.
            first_time = datetime.fromisoformat(
                points[0]["timestamp"]
            )

            last_time = datetime.fromisoformat(
                points[-1]["timestamp"]
            )

            elapsed_seconds = (
                last_time - first_time
            ).total_seconds()

            # Average speed over the available measurements.
            average_speed_kmh = (
                (total_distance / elapsed_seconds) * 3.6
                if elapsed_seconds > 0 else None
            )

            result = {
                "device_id": device_id,
                "window_hours": 2,
                "points_used": len(points),
                "status": "ok",
                "actual_duration_minutes": round(
                    elapsed_seconds / 60, 2
                ),
                "total_distance_m": round(
                    total_distance, 2
                ),
                "average_segment_distance_m": round(
                    average_segment_distance, 2
                ),
                "average_speed_kmh": (
                    round(average_speed_kmh, 2)
                    if average_speed_kmh is not None
                    else None
                )
            }

        logger.info("Distance analysis completed: %s", result)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(result)
        }

    except Exception:

        logger.exception("Distance analysis failed")

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "error": "Distance analysis failed"
            })
        }
