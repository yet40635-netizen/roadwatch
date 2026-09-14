from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.catalog import VisualLabel

Kind = Literal["water", "obstacle", "accident", "pothole", "oil", "garbage", "congestion", "speed_drop"]
Status = Literal["open", "acknowledged", "resolved", "dismissed"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, from_attributes=True)


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorMessage(BaseModel):
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorMessage


class LabelOut(StrictModel):
    id: int
    label: VisualLabel
    name: str


class SourceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    baseline_speed: float = Field(default=60, gt=0, le=200)


class SourceOut(SourceCreate):
    id: str
    created_at: str


class MetricCreate(StrictModel):
    source_id: str
    observed_at: datetime
    speed: float = Field(ge=0, le=250)
    congestion: float = Field(ge=0, le=1)
    volume: int = Field(ge=0, le=100000)

    @field_validator("observed_at")
    @classmethod
    def validate_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        if value > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("observed_at cannot be more than five minutes in the future")
        return value.astimezone(UTC)


class MetricOut(StrictModel):
    id: str
    source_id: str
    observed_at: str
    speed: float
    congestion: float
    volume: int
    anomaly: bool
    score: float
    baseline: float
    reason: str


class EventOut(StrictModel):
    id: str
    source_id: str
    kind: Kind
    severity: Literal["medium", "high"]
    status: Status
    confidence: float | None
    description: str
    origin: Literal["demo", "vision", "timeseries"]
    image_id: str | None
    created_at: str
    updated_at: str
    ai_analysis: str | None = None


class EventPage(StrictModel):
    items: list[EventOut]
    total: int
    limit: int
    offset: int


class ActionCreate(StrictModel):
    status: Status
    note: str = Field(default="", max_length=1000)


class ActionOut(StrictModel):
    id: str
    event_id: str
    status: Status
    note: str
    created_at: str


class DatasetCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)


class DatasetOut(DatasetCreate):
    id: str
    created_at: str


class Box(StrictModel):
    label: VisualLabel
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("bounding box exceeds image bounds")
        return self


class AnnotationUpdate(StrictModel):
    split: Literal["train", "val", "test"]
    annotations: list[Box] = Field(max_length=500)


class BatchSplit(StrictModel):
    image_ids: list[str] = Field(min_length=1, max_length=500)
    split: Literal["train", "val", "test"]


class ImageOut(StrictModel):
    id: str
    dataset_id: str | None
    filename: str
    width: int
    height: int
    split: str
    annotations: list[Box]
    created_at: str


class Detection(Box):
    confidence: float = Field(ge=0, le=1)


class DetectionResult(StrictModel):
    mode: Literal["demo", "yolo"]
    model: str
    latency_ms: float = Field(ge=0)
    detections: list[Detection] = Field(max_length=500)
    warning: str | None = None


class JobOut(StrictModel):
    id: str
    source_id: str
    image_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    result: DetectionResult | None
    error: str | None
    attempts: int
    created_at: str
    updated_at: str


class HealthOut(StrictModel):
    status: str
    service: str


class OverviewOut(StrictModel):
    sources: int
    open_events: int
    high_events: int
    queued_jobs: int
    demo_enabled: bool


class ModelVersionCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    weights_path: str = Field(min_length=1, max_length=500)
    runtime: Literal["yolo", "onnx"] = "yolo"
    classes: list[str] = Field(default_factory=list)
    metrics: dict | None = None
    note: str = Field(default="", max_length=2000)


class ModelVersionOut(ModelVersionCreate):
    id: str
    is_active: bool
    created_at: str
