import numpy as np
import pandas as pd
import pytest

from src import config
from src.feature_engineering import records_to_slots, slots_to_hourly
from src.normal_profile import build_apartment_profile, build_profiles, get_profile
from src.synthetic_anomalies import SCENARIOS, inject, make_event, pulse_liters
from tests.conftest import make_records


def _hourly(seed=0, days=40, start="2021-01-01 00:00"):
    rec = make_records(start, 24 * days, seed=seed)
    s = rec["timestamp_utc"].min().floor("h")
    e = rec["timestamp_utc"].max().floor("h") + pd.Timedelta(minutes=50)
    slots = records_to_slots(rec, s, e)
    return slots, slots_to_hourly(slots)


def test_profile_ignores_unobserved_hours():
    _, h = _hourly()
    p1 = build_apartment_profile(h)
    h2 = h.copy()
    h2.loc[:100, "observed"] = False
    h2.loc[:100, "consumption_liters"] = np.nan
    p2 = build_apartment_profile(h2)
    assert p2["n_observed_hours"] == p1["n_observed_hours"] - 101
    assert len(p1["hourly_mean_liters"]) == 24
    assert p1["night"]["mean_liters_per_hour"] < np.mean(p1["hourly_mean_liters"][8:20])


def test_profiles_use_only_training_period():
    slots, h = _hourly(start="2021-11-01 00:00", days=40)
    h = h.assign(apartment="APT_X")
    slots = slots.assign(apartment="APT_X")
    p = build_profiles(h, slots)
    # Eğitim dönemi 2021-11-23'te biter: sonrası profile girmemeli
    in_train = h[h["hour_utc"] < config.TRAIN_END.tz_convert("UTC")]
    assert p["apartments"]["APT_X"]["n_total_hours"] == len(in_train)
    prof, specific = get_profile(p, "APT_UNKNOWN")
    assert not specific and "hourly_mean_liters" in prof


def test_pulse_liters_integer_and_rate():
    rng = np.random.default_rng(0)
    v = pulse_liters(12.0, 18, rng)
    assert (v == np.round(v)).all() and v.sum() == pytest.approx(36, abs=1)
    assert (pulse_liters(6.0, 18, rng) >= 1).all()      # 6 L/saat → her slotta 1 darbe


def test_synthetic_generation_reproducible_and_documented():
    _, h = _hourly()
    prof = build_apartment_profile(h, None)
    prof["slot_10min"] = {"p99_active_liters": 25.0}
    day = pd.Timestamp("2021-01-20")
    for scen in SCENARIOS:
        e1 = make_event(scen, "APT_X", day, prof, np.random.default_rng(7), "e")
        e2 = make_event(scen, "APT_X", day, prof, np.random.default_rng(7), "e")
        assert e1.slot_liters == e2.slot_liters and e1.start_utc == e2.start_utc
        assert e1.total_liters > 0 and len(e1.slot_liters) == e1.n_slots
        assert all(x == round(x) for x in e1.slot_liters)
    s1 = make_event("S1_night_continuous_flow", "APT_X", day, prof, np.random.default_rng(1), "e")
    loc = s1.start_utc.tz_convert(config.LOCAL_TZ)
    assert loc.hour == 2 and s1.n_slots == 18
    assert 6 <= s1.params["rate_l_per_hour"] <= 30


def test_inject_keeps_real_data_separate_and_rejects_unobserved():
    slots, _ = _hourly()
    prof = {"hourly_p95_liters": [5.0] * 24, "hourly_active_probability": [0.5] * 24}
    ev = make_event("S1_night_continuous_flow", "APT_X", pd.Timestamp("2021-01-20"), prof,
                    np.random.default_rng(0), "e")
    original = slots.copy()
    out = inject(slots, ev)
    pd.testing.assert_frame_equal(slots, original)              # orijinal değişmedi
    assert out["liters"].sum() == pytest.approx(original["liters"].sum() + ev.total_liters)
    bad = slots.copy()
    m = bad["slot_utc"] == ev.start_utc
    bad.loc[m, "liters"] = np.nan
    with pytest.raises(ValueError):
        inject(bad, ev)


def test_demo_leak_records_format():
    from src.synthetic_anomalies import make_demo_leak_records
    recs = make_demo_leak_records("2022-11-24 01:00", hours=3, rate_l_per_hour=18)
    assert len(recs) == 18 and all(r["consumption_liters"] == 3.0 for r in recs)
    assert recs[0]["timestamp"] == "2022-11-24T00:00:00Z"        # 01:00 CET = 00:00 UTC
    assert sum(r["consumption_liters"] for r in recs) == pytest.approx(54)
