from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend import worker
from backend.models import Job
from inference.main import app as detector


def create_job(client, source, image_bytes):
    response = client.post("/api/v1/inference/jobs", data={"source_id": source["id"]},
                           files={"file": ("road.png", image_bytes, "image/png")})
    assert response.status_code == 202
    return response.json()


def test_worker_completes_demo_job(client, source, image_bytes):
    job = create_job(client, source, image_bytes)
    with TestClient(detector) as inference:
        assert worker.run_once(inference) is True
    result = client.get("/api/v1/inference/jobs/" + job["id"]).json()
    assert result["status"] == "succeeded"
    assert result["result"]["mode"] == "demo"
    assert result["result"]["warning"]
    events = client.get("/api/v1/events").json()["items"]
    assert events[0]["origin"] == "demo"
    assert events[0]["image_id"] == job["image_id"]


def test_worker_refuses_demo_in_production(client, source, image_bytes, monkeypatch):
    job = create_job(client, source, image_bytes)
    monkeypatch.setattr(worker, "settings", replace(worker.settings, demo_enabled=False))
    with TestClient(detector) as inference:
        worker.run_once(inference)
    assert client.get("/api/v1/inference/jobs/" + job["id"]).json()["status"] == "failed"
    assert client.get("/api/v1/events").json()["total"] == 0


def test_expired_lease_is_reclaimed(client, source, image_bytes):
    job = create_job(client, source, image_bytes)
    with worker.SessionLocal() as db:
        first = worker.claim(db)
        assert first[0] == job["id"]
    with worker.SessionLocal() as db:
        assert worker.claim(db) is None
        row = db.get(Job, job["id"])
        row.lease_until = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.commit()
    with worker.SessionLocal() as db:
        second = worker.claim(db)
        assert second[0] == first[0]
        assert second[2] != first[2]
        assert db.get(Job, job["id"]).attempts == 2


def test_failed_detector_is_visible(client, source, image_bytes):
    job = create_job(client, source, image_bytes)

    class Broken:
        def post(self, *_args, **_kwargs):
            raise ConnectionError("offline")

    worker.run_once(Broken())
    result = client.get("/api/v1/inference/jobs/" + job["id"]).json()
    assert result["status"] == "failed"
    assert "ConnectionError" in result["error"]
    assert client.get("/api/v1/events").json()["total"] == 0
