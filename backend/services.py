import io
import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, update

from backend.config import settings
from backend.models import Event, ImageAsset, Source, utcnow

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000


def require_row(db, model, row_id):
    row = db.get(model, row_id)
    if row is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return row


def lock_source(db, source_id):
    require_row(db, Source, source_id)
    db.execute(update(Source).where(Source.id == source_id).values(name=Source.name))


def add_event(db, source_id, kind, origin, description, confidence=None, image_id=None):
    from backend.ws import broadcast_event

    cutoff = (datetime.now(UTC) - timedelta(seconds=settings.cooldown)).isoformat(
        timespec="milliseconds"
    )
    existing = db.scalar(select(Event).where(
        Event.source_id == source_id, Event.kind == kind, Event.origin == origin,
        Event.created_at >= cutoff, Event.status.in_(["open", "acknowledged"]),
    ).limit(1))
    if existing:
        return existing
    row = Event(
        source_id=source_id, kind=kind, origin=origin, description=description,
        severity="high" if kind in {"accident", "water", "oil", "congestion"} else "medium",
        confidence=confidence, image_id=image_id,
    )
    db.add(row)
    db.flush()
    broadcast_event({
        "type": "event",
        "id": row.id, "kind": row.kind, "severity": row.severity,
        "status": row.status, "origin": row.origin, "source_id": row.source_id,
        "description": row.description, "created_at": row.created_at,
    })
    # Async LLM analysis (non-blocking)
    _trigger_ai_analysis(row.id, row.kind, row.severity, description, source_id, db)
    return row


def _trigger_ai_analysis(event_id, kind, severity, description, source_id, db):
    """Spawn a background thread to call LLM for event analysis."""
    from backend.db import SessionLocal
    from backend.llm import analyze_event

    source_name = ""
    src = db.get(Source, source_id)
    if src:
        source_name = src.name

    def _worker():
        try:
            analysis = analyze_event(kind, severity, description, source_name)
            if analysis:
                with SessionLocal() as session:
                    session.execute(
                        update(Event).where(Event.id == event_id)
                        .values(ai_analysis=analysis)
                    )
                    session.commit()
                logger.info("AI analysis saved for event %s", event_id)
        except Exception as exc:
            logger.warning("AI analysis failed for event %s: %s", event_id, exc)

    threading.Thread(target=_worker, daemon=True).start()


def save_image(db, upload: UploadFile, dataset_id=None):
    raw = upload.file.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image exceeds 10 MiB")
    try:
        with Image.open(io.BytesIO(raw)) as original:
            if original.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Unsupported image format")
            if original.width * original.height > 20_000_000:
                raise ValueError("Image exceeds 20 megapixels")
            original.load()
            rgb = original.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "Upload must be a valid JPEG, PNG or WebP under 20 MP") from error
    row = ImageAsset(
        filename=Path(upload.filename or "image").name[:200], dataset_id=dataset_id,
        width=rgb.width, height=rgb.height,
    )
    db.add(row)
    db.flush()
    target = settings.data_dir / "images" / f"{row.id}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(target, "JPEG", quality=92)
    return row, target


def change_status(db, event_id, status, note):
    from backend.models import EventAction

    allowed = {
        "open": {"acknowledged", "dismissed"},
        "acknowledged": {"resolved", "dismissed"},
        "resolved": set(), "dismissed": set(),
    }
    row = require_row(db, Event, event_id)
    previous = row.status
    if status not in allowed[previous]:
        raise HTTPException(409, f"Transition {previous} -> {status} is not allowed")
    result = db.execute(update(Event).where(
        Event.id == event_id, Event.status == previous,
    ).values(status=status, updated_at=utcnow()))
    if result.rowcount != 1:
        raise HTTPException(409, "Event was updated by another request")
    db.add(EventAction(event_id=event_id, status=status, note=note))
    db.commit()
    db.refresh(row)
    return row


def preannotate(image_id: str, conf_threshold: float = 0.25) -> list[dict]:
    """Ask the inference service for initial detection boxes to seed manual labeling."""
    import httpx
    from backend.config import settings

    path = settings.data_dir / "images" / f"{image_id}.jpg"
    if not path.is_file():
        return []
    try:
        with httpx.Client(timeout=30) as client:
            with path.open("rb") as image:
                resp = client.post(
                    settings.detector_url + "/predict",
                    headers={"X-API-Key": settings.api_key},
                    files={"file": ("frame.jpg", image, "image/jpeg")},
                )
            resp.raise_for_status()
            data = resp.json()
        boxes = []
        for det in data.get("detections", []):
            if det.get("confidence", 0) >= conf_threshold:
                boxes.append({
                    "label": det["label"], "x": det["x"], "y": det["y"],
                    "width": det["width"], "height": det["height"],
                })
        return boxes
    except Exception:
        return []


def ingest_metric(db, source_id, speed, congestion, volume, observed_at):
    """Core metric ingestion + anomaly detection. Returns (metric_row, event_row_or_None).

    Reused by the HTTP API and the MQTT ingest worker.
    """
    from datetime import timedelta
    from backend.anomaly import analyze
    from backend.models import Metric

    lock_source(db, source_id)
    source = require_row(db, Source, source_id)
    observed = observed_at
    latest = db.scalar(select(Metric).where(Metric.source_id == source.id).order_by(
        Metric.observed_at.desc(),
    ).limit(1))
    if latest and observed <= latest.observed_at:
        raise ValueError("Metrics must arrive in strictly increasing observation time")
    cutoff = (observed_at_as_dt(observed) - timedelta(hours=2)).isoformat(timespec="milliseconds")
    history = list(db.scalars(select(Metric.speed).where(
        Metric.source_id == source.id, Metric.observed_at < observed,
        Metric.observed_at >= cutoff, Metric.anomaly.is_(False),
    ).order_by(Metric.observed_at.desc()).limit(60)))
    result = analyze(speed, congestion, history, source.baseline_speed)
    row = Metric(
        source_id=source_id, observed_at=observed, speed=speed, congestion=congestion,
        volume=volume, **{k: v for k, v in result.items() if k != "kind"},
    )
    db.add(row)
    event = None
    if result["anomaly"]:
        event = add_event(db, source_id, result["kind"], "timeseries", result["reason"])
    return row, event


def observed_at_as_dt(value: str):
    from datetime import datetime
    return datetime.fromisoformat(value)
