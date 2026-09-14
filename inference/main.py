import io
import os
import secrets
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from statistics import mean

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import APIKeyHeader
from PIL import Image, UnidentifiedImageError

from backend.catalog import VISUAL_LABELS
from backend.schemas import DetectionResult

MODE = os.getenv("DETECTOR_MODE", "demo")
KEY = os.getenv("API_KEY", "")
MODEL_PATH = Path(os.getenv("MODEL_PATH", "./models/road.pt"))
MODEL_MANAGER_URL = os.getenv("MODEL_MANAGER_URL", "")
DEVICE = os.getenv("MODEL_DEVICE", "cpu")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_BATCH = int(os.getenv("MAX_BATCH", "16"))
STATS_WINDOW = int(os.getenv("STATS_WINDOW", "200"))

lock = threading.Lock()
model = None
stats_lock = threading.Lock()
latencies: deque[float] = deque(maxlen=STATS_WINDOW)
request_count = 0
started_at = time.time()
Image.MAX_IMAGE_PIXELS = 20_000_000
header = APIKeyHeader(name="X-API-Key", auto_error=False)


def authorize(key: str | None = Depends(header)):
    if KEY and (key is None or not secrets.compare_digest(key, KEY)):
        raise HTTPException(401, "Invalid API key")


def record_latency(latency_ms: float):
    global request_count
    with stats_lock:
        latencies.append(latency_ms)
        request_count += 1


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


@asynccontextmanager
async def lifespan(_):
    global model
    if MODE not in {"demo", "yolo"}:
        raise RuntimeError("DETECTOR_MODE must be demo or yolo")
    if MODE == "yolo":
        weights_path = resolve_active_weights()
        if not weights_path.is_file():
            raise RuntimeError(f"Model weights not found: {weights_path}")
        from ultralytics import YOLO
        model = YOLO(str(weights_path))
        supported = set(VISUAL_LABELS)
        if not model.names or not set(model.names.values()) <= supported:
            raise RuntimeError("Unsupported road model classes: " + ", ".join(VISUAL_LABELS))
    yield


def resolve_active_weights() -> Path:
    """If MODEL_MANAGER_URL is set, fetch the active version's weights path from the API."""
    if not MODEL_MANAGER_URL:
        return MODEL_PATH
    try:
        import httpx
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{MODEL_MANAGER_URL.rstrip('/')}/api/v1/model-versions/active")
            resp.raise_for_status()
            data = resp.json()
            path = Path(data["weights_path"])
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[1] / path
            print(f"Loaded active model version '{data['name']}' from {path}")
            return path
    except Exception as exc:
        print(f"WARN: could not fetch active model from {MODEL_MANAGER_URL} ({exc}); "
              f"falling back to MODEL_PATH={MODEL_PATH}")
        return MODEL_PATH


app = FastAPI(title="RoadWatch Inference", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "mode": MODE, "model_loaded": model is not None}


@app.get("/stats")
def stats():
    with stats_lock:
        window = list(latencies)
        count = request_count
    elapsed = max(time.time() - started_at, 1e-6)
    return {
        "mode": MODE,
        "model": MODEL_PATH.name if MODE == "yolo" else "fixed-demo-fixture",
        "device": DEVICE,
        "total_requests": count,
        "window_size": len(window),
        "avg_ms": round(mean(window), 2) if window else 0.0,
        "p50_ms": round(percentile(window, 0.5), 2) if window else 0.0,
        "p95_ms": round(percentile(window, 0.95), 2) if window else 0.0,
        "p99_ms": round(percentile(window, 0.99), 2) if window else 0.0,
        "throughput_rps": round(count / elapsed, 3),
        "uptime_seconds": round(elapsed, 1),
    }


def parse_image(raw: bytes) -> Image.Image:
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image exceeds 10 MiB")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > 20_000_000:
                raise ValueError("Image too large")
            source.load()
            return source.convert("RGB")
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "Invalid image") from error


def run_detection(image: Image.Image) -> dict:
    started = time.perf_counter()
    if MODE == "demo":
        latency = round((time.perf_counter() - started) * 1000, 2)
        record_latency(latency)
        return {
            "mode": "demo", "model": "fixed-demo-fixture", "latency_ms": latency,
            "warning": "固定演示框，不分析图片内容，不能用作真实道路识别或效果评估。",
            "detections": [{"label": "obstacle", "confidence": 0.9,
                            "x": 0.3, "y": 0.45, "width": 0.3, "height": 0.25}],
        }
    with lock:
        result = model.predict(image, conf=0.4, max_det=500, device=DEVICE, verbose=False)[0]
    boxes = []
    for box in result.boxes:
        x1, y1, x2, y2 = box.xyxyn[0].tolist()
        x1, y1, x2, y2 = [max(0, min(1, value)) for value in (x1, y1, x2, y2)]
        if x2 > x1 and y2 > y1:
            boxes.append({
                "label": result.names[int(box.cls.item())],
                "confidence": float(box.conf.item()), "x": x1, "y": y1,
                "width": x2 - x1, "height": y2 - y1,
            })
    latency = round((time.perf_counter() - started) * 1000, 2)
    record_latency(latency)
    return {
        "mode": "yolo", "model": MODEL_PATH.name, "detections": boxes,
        "latency_ms": latency, "warning": None,
    }


@app.post("/predict", response_model=DetectionResult, dependencies=[Depends(authorize)])
def predict(file: UploadFile = File(...)):
    raw = file.file.read(MAX_IMAGE_BYTES + 1)
    image = parse_image(raw)
    return run_detection(image)


@app.post("/predict_batch", dependencies=[Depends(authorize)])
def predict_batch(files: list[UploadFile] = File(...)):
    """Batch inference endpoint. Accepts up to MAX_BATCH images and returns one result per image."""
    if len(files) > MAX_BATCH:
        raise HTTPException(413, f"Batch size exceeds {MAX_BATCH} images")
    if not files:
        raise HTTPException(422, "At least one image is required")
    results = []
    started = time.perf_counter()
    for upload in files:
        raw = upload.file.read(MAX_IMAGE_BYTES + 1)
        image = parse_image(raw)
        results.append(run_detection(image))
    total = round((time.perf_counter() - started) * 1000, 2)
    return {
        "count": len(results),
        "total_latency_ms": total,
        "avg_latency_ms": round(total / len(results), 2),
        "results": results,
    }
