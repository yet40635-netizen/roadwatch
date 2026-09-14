import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import and_, or_, select, update

from backend import queue
from backend.config import settings
from backend.db import SessionLocal
from backend.models import Job, utcnow
from backend.schemas import DetectionResult
from backend.services import add_event, lock_source

logger = logging.getLogger("roadwatch.worker")


def eligible(now):
    return or_(Job.status == "queued", and_(Job.status == "running", Job.lease_until < now))


def claim(db):
    now = utcnow()
    candidate = db.scalar(select(Job).where(eligible(now)).order_by(Job.created_at).limit(1))
    if candidate is None:
        return None
    if candidate.attempts >= 3:
        db.execute(update(Job).where(Job.id == candidate.id, eligible(now)).values(
            status="failed", error="Retry limit exceeded after worker interruption", updated_at=now,
        ))
        db.commit()
        return None
    token = str(uuid4())
    lease = (datetime.now(UTC) + timedelta(seconds=settings.lease_seconds)).isoformat(
        timespec="milliseconds"
    )
    result = db.execute(update(Job).where(Job.id == candidate.id, eligible(now)).values(
        status="running", lease_token=token, lease_until=lease,
        attempts=Job.attempts + 1, updated_at=now,
    ))
    db.commit()
    if result.rowcount != 1:
        return None
    db.refresh(candidate)
    return candidate.id, candidate.image_id, token


def run_once(client=None):
    with SessionLocal() as db:
        task = claim(db)
    if task is None:
        return False
    job_id, image_id, token = task
    error = None
    result = None
    try:
        with (settings.data_dir / "images" / f"{image_id}.jpg").open("rb") as image:
            if client is None:
                with httpx.Client(timeout=60) as session:
                    response = session.post(
                        settings.detector_url + "/predict",
                        headers={"X-API-Key": settings.api_key},
                        files={"file": ("frame.jpg", image, "image/jpeg")},
                    )
            else:
                response = client.post("/predict", files={"file": ("frame.jpg", image, "image/jpeg")})
        response.raise_for_status()
        result = DetectionResult.model_validate(response.json()).model_dump()
        if result["mode"] == "demo" and not settings.demo_enabled:
            raise ValueError("Demo detector is forbidden when DEMO_ENABLED=false")
    except Exception as exc:
        error = f"{type(exc).__name__}: inference failed; check detector logs"
        logger.exception("Inference job %s failed", job_id)
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        lock_source(db, job.source_id)
        owned = db.execute(update(Job).where(
            Job.id == job_id, Job.lease_token == token, Job.status == "running",
        ).values(
            status="failed" if error else "succeeded", result=result if not error else None,
            error=error, updated_at=utcnow(), lease_until=None,
        ))
        if owned.rowcount == 1 and not error:
            for detection in result["detections"]:
                add_event(
                    db, job.source_id, detection["label"],
                    "demo" if result["mode"] == "demo" else "vision",
                    result["warning"] or f'模型 {result["model"]} 检测到 {detection["label"]}',
                    detection["confidence"], image_id,
                )
        db.commit()
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Worker started (queue: %s)", "redis" if settings.redis_url else "db-polling")
    while True:
        try:
            if not run_once():
                # Block on Redis notification if available, else short poll.
                if not queue.wait_for_job(timeout=5):
                    time.sleep(1)
        except KeyboardInterrupt:
            break
        except Exception:
            logger.exception("Worker loop failed")
            time.sleep(3)


if __name__ == "__main__":
    main()
