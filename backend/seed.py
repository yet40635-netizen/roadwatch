import math
from datetime import UTC, datetime, timedelta

from backend.models import Event, Metric, Source


def seed_demo(db):
    marker = "00000000-0000-4000-8000-000000000001"
    if db.get(Source, marker):
        return
    names = [
        ("中环 · 干诺道中", 22.2858, 114.1580),
        ("湾仔 · 告士打道", 22.2808, 114.1750),
        ("铜锣湾 · 维园道", 22.2830, 114.1890),
        ("九龙 · 弥敦道", 22.3050, 114.1710),
    ]
    now = datetime.now(UTC)
    for index, (name, lat, lon) in enumerate(names):
        source = Source(
            id=f"00000000-0000-4000-8000-{index + 1:012d}",
            name=name, latitude=lat, longitude=lon, baseline_speed=60,
        )
        db.add(source)
        db.flush()
        for step in range(36):
            speed = 58 + 5 * math.sin(step / 3 + index)
            abnormal = index == 1 and step >= 31
            db.add(Metric(
                source_id=source.id,
                observed_at=(now - timedelta(minutes=36 - step)).isoformat(timespec="milliseconds"),
                speed=round(14 + step % 4 if abnormal else speed, 1),
                congestion=0.91 if abnormal else 0.22, volume=36 + step % 11,
                anomaly=abnormal, score=8.5 if abnormal else 0, baseline=60,
                reason="演示指标：用于验证看板与告警流程",
            ))
        if index < 3:
            kind = ["water", "congestion", "obstacle"][index]
            db.add(Event(
                source_id=source.id, kind=kind,
                severity="high" if index < 2 else "medium",
                description="演示事件，用于体验事件确认与处置流程，不代表真实道路情况。",
                origin="demo", confidence=0.9 if index != 1 else None,
                created_at=(now - timedelta(minutes=4 + index * 7)).isoformat(
                    timespec="milliseconds"
                ),
            ))
    db.commit()
