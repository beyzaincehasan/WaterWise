import json

import joblib
import numpy as np
import pandas as pd
import pytest

from src import config
from src.feature_engineering import FEATURE_COLUMNS
from src.predict import WaterWiseInputError, predict_anomaly
from src.train_model import anomaly_scores, calibrate_thresholds, classify, fit_isolation_forest

APT = "APT_005"
TARGET = pd.Timestamp("2022-11-15 03:00", tz=config.LOCAL_TZ)
HIST = TARGET - pd.Timedelta(days=28)

REQUIRED_KEYS = {
    "apartment_id": str, "timestamp": str, "timestamp_local": str, "consumption_liters": float,
    "status": str, "anomaly_score": float, "thresholds": dict, "normal_consumption_liters": float,
    "active_10min_intervals": int, "continuous_activity_minutes": int, "is_night": bool,
    "reasons": list, "message": str, "history": dict, "warnings": list, "disclaimer": str,
    "model_version": str,
}


@pytest.fixture(scope="module")
def real_records():
    p = config.PROCESSED_DIR / "apartment_records.parquet"
    if not p.exists():
        pytest.skip("İşlenmiş veri yok; önce python -m src.data_preprocessing")
    r = pd.read_parquet(p, columns=["apartment", "timestamp_utc", "value_liters"])
    r = r[(r["apartment"] == APT) & (r["timestamp_utc"] >= HIST)
          & (r["timestamp_utc"] < TARGET + pd.Timedelta(hours=1))]
    return [{"timestamp": t.isoformat(), "consumption_liters": float(v)}
            for t, v in zip(r["timestamp_utc"], r["value_liters"])]


# ---------------------------------------------------------------- model
def test_model_save_and_load_roundtrip(tmp_path):
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(2000, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
    m = fit_isolation_forest(X, {"n_estimators": 50})
    path = tmp_path / "m.joblib"
    joblib.dump({"model": m, "feature_columns": FEATURE_COLUMNS}, path)
    m2 = joblib.load(path)["model"]
    np.testing.assert_allclose(anomaly_scores(m, X), anomaly_scores(m2, X))
    s = anomaly_scores(m, X)
    assert (s > 0).all() and (s <= 1).all()
    outlier = anomaly_scores(m, np.full((1, len(FEATURE_COLUMNS)), 8.0))[0]
    assert outlier > np.quantile(s, 0.99)                # yüksek skor = olağandışı


def test_threshold_classification():
    th = calibrate_thresholds(np.linspace(0, 1, 1001))
    assert th["suspicious"] < th["anomalous"]
    out = classify(np.array([0.1, th["suspicious"], th["anomalous"]]), th)
    assert list(out) == [config.STATUS_NORMAL, config.STATUS_SUSPICIOUS, config.STATUS_ANOMALOUS]


def test_saved_artifacts_consistent(detector):
    bundle = joblib.load(config.MODEL_FILE)
    assert bundle["feature_columns"] == FEATURE_COLUMNS
    meta = json.loads(config.METADATA_FILE.read_text(encoding="utf-8"))
    assert meta["feature_columns"] == FEATURE_COLUMNS
    assert meta["thresholds"]["suspicious"] == pytest.approx(detector.thresholds["suspicious"])
    for a, t in detector.apartment_thresholds.items():   # yalnızca yukarı yönlü
        assert t["suspicious"] >= detector.thresholds["suspicious"]
        assert t["anomalous"] >= detector.thresholds["anomalous"]
    assert len(detector.known_apartments()) == 28


# ---------------------------------------------------------------- predict
def test_predict_output_contract(detector, real_records):
    r = predict_anomaly(APT, real_records, TARGET.isoformat(), HIST.isoformat(), detector=detector)
    for k, typ in REQUIRED_KEYS.items():
        assert k in r and isinstance(r[k], typ), k
    assert r["status"] in {config.STATUS_NORMAL, config.STATUS_SUSPICIOUS, config.STATUS_ANOMALOUS}
    assert r["timestamp"].endswith("Z") and r["apartment_id"] == APT
    assert 0 < r["anomaly_score"] <= 1
    json.dumps(r, ensure_ascii=False)                    # JSON'a çevrilebilir


def test_future_records_are_ignored(detector, real_records):
    base = predict_anomaly(APT, real_records, TARGET.isoformat(), HIST.isoformat(), detector=detector)
    fut = real_records + [{"timestamp": (TARGET + pd.Timedelta(hours=2)).isoformat(), "consumption_liters": 500.0}]
    r = predict_anomaly(APT, fut, TARGET.isoformat(), HIST.isoformat(), detector=detector)
    assert r["anomaly_score"] == base["anomaly_score"] and r["status"] == base["status"]


def test_injected_night_leak_is_flagged(detector, real_records):
    leak = [{"timestamp": (TARGET + pd.Timedelta(minutes=10 * k)).isoformat(), "consumption_liters": 3.0}
            for k in range(6)]
    leak += [{"timestamp": (TARGET - pd.Timedelta(hours=1) + pd.Timedelta(minutes=10 * k)).isoformat(),
              "consumption_liters": 3.0} for k in range(6)]
    r = predict_anomaly(APT, real_records + leak, TARGET.isoformat(), HIST.isoformat(), detector=detector)
    assert r["status"] == config.STATUS_ANOMALOUS
    assert any(x["code"] == "NIGHT_CONTINUOUS_FLOW" for x in r["reasons"])
    assert "Gece" in r["message"]


def test_batch_and_online_scores_match(detector, real_records):
    from src.data_preprocessing import apartment_unobserved_intervals
    feats = pd.read_parquet(config.PROCESSED_DIR / "apartment_hourly_features.parquet")
    out = pd.read_csv(config.PROCESSED_DIR / "building_outages.csv", parse_dates=["start_utc", "end_utc"])
    los = pd.read_csv(config.PROCESSED_DIR / "sensor_data_loss_intervals.csv", parse_dates=["start_utc", "end_utc"])
    iv = [(a, b) for a, b in apartment_unobserved_intervals(APT, out, los) if b >= HIST and a <= TARGET]
    res = detector.evaluate(APT, real_records, start=TARGET - pd.Timedelta(hours=12), end=TARGET,
                            history_start=HIST, unobserved_intervals=iv)
    f = feats[(feats["apartment"] == APT) & (feats["hour_utc"] >= (TARGET - pd.Timedelta(hours=12)).tz_convert("UTC"))
              & (feats["hour_utc"] <= TARGET.tz_convert("UTC"))]
    batch = np.round(detector.score(f[FEATURE_COLUMNS]), 4)
    assert np.array_equal(batch, np.array([x["anomaly_score"] for x in res]))


def test_unknown_apartment_and_short_history_warn(detector):
    recs = [{"timestamp": (TARGET - pd.Timedelta(hours=10) + pd.Timedelta(minutes=10 * k)).isoformat(),
             "consumption_liters": 1.0} for k in range(0, 66, 5)]
    r = predict_anomaly("APT_999", recs, TARGET.isoformat(), detector=detector)
    codes = " ".join(r["warnings"])
    assert "UNKNOWN_APARTMENT" in codes and "SHORT_HISTORY" in codes
    assert r["history"]["apartment_profile_available"] is False
    assert r["thresholds"]["scope"] == "global"


def test_csv_style_m3_values_accepted(detector, real_records):
    m3 = [{"timestamp": x["timestamp"], "value": x["consumption_liters"] / 1000} for x in real_records]
    a = predict_anomaly(APT, real_records, TARGET.isoformat(), HIST.isoformat(), detector=detector)
    b = predict_anomaly(APT, m3, TARGET.isoformat(), HIST.isoformat(), detector=detector)
    assert a["anomaly_score"] == b["anomaly_score"]


@pytest.mark.parametrize("records,code", [
    ([], "NO_RECORDS"),
    (None, "NO_RECORDS"),
    ([{"consumption_liters": 1.0}], "MISSING_FIELD"),
    ([{"timestamp": "2022-01-01T00:00:00Z"}], "MISSING_FIELD"),
    ([{"timestamp": "2022-01-01T00:00:00Z", "consumption_liters": -1}], "NEGATIVE_VALUE"),
    ([{"timestamp": "2022-01-01T00:00:00Z", "consumption_liters": "abc"}], "INVALID_VALUE"),
    ([{"timestamp": "not-a-date", "consumption_liters": 1.0}], "INVALID_TIMESTAMP"),
    ([{"timestamp": "2022-01-01T00:00:00Z", "consumption_liters": 1.0, "apartment": "APT_002"}], "APARTMENT_MISMATCH"),
])
def test_invalid_inputs_raise_coded_errors(detector, records, code):
    with pytest.raises(WaterWiseInputError) as e:
        predict_anomaly("APT_001", records, detector=detector)
    assert e.value.code == code


def test_invalid_apartment_and_range(detector):
    recs = [{"timestamp": "2022-01-01T00:00:00Z", "consumption_liters": 1.0}]
    with pytest.raises(WaterWiseInputError) as e:
        predict_anomaly("", recs, detector=detector)
    assert e.value.code == "INVALID_APARTMENT"
    with pytest.raises(WaterWiseInputError) as e:
        predict_anomaly("APT_001", recs, "2022-01-01T00:00:00Z", history_start="2022-01-02T00:00:00Z",
                        detector=detector)
    assert e.value.code == "INVALID_RANGE"


def test_target_in_unobserved_interval(detector):
    recs = [{"timestamp": "2022-01-01T00:00:00Z", "consumption_liters": 1.0}]
    with pytest.raises(WaterWiseInputError) as e:
        predict_anomaly("APT_001", recs, "2022-01-01T05:00:00Z", history_start="2022-01-01T00:00:00Z",
                        unobserved_intervals=[("2022-01-01T04:00:00Z", "2022-01-01T06:00:00Z")],
                        detector=detector)
    assert e.value.code == "TARGET_NOT_OBSERVED"
