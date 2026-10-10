"""HSB Living Lab veri setinin yüklenmesi, doğrulanması ve temizlenmesi.

Ham CSV hiçbir zaman değiştirilmez; tüm çıktılar `data/processed/` altına yazılır.

Doğrulanmış veri semantiği (ayrıntı: docs/ai_methodology.md)
------------------------------------------------------------
1. `value` m³ cinsindendir → `value_liters = value * 1000` (ham sütun korunur).
2. `aggregated_value`, sensörün kümülatif sayaç endeksidir (m³). Toplam tüketim
   hesabında KULLANILMAZ; yalnızca veri kaybı tespitinde kullanılır.
3. `timestamp` yerel duvar saatidir (Europe/Stockholm); UTC'ye DST-doğru çevrilir.
4. Sensörler yalnızca tüketim olduğunda kayıt üretir. Sayaç endeksi tutarlı
   ilerlediği sürece kayıt olmayan aralık = 0 tüketim. Sayaç, boşluk boyunca
   kaydedilenden fazla ilerlediyse o aralık "gözlenmedi" kabul edilir.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .feature_engineering import records_to_slots, slots_to_hourly, add_run_length

log = logging.getLogger(__name__)

EXPECTED_COLUMNS = [
    "timestamp", "date", "hour", "day_of_week", "day_name", "month", "year",
    "sensor_id", "apartment", "cluster_name", "room_number", "room_type",
    "type", "attached_to", "value", "aggregated_value",
]

# Öneri formundaki kullanım kategorileri: duş, musluk, tuvalet, makineler
USAGE_CATEGORY_MAP = {
    "Shower": "Duş",
    "Kitchen tap": "Musluk",
    "Washbasin": "Musluk",
    "Toilet": "Tuvalet",
    "Washing machine": "Makine",
    "Dishwasher": "Makine",
    "Other": "Diğer",
}
WATER_TYPE_MAP = {"cold water consumption": "cold", "hot water consumption": "hot"}


# ---------------------------------------------------------------------------
# Yükleme ve doğrulama
# ---------------------------------------------------------------------------
def load_raw(path=config.RAW_CSV) -> pd.DataFrame:
    """Ham CSV'yi okur (`;` ayırıcı). Zaman damgası naive yerel saat olarak kalır."""
    df = pd.read_csv(path, sep=config.CSV_SEPARATOR,
                     dtype={"sensor_id": "str", "apartment": "str", "cluster_name": "str",
                            "room_number": "str"})
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV beklenen sütunları içermiyor: {missing}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S")
    return df


def validate_raw(df: pd.DataFrame) -> dict:
    """Ham veri için kalite raporu üretir (veriyi değiştirmez)."""
    ts = df["timestamp"]
    report = {
        "n_rows": int(len(df)),
        "n_columns": int(df.shape[1]),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "missing": {c: int(n) for c, n in df.isna().sum().items() if n > 0},
        "n_apartments": int(df["apartment"].nunique()),
        "n_sensors": int(df["sensor_id"].nunique()),
        "n_clusters": int(df["cluster_name"].nunique()),
        "timestamp_min": str(ts.min()),
        "timestamp_max": str(ts.max()),
        "n_days_with_data": int(df["date"].nunique()),
        "value_sum_raw": float(df["value"].sum()),
        "value_min": float(df["value"].min()),
        "value_max": float(df["value"].max()),
        "n_value_zero": int((df["value"] == 0).sum()),
        "n_value_negative": int((df["value"] < 0).sum()),
        "n_value_non_integer_liters": int((~np.isclose(df["value"] * 1000, (df["value"] * 1000).round())).sum()),
        "n_exact_duplicate_rows": int(df.duplicated().sum()),
        "n_duplicate_sensor_timestamp": int(df.duplicated(["sensor_id", "timestamp"]).sum()),
        "derived_columns_consistent": {
            "hour": bool((ts.dt.hour == df["hour"]).all()),
            "day_of_week": bool((ts.dt.dayofweek == df["day_of_week"]).all()),
            "date": bool((ts.dt.strftime("%Y-%m-%d") == df["date"]).all()),
            "month": bool((ts.dt.month == df["month"]).all()),
            "year": bool((ts.dt.year == df["year"]).all()),
        },
        "minutes_on_10min_grid": bool((ts.dt.minute % 10 == 0).all() and (ts.dt.second == 0).all()),
    }
    m = df.groupby("sensor_id").agg(
        n_apartment=("apartment", lambda s: s.nunique(dropna=False)),
        n_room=("room_number", "nunique"),
        n_fixture=("attached_to", "nunique"),
        n_type=("type", "nunique"),
    )
    report["sensor_mapping_one_to_one"] = bool((m.max() == 1).all())
    report["sensors_without_apartment"] = int(df.loc[df["apartment"].isna(), "sensor_id"].nunique())
    report["missing_apartment_by_room_type"] = (
        df.loc[df["apartment"].isna(), "room_type"].value_counts().to_dict())
    return report


# ---------------------------------------------------------------------------
# Temizleme adımları
# ---------------------------------------------------------------------------
def drop_exact_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Tamamen aynı satırları atar.

    Bu satırlarda kümülatif sayaç endeksi ilerlememiştir (aynı okumanın tekrar
    iletimi). Aynı sensör + aynı zaman damgasına sahip ama farklı sayaç
    endeksli satırlar ise 10 dakikaya yuvarlama nedeniyle aynı slota düşen
    ayrı okumalardır ve KORUNUR (slotta toplanır).
    """
    dup = df.duplicated()
    return df.loc[~dup].copy(), int(dup.sum())


def localize_timestamps(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Yerel zaman damgalarını Europe/Stockholm olarak yerelleştirip UTC'ye çevirir.

    Sonbahar DST geri alımında 02:00–02:59 iki kez yaşanır. Belirsiz satırlar
    için sensörün kümülatif sayaç sırası kullanılır: sayaç sırasına göre zaman
    geri gidiyorsa sonraki satırlar ikinci geçiştir (standart saat). Ayırt
    edilemeyen satırlarda yaz saati (ilk geçiş) varsayılır.
    """
    out = df.copy()
    naive = out["timestamp"]
    loc = naive.dt.tz_localize(config.LOCAL_TZ, ambiguous="NaT", nonexistent="NaT")
    probe = naive.dt.tz_localize(config.LOCAL_TZ, ambiguous="NaT", nonexistent="shift_forward")
    nonexistent = loc.isna() & probe.notna()
    ambiguous = probe.isna()

    is_dst = np.ones(len(out), dtype=bool)
    if ambiguous.any():
        sub = out.loc[ambiguous, ["sensor_id", "timestamp", "aggregated_value"]]
        sub = sub.sort_values(["sensor_id", "aggregated_value"])
        prev_max = sub.groupby("sensor_id")["timestamp"].cummax().groupby(sub["sensor_id"]).shift()
        second = (sub["timestamp"] < prev_max).astype(int).groupby(sub["sensor_id"]).cummax().astype(bool)
        is_dst_amb = pd.Series(True, index=out.index)
        is_dst_amb.loc[second.index] = ~second
        is_dst = np.where(ambiguous, is_dst_amb.to_numpy(), True)

    local = naive.dt.tz_localize(config.LOCAL_TZ, ambiguous=is_dst, nonexistent="shift_forward")
    out["timestamp_local"] = local
    out["timestamp_utc"] = local.dt.tz_convert("UTC")
    info = {
        "assumed_source_timezone": config.LOCAL_TZ,
        "n_ambiguous_dst_rows": int(ambiguous.sum()),
        "n_ambiguous_resolved_as_standard_time": int((ambiguous & ~is_dst).sum()),
        "n_nonexistent_rows": int(nonexistent.sum()),
    }
    return out, info


def add_liters(df: pd.DataFrame) -> pd.DataFrame:
    """`value_liters = value * 1000` ekler; ham `value` korunur."""
    out = df.copy()
    out["value_liters"] = (out["value"] * config.M3_TO_LITERS).round(3)
    return out


def standardize_categories(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["usage_category"] = out["attached_to"].map(USAGE_CATEGORY_MAP).fillna("Diğer")
    out["water_type"] = out["type"].map(WATER_TYPE_MAP).fillna("unknown")
    out["is_shared_area"] = out["apartment"].isna()
    return out


def add_register_checks(df: pd.DataFrame) -> pd.DataFrame:
    """Sayaç endeksi tutarlılığı: önceki kayıttan bu yana kaydedilmemiş tüketim."""
    out = df.sort_values(["sensor_id", "timestamp_utc", "aggregated_value"]).copy()
    g = out.groupby("sensor_id")
    out["prev_timestamp_utc"] = g["timestamp_utc"].shift()
    out["register_diff_m3"] = g["aggregated_value"].diff().round(6)
    out["gap_before_hours"] = (out["timestamp_utc"] - out["prev_timestamp_utc"]).dt.total_seconds() / 3600
    out["unrecorded_m3"] = (out["register_diff_m3"] - out["value"]).round(6)
    # 10 dakikada >= 100 L tek armatürden: ya gerçek olağandışı akış (ör. arızalı
    # rezervuar) ya da sensör toplu gönderimi. Silinmez, işaretlenir.
    out["high_rate_flag"] = out["value_liters"] >= 100
    return out.sort_index()


def detect_building_outages(df: pd.DataFrame) -> pd.DataFrame:
    """Bina genelinde BUILDING_OUTAGE_HOURS'tan uzun kayıtsız aralıklar.

    Döndürülen aralık, gözlenmeyen ilk ve son 10 dakikalık slottur.
    """
    slots = np.sort(df["timestamp_utc"].dt.floor("10min").unique())
    s = pd.Series(slots)
    gap_h = s.diff().dt.total_seconds() / 3600
    mask = gap_h > config.BUILDING_OUTAGE_HOURS
    step = pd.Timedelta(minutes=config.SLOT_MINUTES)
    out = pd.DataFrame({
        "start_utc": s.shift()[mask] + step,
        "end_utc": s[mask] - step,
        "gap_hours": gap_h[mask],
    }).reset_index(drop=True)
    return out


def detect_sensor_data_loss(df: pd.DataFrame) -> pd.DataFrame:
    """Sayaç endeksinin kaydedilenden fazla ilerlediği sensör boşlukları."""
    chk = df if "unrecorded_m3" in df else add_register_checks(df)
    loss = chk[chk["unrecorded_m3"] > config.UNRECORDED_TOLERANCE_M3].copy()
    step = pd.Timedelta(minutes=config.SLOT_MINUTES)
    prev_slot = loss["prev_timestamp_utc"].dt.floor("10min")
    cur_slot = loss["timestamp_utc"].dt.floor("10min")
    start = prev_slot + step
    end = cur_slot - step
    empty = start > end           # ardışık slotlar: kayıp slotlardan birinde
    start = start.where(~empty, prev_slot)
    end = end.where(~empty, cur_slot)
    return pd.DataFrame({
        "sensor_id": loss["sensor_id"].to_numpy(),
        "apartment": loss["apartment"].to_numpy(),
        "start_utc": start.to_numpy(),
        "end_utc": end.to_numpy(),
        "unrecorded_liters": (loss["unrecorded_m3"] * 1000).round(1).to_numpy(),
        "gap_hours": loss["gap_before_hours"].round(2).to_numpy(),
    }).sort_values(["apartment", "start_utc"]).reset_index(drop=True)


def apartment_unobserved_intervals(apartment: str, outages: pd.DataFrame,
                                   losses: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    iv = list(zip(outages["start_utc"], outages["end_utc"]))
    sub = losses[losses["apartment"] == apartment]
    iv += list(zip(sub["start_utc"], sub["end_utc"]))
    return iv


# ---------------------------------------------------------------------------
# Daire bazlı seriler
# ---------------------------------------------------------------------------
def build_apartment_series(apartment_records: pd.DataFrame, outages: pd.DataFrame,
                           losses: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Her daire için 10 dk slot ve saatlik seriler üretir.

    Daire gözlem penceresi: ilk kaydın saati → son kaydın saatinin sonu.
    """
    slot_frames, hourly_frames = [], []
    for apt, grp in apartment_records.groupby("apartment"):
        start = grp["timestamp_utc"].min().floor("h")
        end = grp["timestamp_utc"].max().floor("h") + pd.Timedelta(minutes=50)
        iv = apartment_unobserved_intervals(apt, outages, losses)
        slots = add_run_length(records_to_slots(grp, start, end, iv))
        hourly = slots_to_hourly(slots)
        slots.insert(0, "apartment", apt)
        hourly.insert(0, "apartment", apt)
        slot_frames.append(slots)
        hourly_frames.append(hourly)
    slots_all = pd.concat(slot_frames, ignore_index=True)
    hourly_all = pd.concat(hourly_frames, ignore_index=True)
    return slots_all, hourly_all


@dataclass
class PreprocessingResult:
    records: pd.DataFrame                 # tüm temiz kayıtlar (ortak alanlar dahil)
    apartment_records: pd.DataFrame
    shared_records: pd.DataFrame
    outages: pd.DataFrame
    losses: pd.DataFrame
    slots: pd.DataFrame
    hourly: pd.DataFrame
    report: dict = field(default_factory=dict)


def run_preprocessing(save: bool = True, path=config.RAW_CSV) -> PreprocessingResult:
    raw = load_raw(path)
    report = {"raw": validate_raw(raw)}

    df, n_dup = drop_exact_duplicates(raw)
    df, tz_info = localize_timestamps(df)
    df = add_liters(df)
    df = standardize_categories(df)
    df = add_register_checks(df)

    outages = detect_building_outages(df)
    losses = detect_sensor_data_loss(df)

    apt = df[df["apartment"].notna()].copy()
    shared = df[df["apartment"].isna()].copy()
    slots, hourly = build_apartment_series(apt, outages, losses)

    obs = hourly["observed"]
    report["cleaning"] = {
        "exact_duplicates_removed": n_dup,
        "rows_after_cleaning": int(len(df)),
        "timezone": tz_info,
        "unit_decision": "value (m³) * 1000 = value_liters",
        "total_liters": float(df["value_liters"].sum()),
        "total_m3": float(df["value_liters"].sum() / 1000),
        "apartment_rows": int(len(apt)),
        "shared_area_rows": int(len(shared)),
        "shared_area_sensors": int(shared["sensor_id"].nunique()),
        "apartment_liters": float(apt["value_liters"].sum()),
        "shared_area_liters": float(shared["value_liters"].sum()),
        "rows_with_register_inconsistency": int((df["unrecorded_m3"] > config.UNRECORDED_TOLERANCE_M3).sum()),
        "unrecorded_liters_in_gaps": float(df.loc[df["unrecorded_m3"] > config.UNRECORDED_TOLERANCE_M3, "unrecorded_m3"].sum() * 1000),
        "negative_register_steps_after_utc": int((df["register_diff_m3"] < -1e-9).sum()),
        "high_rate_rows_ge_100L_per_10min": int(df["high_rate_flag"].sum()),
        "building_outages": int(len(outages)),
        "building_outage_hours_total": float(outages["gap_hours"].sum()),
        "sensor_data_loss_intervals": int(len(losses)),
        "apartment_hours_total": int(len(hourly)),
        "apartment_hours_observed": int(obs.sum()),
        "apartment_hour_coverage": float(obs.mean()),
    }
    result = PreprocessingResult(df, apt, shared, outages, losses, slots, hourly, report)
    if save:
        save_outputs(result)
    return result


def save_outputs(r: PreprocessingResult) -> None:
    out = config.PROCESSED_DIR
    out.mkdir(parents=True, exist_ok=True)
    keep = ["timestamp", "timestamp_local", "timestamp_utc", "sensor_id", "apartment", "cluster_name",
            "room_number", "room_type", "type", "water_type", "attached_to", "usage_category",
            "is_shared_area", "value", "value_liters", "aggregated_value", "gap_before_hours",
            "unrecorded_m3", "high_rate_flag"]
    recs = r.records[keep].sort_values(["timestamp_utc", "sensor_id"])
    recs.to_parquet(out / "records_clean.parquet", index=False)
    recs[recs["is_shared_area"]].to_parquet(out / "shared_area_records.parquet", index=False)
    recs[~recs["is_shared_area"]].to_parquet(out / "apartment_records.parquet", index=False)
    r.slots.to_parquet(out / "apartment_slots_10min.parquet", index=False)
    r.hourly.to_parquet(out / "apartment_hourly.parquet", index=False)
    # Backend/veritabanı için okunabilir CSV özetleri
    hourly_csv = r.hourly.copy()
    hourly_csv["hour_local"] = hourly_csv["hour_utc"].dt.tz_convert(config.LOCAL_TZ)
    hourly_csv.to_csv(out / "apartment_hourly.csv", index=False)
    r.outages.to_csv(out / "building_outages.csv", index=False)
    r.losses.to_csv(out / "sensor_data_loss_intervals.csv", index=False)
    with open(out / "cleaning_report.json", "w", encoding="utf-8") as f:
        json.dump(r.report, f, ensure_ascii=False, indent=2, default=str)


def load_processed() -> PreprocessingResult:
    """Önceden kaydedilmiş işlenmiş verileri okur."""
    p = config.PROCESSED_DIR
    with open(p / "cleaning_report.json", encoding="utf-8") as f:
        report = json.load(f)
    records = pd.read_parquet(p / "records_clean.parquet")
    outages = pd.read_csv(p / "building_outages.csv", parse_dates=["start_utc", "end_utc"])
    losses = pd.read_csv(p / "sensor_data_loss_intervals.csv", parse_dates=["start_utc", "end_utc"])
    return PreprocessingResult(
        records=records,
        apartment_records=records[~records["is_shared_area"]],
        shared_records=records[records["is_shared_area"]],
        outages=outages, losses=losses,
        slots=pd.read_parquet(p / "apartment_slots_10min.parquet"),
        hourly=pd.read_parquet(p / "apartment_hourly.parquet"),
        report=report,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = run_preprocessing()
    print(json.dumps(res.report["cleaning"], ensure_ascii=False, indent=2, default=str))
