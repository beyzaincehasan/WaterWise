"""Özellik mühendisliği – eğitim ve tahmin için TEK ortak mantık.

Akış (daire başına):

    ham kayıtlar ──records_to_slots──▶ 10 dk slot serisi
                 ──slots_to_hourly───▶ saatlik seri (+ süreklilik göstergesi)
                 ──compute_features──▶ Isolation Forest özellikleri

Önemli semantik kararlar
------------------------
* Sensörler yalnızca tüketim olduğunda kayıt üretir. Bu nedenle *gözlenen*
  bir aralıkta kaydı olmayan 10 dakikalık slot = 0 L tüketimdir. Gözlenmeyen
  (sistem kesintisi / veri kaybı) slotlar NaN olarak tutulur, asla 0 yapılmaz.
* Bir saat yalnızca 6 slotunun tamamı gözlendiyse "gözlenen saat" sayılır.
* Bütün geçmiş-tabanlı özellikler yalnızca hedef saatten ÖNCEKİ verilerle
  hesaplanır (shift / closed='left'); gelecekten bilgi sızmaz.
* `continuous_activity_min` gerçek akış süresi DEĞİLDİR: art arda tüketim
  kaydı bulunan 10 dakikalık slot sayısı × 10 dakikadır (bir süreklilik
  göstergesi). Sayaçlar 1 L çözünürlükte darbe saydığından 10 dakikada 1 L'den
  az akan çok küçük kaçaklar kesintili görünebilir.
"""
from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from . import config

SLOT_FREQ = f"{config.SLOT_MINUTES}min"

# Modelin kullandığı özellikler (sıra önemlidir; metadata'ya kaydedilir).
FEATURE_COLUMNS: list[str] = [
    "hour_sin",
    "hour_cos",
    "is_weekend",
    "log_consumption",
    "log_prev_hour",
    "log_rolling_3h_sum",
    "deviation_from_normal",
    "deviation_from_24h",
    "deviation_from_7d",
    "active_slots",
    "log_continuous_activity_min",
    "night_log_consumption",
    "night_active_slots",
]


# ---------------------------------------------------------------------------
# Zaman yardımcıları
# ---------------------------------------------------------------------------
def to_utc(ts: pd.Series | pd.DatetimeIndex | Iterable, assume_tz: str = config.LOCAL_TZ) -> pd.Series:
    """Zaman damgalarını tz-aware UTC'ye çevirir.

    Saat dilimi bilgisi olmayan (naive) değerler `assume_tz` yerel saati kabul
    edilir. DST geri alımındaki belirsiz saatler için yaz saati (ilk geçiş)
    varsayılır; var olmayan saatler ileri kaydırılır.
    """
    raw = pd.Series(ts).reset_index(drop=True)
    if raw.empty:
        return pd.Series(pd.DatetimeIndex([], tz="UTC"))

    def localize(naive: pd.Series) -> pd.Series:
        return naive.dt.tz_localize(assume_tz, ambiguous=np.ones(len(naive), dtype=bool),
                                    nonexistent="shift_forward").dt.tz_convert("UTC")

    try:
        s = pd.Series(pd.to_datetime(raw))
        if isinstance(s.dtype, pd.DatetimeTZDtype):
            return s.dt.tz_convert("UTC")
        if pd.api.types.is_datetime64_dtype(s):
            return localize(s)
    except (ValueError, TypeError):
        pass
    # Karışık ofsetler (ör. DST sınırını geçen +01:00/+02:00) veya naive/aware karışımı
    if raw.map(lambda x: isinstance(x, str)).all():
        aware = raw.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True).to_numpy()
    else:
        aware = raw.map(lambda x: getattr(pd.Timestamp(x), "tzinfo", None) is not None).to_numpy()
    out = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns, UTC]")
    if aware.any():
        out[aware] = pd.to_datetime(raw[aware], utc=True, format="ISO8601" if isinstance(raw.iloc[0], str) else None)
    if (~aware).any():
        out[~aware] = localize(pd.Series(pd.to_datetime(raw[~aware])))
    return out


def local_hours(hour_utc: pd.Series) -> pd.Series:
    return hour_utc.dt.tz_convert(config.LOCAL_TZ).dt.hour


def is_night_hour(hour_local: pd.Series | np.ndarray) -> np.ndarray:
    h = np.asarray(hour_local)
    return (h >= config.NIGHT_START_HOUR) & (h < config.NIGHT_END_HOUR)


# ---------------------------------------------------------------------------
# 1) Kayıtlar → 10 dakikalık slotlar
# ---------------------------------------------------------------------------
def records_to_slots(
    records: pd.DataFrame,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    unobserved_intervals: Iterable[tuple[pd.Timestamp, pd.Timestamp]] | None = None,
    time_col: str = "timestamp_utc",
    value_col: str = "value_liters",
) -> pd.DataFrame:
    """Bir dairenin kayıtlarını düzenli 10 dakikalık slot serisine çevirir.

    Parameters
    ----------
    records : en az `time_col` (tz-aware UTC) ve `value_col` (litre) sütunları.
        Aynı slota düşen birden çok kayıt (farklı armatürler, sıcak/soğuk)
        toplanır.
    start_utc, end_utc : slot aralığı [start, end] (her ikisi dahil, slot başı).
    unobserved_intervals : (başlangıç, bitiş) çiftleri; bu aralıktaki slotlar
        gözlenmedi (NaN) olarak işaretlenir. Aralıklar slot başlangıcına göre
        kapalıdır: başlangıç <= slot <= bitiş.

    Returns
    -------
    DataFrame: slot_utc, liters (NaN = gözlenmedi), observed (bool)
    """
    start_utc = pd.Timestamp(start_utc).floor(SLOT_FREQ)
    end_utc = pd.Timestamp(end_utc).floor(SLOT_FREQ)
    idx = pd.date_range(start_utc, end_utc, freq=SLOT_FREQ, name="slot_utc")
    if len(records):
        slot = records[time_col].dt.floor(SLOT_FREQ)
        sums = records.groupby(slot)[value_col].sum()
        sums = sums[(sums.index >= start_utc) & (sums.index <= end_utc)]
        liters = sums.reindex(idx, fill_value=0.0).astype(float)
    else:
        liters = pd.Series(0.0, index=idx)
    observed = np.ones(len(idx), dtype=bool)
    if unobserved_intervals is not None:
        values = idx.values
        for a, b in unobserved_intervals:
            lo = np.searchsorted(values, pd.Timestamp(a).to_datetime64(), side="left")
            hi = np.searchsorted(values, pd.Timestamp(b).to_datetime64(), side="right")
            observed[lo:hi] = False
    liters = liters.where(observed)
    return pd.DataFrame({"slot_utc": idx, "liters": liters.values, "observed": observed})


def add_run_length(slots: pd.DataFrame) -> pd.DataFrame:
    """Art arda tüketim kaydı olan slot sayısını (süreklilik göstergesi) ekler."""
    active = (slots["liters"].fillna(0) > 0).to_numpy()
    idx = np.arange(len(active))
    # Son pasif slotun indeksi; aktif slotlarda koşu uzunluğu = idx - son_pasif
    last_reset = np.maximum.accumulate(np.where(~active, idx, -1)) if len(active) else idx
    run = idx - last_reset
    out = slots.copy()
    out["active"] = active
    out["run_slots"] = np.minimum(run, config.RUN_CAP_SLOTS)
    return out


# ---------------------------------------------------------------------------
# 2) Slotlar → saatlik seri
# ---------------------------------------------------------------------------
def slots_to_hourly(slots: pd.DataFrame) -> pd.DataFrame:
    """10 dk slotları UTC saatlerine toplar.

    Çıktı sütunları: hour_utc, consumption_liters (yalnızca 6 slot gözlendiyse,
    aksi halde NaN), observed_slots, active_slots, max_run_slots, observed.
    """
    s = add_run_length(slots) if "run_slots" not in slots else slots
    hour = s["slot_utc"].dt.floor("h")
    g = s.groupby(hour)
    hourly = pd.DataFrame({
        "consumption_liters": g["liters"].sum(min_count=1),
        "observed_slots": g["observed"].sum(),
        "active_slots": g["active"].sum(),
        "max_run_slots": g["run_slots"].max(),
    })
    hourly.index.name = "hour_utc"
    hourly = hourly.reset_index()
    hourly["observed"] = hourly["observed_slots"] == config.SLOTS_PER_HOUR
    hourly.loc[~hourly["observed"], "consumption_liters"] = np.nan
    hourly["observed_slots"] = hourly["observed_slots"].astype(int)
    hourly["active_slots"] = hourly["active_slots"].astype(int)
    hourly["max_run_slots"] = hourly["max_run_slots"].astype(int)
    return hourly


# ---------------------------------------------------------------------------
# 3) Saatlik seri → özellikler
# ---------------------------------------------------------------------------
def _same_hour_stats(c: pd.Series, hour_utc: pd.Series, hour_local: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Aynı yerel saatin son HISTORY_DAYS gündeki ortalama ve std'si (hedef saat hariç)."""
    tmp = pd.DataFrame({"c": c.to_numpy(), "h": hour_local.to_numpy()},
                       index=pd.DatetimeIndex(hour_utc))
    window = f"{config.HISTORY_DAYS}D"
    mean = pd.Series(np.nan, index=tmp.index)
    std = pd.Series(np.nan, index=tmp.index)
    for h, grp in tmp.groupby("h"):
        r = grp["c"].rolling(window, closed="left", min_periods=config.MIN_SAME_HOUR_OBS)
        mean.loc[grp.index] = r.mean().to_numpy()
        std.loc[grp.index] = r.std().to_numpy()
    return pd.Series(mean.to_numpy(), index=c.index), pd.Series(std.to_numpy(), index=c.index)


def compute_features(hourly: pd.DataFrame, profile: Mapping | None = None) -> pd.DataFrame:
    """Tek bir dairenin saatlik serisinden model özelliklerini hesaplar.

    `hourly` kesintisiz (her UTC saati bir satır) ve zamana göre sıralı
    olmalıdır; gözlenmeyen saatlerde consumption_liters = NaN.

    `profile` (normal_profile.py çıktısı, eğitim döneminden) yalnızca geçmiş
    bağlam yetersiz olduğunda yedek taban değeri olarak kullanılır ve bu durum
    `fallback_used` sütununda işaretlenir.
    """
    df = hourly.sort_values("hour_utc").reset_index(drop=True).copy()
    c = df["consumption_liters"].astype(float)
    hl = local_hours(df["hour_utc"])
    df["hour_local"] = hl
    local = df["hour_utc"].dt.tz_convert(config.LOCAL_TZ)
    df["day_of_week"] = local.dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * hl / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hl / 24)
    df["is_night"] = is_night_hour(hl).astype(int)

    # Geçmiş bağlam (yalnızca hedef saatten önceki saatler)
    df["previous_hour_consumption"] = c.shift(1)
    past = c.shift(1)
    df["rolling_24h_mean"] = past.rolling(24, min_periods=config.MIN_24H_OBS).mean()
    df["rolling_7d_mean"] = past.rolling(168, min_periods=config.MIN_7D_OBS).mean()
    sh_mean, sh_std = _same_hour_stats(c, df["hour_utc"], hl)
    df["historical_same_hour_mean"] = sh_mean
    df["historical_same_hour_std"] = sh_std
    # Hedef saat + önceki 2 saat (gözlenen saatlere göre ölçeklenmiş toplam)
    r3 = c.rolling(3, min_periods=1)
    df["rolling_3h_sum"] = r3.mean() * 3

    # Yedek değerler (profil) – yalnızca geçmiş bağlam eksikse
    fallback = np.zeros(len(df), dtype=bool)
    if profile is not None:
        hourly_mean = np.asarray(profile["hourly_mean_liters"], dtype=float)
        daily_mean = float(profile["daily"]["mean_liters"])
        prof_hour = pd.Series(hourly_mean[hl.to_numpy()], index=df.index)
        for col, fill in [
            ("historical_same_hour_mean", prof_hour),
            ("rolling_24h_mean", pd.Series(daily_mean / 24.0, index=df.index)),
            ("rolling_7d_mean", pd.Series(daily_mean / 24.0, index=df.index)),
        ]:
            miss = df[col].isna().to_numpy()
            fallback |= miss & c.notna().to_numpy()
            df[col] = df[col].fillna(fill)
    prev_missing = df["previous_hour_consumption"].isna()
    df["previous_hour_consumption"] = df["previous_hour_consumption"].fillna(df["historical_same_hour_mean"])
    df["fallback_used"] = fallback
    df["history_sufficient"] = (
        df[["historical_same_hour_mean", "rolling_24h_mean", "rolling_7d_mean"]].notna().all(axis=1)
        & ~fallback
    )
    df["prev_hour_imputed"] = prev_missing & c.notna()

    # Model özellikleri (log ölçeği ağır kuyruklu dağılımı dengeler)
    lc = np.log1p(c)
    df["log_consumption"] = lc
    df["log_prev_hour"] = np.log1p(df["previous_hour_consumption"])
    df["log_rolling_3h_sum"] = np.log1p(df["rolling_3h_sum"])
    df["deviation_from_normal"] = lc - np.log1p(df["historical_same_hour_mean"])
    df["deviation_from_24h"] = lc - np.log1p(df["rolling_24h_mean"])
    df["deviation_from_7d"] = lc - np.log1p(df["rolling_7d_mean"])
    df["continuous_activity_min"] = df["max_run_slots"] * config.SLOT_MINUTES
    df["log_continuous_activity_min"] = np.log1p(df["continuous_activity_min"])
    df["nighttime_consumption"] = np.where(df["is_night"] == 1, c, 0.0)
    df["night_log_consumption"] = df["is_night"] * lc
    df["night_active_slots"] = df["is_night"] * df["active_slots"]

    df["feature_complete"] = df[FEATURE_COLUMNS].notna().all(axis=1) & df["observed"]
    return df


def build_apartment_features(
    records: pd.DataFrame,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    unobserved_intervals=None,
    profile: Mapping | None = None,
    time_col: str = "timestamp_utc",
    value_col: str = "value_liters",
) -> pd.DataFrame:
    """records → slots → hourly → features (tek çağrıda)."""
    slots = records_to_slots(records, start_utc, end_utc, unobserved_intervals, time_col, value_col)
    hourly = slots_to_hourly(slots)
    return compute_features(hourly, profile)
