"""MQTT ingress worker.

Subscribes to a metrics topic and writes each JSON message into the same
ingestion pipeline used by the HTTP API (anomaly detection + event creation).

Run:  python -m backend.mqtt_ingest
Envvars: MQTT_BROKER (host:port, e.g. localhost:1883), MQTT_TOPIC.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from backend.config import settings
from backend.db import SessionLocal
from backend.services import ingest_metric

logger = logging.getLogger("roadwatch.mqtt")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        source_id = payload["source_id"]
        speed = float(payload["speed"])
        congestion = float(payload["congestion"])
        volume = int(payload.get("volume", 0))
        observed = payload.get("observed_at") or datetime.now(UTC).isoformat(
            timespec="milliseconds"
        )
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("Bad MQTT payload on %s: %s (%s)", msg.topic, exc, msg.payload[:120])
        return
    with SessionLocal() as db:
        try:
            row, event = ingest_metric(db, source_id, speed, congestion, volume, observed)
            db.commit()
            kind = event.kind if event else "ok"
            logger.info("MQTT metric source=%s speed=%.1f anomaly=%s event=%s",
                        source_id, speed, row.anomaly, kind)
        except ValueError as exc:
            logger.warning("Ingest rejected: %s", exc)
        except Exception:
            logger.exception("Failed to ingest MQTT metric")


def main():
    if not settings.mqtt_broker:
        raise SystemExit("MQTT_BROKER is not set (e.g. localhost:1883)")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host, _, port = settings.mqtt_broker.partition(":")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="roadwatch-ingest")
    client.on_message = on_message
    client.connect(host, int(port) if port else 1883, keepalive=60)
    client.subscribe(settings.mqtt_topic, qos=1)
    logger.info("Subscribed to %s on broker %s", settings.mqtt_topic, settings.mqtt_broker)
    client.loop_forever()


if __name__ == "__main__":
    main()
