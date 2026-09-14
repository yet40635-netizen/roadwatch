from statistics import median


def analyze(speed: float, congestion: float, history: list[float], fallback: float) -> dict:
    """Use past normal speeds; a scale floor handles a constant baseline."""
    baseline = median(history) if len(history) >= 5 else fallback
    mad = median([abs(value - baseline) for value in history]) if len(history) >= 5 else 0
    scale = max(1.4826 * mad, 5.0)
    score = max(0.0, (baseline - speed) / scale)
    speed_drop = speed < baseline * 0.6 and score >= 3
    congested = congestion >= 0.8 and speed < baseline * 0.5
    kind = "congestion" if congested else "speed_drop"
    reason = (
        f"速度 {speed:.1f} km/h，基线 {baseline:.1f} km/h，"
        f"稳健偏差 {score:.2f}，拥堵指数 {congestion:.2f}"
    )
    return {
        "anomaly": speed_drop or congested, "kind": kind,
        "score": round(score, 3), "baseline": round(baseline, 3), "reason": reason,
    }
