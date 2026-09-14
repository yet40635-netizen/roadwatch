import io
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from backend import main


def metric(source, minutes, **values):
    return {
        "source_id": source["id"],
        "observed_at": (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(),
        "speed": 60, "congestion": 0.2, "volume": 40, **values,
    }


def test_seed_is_idempotent(client):
    assert client.post("/api/v1/demo/seed").status_code == 201
    assert client.post("/api/v1/demo/seed").status_code == 201
    assert client.get("/api/v1/overview").json()["sources"] == 4
    assert client.get("/api/v1/events").json()["total"] == 3


def test_anomaly_and_cooldown(client, source):
    for minute in range(-12, -6):
        assert client.post("/api/v1/metrics", json=metric(source, minute)).status_code == 201
    for minute in [-5, -4]:
        response = client.post("/api/v1/metrics", json=metric(
            source, minute, speed=12, congestion=0.92,
        ))
        assert response.status_code == 201
        assert response.json()["anomaly"] is True
        assert response.json()["baseline"] == 60
    events = client.get("/api/v1/events").json()
    assert events["total"] == 1
    assert events["items"][0]["kind"] == "congestion"
    assert events["items"][0]["origin"] == "timeseries"


def test_event_state_machine_and_audit(client, source):
    client.post("/api/v1/metrics", json=metric(source, -1, speed=10, congestion=.95))
    event = client.get("/api/v1/events").json()["items"][0]
    path = "/api/v1/events/" + event["id"]
    assert client.patch(path, json={"status": "resolved"}).status_code == 409
    assert client.patch(path, json={"status": "acknowledged", "note": "已确认"}).status_code == 200
    assert client.patch(path, json={"status": "resolved", "note": "已恢复"}).status_code == 200
    assert client.patch(path, json={"status": "open"}).status_code == 409
    actions = client.get(path + "/actions").json()
    assert [item["note"] for item in actions] == ["已确认", "已恢复"]


def test_metric_validation_and_order(client, source):
    assert client.post("/api/v1/metrics", json=metric(source, 0, speed=-1)).status_code == 422
    assert client.post("/api/v1/metrics", json=metric(source, 10)).status_code == 422
    naive = metric(source, -1)
    naive["observed_at"] = "2026-01-01T12:00:00"
    assert client.post("/api/v1/metrics", json=naive).status_code == 422
    first = metric(source, -2)
    assert client.post("/api/v1/metrics", json=first).status_code == 201
    assert client.post("/api/v1/metrics", json=first).status_code == 409
    assert client.post("/api/v1/metrics", json=metric(source, -3)).status_code == 409


def test_dataset_round_trip(client, image_bytes):
    dataset = client.post("/api/v1/datasets", json={"name": "道路测试"}).json()
    path = "/api/v1/datasets/" + dataset["id"]
    assert client.post("/api/v1/datasets", json={"name": "道路测试"}).status_code == 409
    uploaded = client.post(path + "/images", files={"file": ("road.png", image_bytes, "image/png")})
    assert uploaded.status_code == 201
    image = uploaded.json()
    annotation = {"split": "val", "annotations": [
        {"label": "water", "x": .1, "y": .2, "width": .4, "height": .5},
    ]}
    assert client.put("/api/v1/images/" + image["id"] + "/annotations", json=annotation).status_code == 200
    exported = client.get(path + "/export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        text = archive.read("labels/val/" + image["id"] + ".txt").decode()
        assert text == "0 0.300000 0.450000 0.400000 0.500000"
        assert "names:" in archive.read("data.yaml").decode()
    assert client.get("/api/v1/images/" + image["id"] + "/content").headers["content-type"] == "image/jpeg"


def test_reject_bad_upload_and_box(client, image_bytes):
    dataset = client.post("/api/v1/datasets", json={"name": "验证"}).json()
    path = "/api/v1/datasets/" + dataset["id"] + "/images"
    assert client.post(path, files={"file": ("bad.png", b"not an image", "image/png")}).status_code == 422
    image = client.post(path, files={"file": ("ok.png", image_bytes, "image/png")}).json()
    body = {"split": "train", "annotations": [
        {"label": "water", "x": .9, "y": 0, "width": .4, "height": .5},
    ]}
    assert client.put("/api/v1/images/" + image["id"] + "/annotations", json=body).status_code == 422


def test_auth_and_demo_disable(client, monkeypatch):
    monkeypatch.setattr(main, "settings", replace(main.settings, api_key="test-secret", demo_enabled=False))
    assert client.get("/api/v1/sources").status_code == 401
    assert client.get("/api/v1/sources", headers={"X-API-Key": "bad"}).status_code == 401
    assert client.get("/api/v1/sources", headers={"X-API-Key": "test-secret"}).status_code == 200
    assert client.post("/api/v1/demo/seed", headers={"X-API-Key": "test-secret"}).status_code == 403
    assert client.get("/health").status_code == 200


def test_missing_resource_and_filter_validation(client):
    assert client.get("/api/v1/events/missing").status_code == 404
    assert client.get("/api/v1/events?status=invalid").status_code == 422
    assert client.get("/api/v1/events?limit=101").status_code == 422


def test_openapi_and_static_assets(client):
    schema = client.get("/openapi.json").json()
    assert "/api/v1/inference/jobs" in schema["paths"]
    assert "DetectionResult" in schema["components"]["schemas"]
    assert client.get("/").status_code == 200
    for asset in ["app.js", "styles.css", "favicon.svg"]:
        assert client.get("/assets/" + asset).status_code == 200
