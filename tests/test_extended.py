import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend import worker
from inference.main import app as detector
from scripts.check_dataset import check_dataset


@pytest.mark.parametrize("label,category", [("oil", 4), ("garbage", 5)])
def test_new_categories_roundtrip(client, image_bytes, label, category):
    dataset = client.post("/api/v1/datasets", json={"name": label}).json()
    path = "/api/v1/datasets/" + dataset["id"]
    image = client.post(path + "/images", files={"file": ("a.png", image_bytes)}).json()
    body = {"split": "train", "annotations": [
        {"label": label, "x": .1, "y": .2, "width": .2, "height": .2}]}
    assert client.put("/api/v1/images/" + image["id"] + "/annotations", json=body).status_code == 200
    with zipfile.ZipFile(io.BytesIO(client.get(path + "/export").content)) as archive:
        assert archive.read("labels/train/" + image["id"] + ".txt").decode().startswith(str(category))
        assert "5: garbage" in archive.read("data.yaml").decode()


def test_vision_oil_creates_real_event(client, source, image_bytes):
    job = client.post("/api/v1/inference/jobs", data={"source_id": source["id"]},
                      files={"file": ("a.png", image_bytes)}).json()

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"mode": "yolo", "model": "test-contract", "latency_ms": 10,
                    "detections": [{"label": "oil", "confidence": .88, "x": .1,
                                    "y": .2, "width": .2, "height": .3}]}

    class Predictor:
        def post(self, *args, **kwargs):
            return Response()

    worker.run_once(Predictor())
    assert client.get("/api/v1/inference/jobs/" + job["id"]).json()["status"] == "succeeded"
    event = client.get("/api/v1/events?kind=oil").json()["items"][0]
    assert event["origin"] == "vision"
    assert event["severity"] == "high"


def test_detector_rejects_invalid_image():
    with TestClient(detector) as client:
        assert client.post("/predict", files={"file": ("bad.jpg", b"bad")}).status_code == 422


def test_detector_demo_is_explicit(image_bytes):
    with TestClient(detector) as client:
        result = client.post("/predict", files={"file": ("a.png", image_bytes)}).json()
        assert result["mode"] == "demo"
        assert "固定演示框" in result["warning"]


def test_catalog_and_unknown_label(client):
    labels = client.get("/api/v1/labels").json()
    assert [label["label"] for label in labels][-2:] == ["oil", "garbage"]
    assert client.get("/api/v1/events?kind=unknown").status_code == 422


def test_dataset_checker_detects_leakage(tmp_path):
    for split in ["train", "val", "test"]:
        (tmp_path / "images" / split).mkdir(parents=True)
        (tmp_path / "labels" / split).mkdir(parents=True)
        (tmp_path / "images" / split / "a.jpg").write_bytes(b"same image")
        (tmp_path / "labels" / split / "a.txt").write_text("4 0.5 0.5 0.2 0.2")
    report = check_dataset(tmp_path)
    assert not report["valid"]
    assert any("identical image" in error for error in report["errors"])


def test_dataset_checker_rejects_nan(tmp_path):
    for index, split in enumerate(["train", "val", "test"]):
        (tmp_path / "images" / split).mkdir(parents=True)
        (tmp_path / "labels" / split).mkdir(parents=True)
        (tmp_path / "images" / split / "a.jpg").write_bytes(bytes([index]))
        (tmp_path / "labels" / split / "a.txt").write_text("4 nan 0.5 0.2 0.2")
    assert not check_dataset(tmp_path)["valid"]
