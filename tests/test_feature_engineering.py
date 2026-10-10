import numpy as np
import pandas as pd
import pytest

from src import config
from src.feature_engineering import (FEATURE_COLUMNS, add_run_length, build_apartment_features, compute_features,
                                     records_to_slots, slots_to_hourly, to_utc)
from tests.conftest import make_records

U = "UTC"


def ts(s):
    return pd.Timestamp(s, tz=U)


def test_to_utc_naive_is_local_time():
    out = to_utc(["2022-07-01 12:00:00", "2022-01-01 12:00:00"])
    assert out.iloc[0] == ts("2022-07-01 10:00")    # CEST = UTC+2
    assert out.iloc[1] == ts("2022-01-01 11:00")    # CET = UTC+1
    aware = to_utc(["2022-07-01T12:00:00Z"])
    assert aware.iloc[0] == ts("2022-07-01 12:00")


def test_to_utc_mixed_offsets_across_dst():
    out = to_utc(["2022-10-29T12:00:00+02:00", "2022-10-31T12:00:00+01:00", "2022-11-01T12:00:00Z",
                  "2022-11-02 12:00:00"])
    assert list(out) == [ts("2022-10-29 10:00"), ts("2022-10-31 11:00"), ts("2022-11-01 12:00"),
                         ts("2022-11-02 11:00")]


def test_missing_slots_are_zero_but_unobserved_are_nan():
    rec = pd.DataFrame({"timestamp_utc": [ts("2022-01-01 00:10"), ts("2022-01-01 00:10"), ts("2022-01-01 00:40")],
                        "value_liters": [2.0, 3.0, 1.0]})
    s = records_to_slots(rec, ts("2022-01-01 00:00"), ts("2022-01-01 01:50"),
                         [(ts("2022-01-01 01:00"), ts("2022-01-01 01:20"))])
    assert len(s) == 12
    assert s.loc[1, "liters"] == 5.0                  # aynı slottaki kayıtlar toplanır
    assert s.loc[0, "liters"] == 0.0                  # kayıt yok, gözlendi → 0
    assert s.loc[6:8, "liters"].isna().all()          # gözlenmedi → NaN (0 değil)
    assert not s.loc[6:8, "observed"].any()


def test_hourly_requires_all_six_slots():
    rec = pd.DataFrame({"timestamp_utc": [ts("2022-01-01 00:10"), ts("2022-01-01 01:10")], "value_liters": [2.0, 4.0]})
    s = records_to_slots(rec, ts("2022-01-01 00:00"), ts("2022-01-01 01:50"),
                         [(ts("2022-01-01 01:30"), ts("2022-01-01 01:30"))])
    h = slots_to_hourly(s)
    assert h.loc[0, "consumption_liters"] == 2.0 and h.loc[0, "observed"]
    assert np.isnan(h.loc[1, "consumption_liters"]) and not h.loc[1, "observed"]


def test_run_length_continuity_proxy():
    liters = [1, 1, 0, 1, 1, 1, np.nan, 1]
    s = pd.DataFrame({"slot_utc": pd.date_range(ts("2022-01-01"), periods=8, freq="10min"), "liters": liters,
                      "observed": [not np.isnan(x) for x in liters]})
    r = add_run_length(s)["run_slots"].tolist()
    assert r == [1, 2, 0, 1, 2, 3, 0, 1]             # gözlenmeyen slot zinciri keser


def test_hourly_aggregation_totals():
    rec = make_records("2022-03-01 00:00", 48, seed=1)
    start, end = rec["timestamp_utc"].min().floor("h"), rec["timestamp_utc"].max().floor("h") + pd.Timedelta(minutes=50)
    h = slots_to_hourly(records_to_slots(rec, start, end))
    assert h["consumption_liters"].sum() == pytest.approx(rec["value_liters"].sum())
    assert h["active_slots"].between(0, 6).all()


def _features(rec, profile=None):
    start = rec["timestamp_utc"].min().floor("h")
    end = rec["timestamp_utc"].max().floor("h") + pd.Timedelta(minutes=50)
    return build_apartment_features(rec, start, end, None, profile)


def test_rolling_features_values():
    rec = make_records("2022-03-01 00:00", 24 * 10, seed=2)
    f = _features(rec)
    c = f["consumption_liters"]
    i = 24 * 9
    assert f.loc[i, "previous_hour_consumption"] == c[i - 1]
    assert f.loc[i, "rolling_24h_mean"] == pytest.approx(c[i - 24:i].mean())
    assert f.loc[i, "rolling_7d_mean"] == pytest.approx(c[i - 168:i].mean())
    same = c[[i - 24 * k for k in range(1, 10) if i - 24 * k >= 0]]
    assert f.loc[i, "historical_same_hour_mean"] == pytest.approx(same.mean())
    assert f.loc[i, "deviation_from_normal"] == pytest.approx(np.log1p(c[i]) - np.log1p(same.mean()))
    assert f.loc[i:, FEATURE_COLUMNS].notna().all().all()


def test_no_future_leakage():
    rec = make_records("2022-03-01 00:00", 24 * 35, seed=3)
    base = _features(rec)
    cut = base["hour_utc"].iloc[24 * 30]
    future = rec["timestamp_utc"] > cut + pd.Timedelta(minutes=50)
    modified = rec.copy()
    modified.loc[future, "value_liters"] *= 50       # gelecekte büyük değişiklik
    mod = _features(modified)
    cols = FEATURE_COLUMNS + ["historical_same_hour_mean", "rolling_24h_mean", "rolling_7d_mean"]
    upto = base["hour_utc"] <= cut
    pd.testing.assert_frame_equal(base.loc[upto, cols].reset_index(drop=True),
                                  mod.loc[upto, cols].reset_index(drop=True))


def test_history_insufficient_uses_profile_fallback():
    rec = make_records("2022-03-01 00:00", 24 * 2, seed=4)
    profile = {"hourly_mean_liters": [1.0] * 24, "daily": {"mean_liters": 24.0}}
    f = _features(rec, profile)
    assert f["fallback_used"].iloc[5] and not f["history_sufficient"].iloc[5]
    assert f.loc[5, "historical_same_hour_mean"] == 1.0
    assert f[FEATURE_COLUMNS].iloc[1:].notna().all().all()
    nf = _features(rec, None)
    assert nf["historical_same_hour_mean"].iloc[5] != nf["historical_same_hour_mean"].iloc[5]  # NaN


def test_local_hour_and_night_flag_dst_aware():
    rec = pd.DataFrame({"timestamp_utc": [ts("2022-07-01 00:10"), ts("2022-01-01 01:10")], "value_liters": [1.0, 1.0]})
    for t, expected in [(ts("2022-07-01 00:00"), 2), (ts("2022-01-01 01:00"), 2)]:
        f = build_apartment_features(rec, t, t + pd.Timedelta(minutes=50))
        assert f.loc[0, "hour_local"] == expected and f.loc[0, "is_night"] == 1
