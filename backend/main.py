import io
import secrets
import zipfile
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import queue, services
from backend import schemas as s
from backend.anomaly import analyze
from backend.catalog import LABEL_NAMES, VISUAL_LABELS
from backend.config import settings
from backend.db import Base, engine, get_db
from backend.models import Dataset, Event, EventAction, ImageAsset, Job, Metric, ModelVersion, Source
from backend.seed import seed_demo
from backend.services import add_event, change_status, lock_source, preannotate, require_row, save_image

ROOT = Path(__file__).resolve().parents[1]
api_key = APIKeyHeader(name="X-API-Key", auto_error=False)


def authorize(key: str | None = Depends(api_key)):
    if settings.api_key and (key is None or not secrets.compare_digest(key, settings.api_key)):
        raise HTTPException(401, "Invalid API key")


@asynccontextmanager
async def lifespan(_):
    import asyncio
    from backend import ws
    ws.set_loop(asyncio.get_running_loop())
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
        # Auto-migrate: add ai_analysis column to existing events table
        with engine.connect() as conn:
            from sqlalchemy import inspect, text
            insp = inspect(conn)
            if "events" in insp.get_table_names():
                cols = [c["name"] for c in insp.get_columns("events")]
                if "ai_analysis" not in cols:
                    conn.execute(text("ALTER TABLE events ADD COLUMN ai_analysis TEXT"))
                    conn.commit()
    yield


app = FastAPI(
    title="RoadWatch API", version="1.0.0",
    description="交通事件、时序异常、数据集与异步图片检测。所有 /api/v1 接口支持 X-API-Key。",
    lifespan=lifespan,
)
router = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize)], responses={
    code: {"model": s.ErrorResponse} for code in [401, 403, 404, 409, 413, 422]
})


@router.get("/labels", response_model=list[s.LabelOut], tags=["datasets"])
def labels():
    return [{"id": i, "label": label, "name": LABEL_NAMES[label]}
            for i, label in enumerate(VISUAL_LABELS)]


@app.exception_handler(HTTPException)
async def http_error(_, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": {"message": str(exc.detail)}})


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc):
    details = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {
        "message": "Request validation failed", "details": details,
    }})


@app.exception_handler(IntegrityError)
async def conflict_error(_, __):
    return JSONResponse(status_code=409, content={"error": {"message": "Record already exists"}})


@app.get("/health", response_model=s.HealthOut, tags=["system"])
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "service": "roadwatch-api"}


@router.get("/overview", response_model=s.OverviewOut, tags=["overview"])
def overview(db: Session = Depends(get_db)):
    active = ["open", "acknowledged"]
    return {
        "sources": db.scalar(select(func.count()).select_from(Source)),
        "open_events": db.scalar(select(func.count()).select_from(Event).where(Event.status.in_(active))),
        "high_events": db.scalar(select(func.count()).select_from(Event).where(
            Event.status.in_(active), Event.severity == "high",
        )),
        "queued_jobs": db.scalar(select(func.count()).select_from(Job).where(
            Job.status.in_(["queued", "running"]),
        )),
        "demo_enabled": settings.demo_enabled,
    }


@router.post("/demo/seed", status_code=201, response_model=s.HealthOut, tags=["demo"])
def demo_seed(db: Session = Depends(get_db)):
    if not settings.demo_enabled:
        raise HTTPException(403, "Demo is disabled")
    seed_demo(db)
    return {"status": "ready", "service": "demo-fixtures"}


@router.get("/sources", response_model=list[s.SourceOut], tags=["sources"])
def sources(db: Session = Depends(get_db)):
    return db.scalars(select(Source).order_by(Source.created_at).limit(1000)).all()


@router.post("/sources", response_model=s.SourceOut, status_code=201, tags=["sources"])
def create_source(body: s.SourceCreate, db: Session = Depends(get_db)):
    row = Source(**body.model_dump())
    db.add(row)
    db.commit()
    return row


@router.post("/metrics", response_model=s.MetricOut, status_code=201, tags=["metrics"])
def ingest_metric(body: s.MetricCreate, db: Session = Depends(get_db)):
    observed = body.observed_at.isoformat(timespec="milliseconds")
    try:
        row, _ = services.ingest_metric(
            db, body.source_id, body.speed, body.congestion, body.volume, observed,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return row


@router.get("/metrics", response_model=list[s.MetricOut], tags=["metrics"])
def metrics(source_id: str, limit: int = Query(60, ge=1, le=1000), db: Session = Depends(get_db)):
    require_row(db, Source, source_id)
    rows = db.scalars(select(Metric).where(Metric.source_id == source_id).order_by(
        Metric.observed_at.desc(),
    ).limit(limit)).all()
    return list(reversed(rows))


@router.get("/events", response_model=s.EventPage, tags=["events"])
def events(
    status: s.Status | None = None, kind: s.Kind | None = None, source_id: str | None = None,
    limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(Event)
    if status:
        query = query.where(Event.status == status)
    if kind:
        query = query.where(Event.kind == kind)
    if source_id:
        query = query.where(Event.source_id == source_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Event.created_at.desc(), Event.id).offset(offset).limit(limit)).all()
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/events/{event_id}", response_model=s.EventOut, tags=["events"])
def event_detail(event_id: str, db: Session = Depends(get_db)):
    return require_row(db, Event, event_id)


@router.patch("/events/{event_id}", response_model=s.EventOut, tags=["events"])
def update_event(event_id: str, body: s.ActionCreate, db: Session = Depends(get_db)):
    return change_status(db, event_id, body.status, body.note)


@router.get("/events/{event_id}/actions", response_model=list[s.ActionOut], tags=["events"])
def event_actions(event_id: str, db: Session = Depends(get_db)):
    require_row(db, Event, event_id)
    return db.scalars(select(EventAction).where(
        EventAction.event_id == event_id,
    ).order_by(EventAction.created_at)).all()


@router.post("/events/{event_id}/ai-analysis", response_model=s.EventOut, tags=["events"])
def regenerate_ai_analysis(event_id: str, db: Session = Depends(get_db)):
    """Regenerate AI analysis for an event using the configured LLM."""
    from backend.llm import analyze_event
    row = require_row(db, Event, event_id)
    source_name = ""
    if row.source_id:
        src = db.get(Source, row.source_id)
        if src:
            source_name = src.name
    analysis = analyze_event(row.kind, row.severity, row.description, source_name)
    if analysis:
        row.ai_analysis = analysis
        db.commit()
    return row


@router.get("/datasets", response_model=list[s.DatasetOut], tags=["datasets"])
def datasets(db: Session = Depends(get_db)):
    return db.scalars(select(Dataset).order_by(Dataset.created_at.desc()).limit(1000)).all()


@router.post("/datasets", response_model=s.DatasetOut, status_code=201, tags=["datasets"])
def create_dataset(body: s.DatasetCreate, db: Session = Depends(get_db)):
    row = Dataset(**body.model_dump())
    db.add(row)
    db.commit()
    return row


@router.post("/datasets/{dataset_id}/images", response_model=s.ImageOut, status_code=201, tags=["datasets"])
def upload_dataset_image(
    dataset_id: str, file: UploadFile = File(...),
    preannotate_boxes: bool = Form(False), conf: float = Form(0.25),
    db: Session = Depends(get_db),
):
    require_row(db, Dataset, dataset_id)
    row, path = save_image(db, file, dataset_id)
    try:
        if preannotate_boxes:
            row.annotations = preannotate(row.id, conf)
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return row


@router.post("/datasets/{dataset_id}/images/batch-split", response_model=list[s.ImageOut], tags=["datasets"])
def batch_split(
    dataset_id: str, body: s.BatchSplit, db: Session = Depends(get_db),
):
    """Set the split (train/val/test) for a list of images at once."""
    require_row(db, Dataset, dataset_id)
    rows = db.scalars(select(ImageAsset).where(
        ImageAsset.dataset_id == dataset_id, ImageAsset.id.in_(body.image_ids),
    )).all()
    for row in rows:
        row.split = body.split
    db.commit()
    return rows


@router.post("/images/{image_id}/preannotate", response_model=s.ImageOut, tags=["datasets"])
def run_preannotate(
    image_id: str, conf: float = Query(0.25, ge=0.01, le=0.99), db: Session = Depends(get_db),
):
    """Re-run auto-annotation for an existing dataset image using the current detector."""
    row = require_row(db, ImageAsset, image_id)
    if row.dataset_id is None:
        raise HTTPException(409, "Only dataset images can be annotated")
    row.annotations = preannotate(row.id, conf)
    db.commit()
    return row


@router.get("/datasets/{dataset_id}/images", response_model=list[s.ImageOut], tags=["datasets"])
def dataset_images(
    dataset_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    require_row(db, Dataset, dataset_id)
    return db.scalars(select(ImageAsset).where(
        ImageAsset.dataset_id == dataset_id,
    ).order_by(ImageAsset.created_at).offset(offset).limit(limit)).all()


@router.put("/images/{image_id}/annotations", response_model=s.ImageOut, tags=["datasets"])
def annotate(image_id: str, body: s.AnnotationUpdate, db: Session = Depends(get_db)):
    row = require_row(db, ImageAsset, image_id)
    if row.dataset_id is None:
        raise HTTPException(409, "Only dataset images can be annotated")
    row.split = body.split
    row.annotations = [box.model_dump() for box in body.annotations]
    db.commit()
    return row


@router.get("/images/{image_id}/content", tags=["images"], response_class=FileResponse)
def image_content(image_id: str, db: Session = Depends(get_db)):
    require_row(db, ImageAsset, image_id)
    path = settings.data_dir / "images" / f"{image_id}.jpg"
    if not path.is_file():
        raise HTTPException(404, "Image file not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/datasets/{dataset_id}/export", tags=["datasets"], response_class=StreamingResponse)
def export_dataset(dataset_id: str, db: Session = Depends(get_db)):
    require_row(db, Dataset, dataset_id)
    rows = db.scalars(select(ImageAsset).where(ImageAsset.dataset_id == dataset_id).limit(501)).all()
    if not rows:
        raise HTTPException(409, "Dataset is empty")
    if len(rows) > 500:
        raise HTTPException(413, "Interactive export is limited to 500 images")
    paths = [settings.data_dir / "images" / f"{row.id}.jpg" for row in rows]
    if any(not path.is_file() for path in paths):
        raise HTTPException(409, "Dataset contains missing image files")
    if sum(path.stat().st_size for path in paths) > 100 * 1024 * 1024:
        raise HTTPException(413, "Interactive export is limited to 100 MiB")
    labels = VISUAL_LABELS
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for row, path in zip(rows, paths):
            archive.write(path, f"images/{row.split}/{row.id}.jpg")
            lines = []
            for box in row.annotations:
                cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                lines.append(f'{labels.index(box["label"])} {cx:.6f} {cy:.6f} '
                             f'{box["width"]:.6f} {box["height"]:.6f}')
            archive.writestr(f"labels/{row.split}/{row.id}.txt", "\n".join(lines))
        archive.writestr("data.yaml", "train: images/train\nval: images/val\ntest: images/test\nnames:\n"
                         + "".join(f"  {i}: {label}\n" for i, label in enumerate(labels)))
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="dataset-{dataset_id}.zip"',
    })


@router.post("/inference/jobs", response_model=s.JobOut, status_code=202, tags=["inference"])
def create_job(
    source_id: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db),
):
    require_row(db, Source, source_id)
    row, path = save_image(db, file)
    job = Job(source_id=source_id, image_id=row.id)
    db.add(job)
    try:
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    queue.enqueue(job.id)
    return job


@router.get("/inference/jobs", response_model=list[s.JobOut], tags=["inference"])
def jobs(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    return db.scalars(select(Job).order_by(Job.created_at.desc()).limit(limit)).all()


@router.get("/inference/jobs/{job_id}", response_model=s.JobOut, tags=["inference"])
def job_detail(job_id: str, db: Session = Depends(get_db)):
    return require_row(db, Job, job_id)


@router.get("/datasets/{dataset_id}/annotation-strategy", tags=["datasets"])
def annotation_strategy(dataset_id: str, db: Session = Depends(get_db)):
    """Ask LLM for annotation strategy guidance based on dataset categories."""
    from backend.llm import suggest_annotation_strategy
    ds = require_row(db, Dataset, dataset_id)
    img_count = db.scalar(select(func.count()).select_from(ImageAsset).where(
        ImageAsset.dataset_id == dataset_id))
    categories = list(LABEL_NAMES)
    strategy = suggest_annotation_strategy(categories, img_count or 0)
    return {"strategy": strategy, "categories": categories, "image_count": img_count}


@router.get("/model-versions", response_model=list[s.ModelVersionOut], tags=["models"])
def model_versions(db: Session = Depends(get_db)):
    return db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc())).all()


@router.get("/model-versions/active", response_model=s.ModelVersionOut, tags=["models"])
def active_model_version(db: Session = Depends(get_db)):
    row = db.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True)).limit(1))
    if row is None:
        raise HTTPException(404, "No active model version")
    return row


@router.post("/model-versions", response_model=s.ModelVersionOut, status_code=201, tags=["models"])
def create_model_version(body: s.ModelVersionCreate, db: Session = Depends(get_db)):
    row = ModelVersion(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/model-versions/{version_id}/activate", response_model=s.ModelVersionOut, tags=["models"])
def activate_model_version(version_id: str, db: Session = Depends(get_db)):
    row = require_row(db, ModelVersion, version_id)
    path = Path(row.weights_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise HTTPException(409, f"Weights file not found: {row.weights_path}")
    db.execute(update(ModelVersion).values(is_active=False))
    row.is_active = True
    db.commit()
    db.refresh(row)
    return row


@router.delete("/model-versions/{version_id}", status_code=204, tags=["models"])
def delete_model_version(version_id: str, db: Session = Depends(get_db)):
    row = require_row(db, ModelVersion, version_id)
    if row.is_active:
        raise HTTPException(409, "Cannot delete the active model version; activate another first")
    db.delete(row)
    db.commit()


app.include_router(router)
app.mount("/assets", StaticFiles(directory=ROOT / "frontend"), name="assets")
app.mount("/guide", StaticFiles(directory=ROOT / "docs", html=True), name="guide")


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    """Push newly created events to the dashboard in real time."""
    await websocket.accept()
    import asyncio
    from backend import ws
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    await ws.subscribe(queue)
    try:
        while True:
            message = await queue.get()
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    finally:
        await ws.unsubscribe(queue)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "frontend" / "index.html")
