import numpy as np
import pandas as pd
import pytest

from src import config
from src.data_preprocessing import (USAGE_CATEGORY_MAP, add_liters, add_register_checks, detect_building_outages,
                                    detect_sensor_data_loss, drop_exact_duplicates, load_raw,
                                    localize_timestamps, standardize_categories, validate_raw)


def _clean(path):
    df, n = drop_exact_duplicates(load_raw(path))
    df, info = localize_timestamps(df)
    df = add_register_checks(standardize_categories(add_liters(df)))
    return df, n, info


def test_csv_read_semicolon_and_types(small_csv):
    df = load_raw(small_csv)
    assert len(df) == 9 and df.shape[1] == 16
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])
    assert df["timestamp"].dt.tz is None          # ham hâlde naive yerel saat


def test_missing_required_column_raises(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("timestamp;value\n2021-01-01 00:00:00;0.001\n", encoding="utf-8")
    with pytest.raises(ValueError, match="beklenen sütun"):
        load_raw(p)


def test_liter_conversion_keeps_raw_value(small_csv):
    df = add_liters(load_raw(small_csv))
    assert "value" in df and "value_liters" in df
    np.testing.assert_allclose(df["value_liters"], df["value"] * 1000)
    assert df.loc[0, "value_liters"] == 2.0


def test_exact_duplicates_removed_only(small_csv):
    df, n = drop_exact_duplicates(load_raw(small_csv))
    assert n == 1 and len(df) == 8


def test_dst_ambiguous_resolved_with_register(small_csv):
    df, _, info = _clean(small_csv)
    assert info["n_ambiguous_dst_rows"] == 2
    assert info["n_ambiguous_resolved_as_standard_time"] == 1
    s1 = df[df["sensor_id"] == "S0001"].sort_values("aggregated_value")
    # UTC sırası sayaç sırasıyla aynı olmalı (geri adım yok)
    assert s1["timestamp_utc"].is_monotonic_increasing
    assert (df["register_diff_m3"].dropna() >= 0).all()


def test_missing_apartment_is_shared_area_not_dropped(small_csv):
    df, _, _ = _clean(small_csv)
    shared = df[df["is_shared_area"]]
    assert len(shared) == 2 and shared["apartment"].isna().all()
    assert df["apartment"].isna().sum() == 2          # doldurulmadı


def test_usage_categories_standardized(small_csv):
    df, _, _ = _clean(small_csv)
    assert set(df["usage_category"]) <= set(USAGE_CATEGORY_MAP.values())
    assert df.loc[df["attached_to"] == "Shower", "usage_category"].eq("Duş").all()


def test_register_data_loss_detected(small_csv):
    df, _, _ = _clean(small_csv)
    loss = detect_sensor_data_loss(df)
    assert len(loss) == 1
    r = loss.iloc[0]
    assert r["apartment"] == "APT_001" and r["unrecorded_liters"] == pytest.approx(50.0)
    assert r["start_utc"] < r["end_utc"]


def test_building_outages_threshold(small_csv):
    df, _, _ = _clean(small_csv)
    out = detect_building_outages(df)
    # 03:00 → 08:00 yerel arası 5 saat < 6 saat eşiği; 22:00 → 01:50 de 6 saatten kısa
    assert (out["gap_hours"] > config.BUILDING_OUTAGE_HOURS).all()


def test_validate_raw_reports(small_csv):
    rep = validate_raw(load_raw(small_csv))
    assert rep["n_rows"] == 9 and rep["n_exact_duplicate_rows"] == 1
    assert rep["missing"]["apartment"] == 2
    assert all(rep["derived_columns_consistent"].values())


@pytest.mark.skipif(not config.RAW_CSV.exists(), reason="ham CSV yok")
def test_real_csv_matches_documented_facts():
    df = load_raw()
    assert df.shape == (652315, 16)
    assert df["apartment"].isna().sum() == 154269
    assert df["cluster_name"].isna().sum() == 41798
    assert df["sensor_id"].nunique() == 214 and df["apartment"].nunique() == 28
    assert df["value"].sum() == pytest.approx(3270.789, abs=1e-3)   # README: ~3271 m³
    assert (df["value"] > 0).all()
