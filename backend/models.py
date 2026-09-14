from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


def uid():
    return str(uuid4())


def utcnow():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    baseline_speed: Mapped[float] = mapped_column(Float, default=60)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (
        UniqueConstraint("source_id", "observed_at"),
        Index("ix_metrics_source_time", "source_id", "observed_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    observed_at: Mapped[str] = mapped_column(String(32))
    speed: Mapped[float] = mapped_column(Float)
    congestion: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    anomaly: Mapped[bool] = mapped_column(default=False)
    score: Mapped[float] = mapped_column(Float, default=0)
    baseline: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_source_kind_time", "source_id", "kind", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(20))
    image_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow, index=True)
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow)
    ai_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventAction(Base):
    __tablename__ = "event_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)


class ImageAsset(Base):
    __tablename__ = "images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(200))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    split: Mapped[str] = mapped_column(String(10), default="train")
    annotations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80))
    weights_path: Mapped[str] = mapped_column(String(500))
    runtime: Mapped[str] = mapped_column(String(20), default="yolo")
    classes: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=False, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
