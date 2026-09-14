from backend.anomaly import analyze


def test_normal_variation_and_constant_history():
    assert not analyze(55, .2, [60] * 10, 60)["anomaly"]
    assert analyze(15, .9, [60] * 10, 60)["anomaly"]


def test_history_baseline_overrides_configured_baseline():
    result = analyze(22, .2, [20, 21, 23, 22, 21], 60)
    assert not result["anomaly"]
    assert result["baseline"] == 21


def test_congestion_index_alone_is_insufficient():
    assert not analyze(58, .95, [], 60)["anomaly"]
