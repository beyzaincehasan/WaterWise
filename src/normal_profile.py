"""Daire bazlı normal tüketim profilleri.

Profil YALNIZCA eğitim döneminden (config.TRAIN_START – TRAIN_END) ve yalnızca
tamamen gözlenen saatlerden/günlerden hesaplanır. Gözlenmeyen saatler (sistem
kesintisi, veri kaybı) hesaba katılmaz; böylece kesinti dönemleri ortalamaları
aşağı çekmez. Doğrulama/test dönemlerinden hiçbir bilgi profile girmez.

Profil backend tarafından iki amaçla kullanılır:
  1. Uyarı mesajlarında "normal – tespit edilen" karşılaştırması
  2. Geçmiş bağlam yetersizse özellik hesaplamasında yedek taban değeri
"""
from __future__ import annotations

import json
from typing import Mapping

import numpy as np
import pandas as pd

from . import config
from .feature_engineering import is_night_hour


def _q(s: pd.Series, q: float) -> float:
    s = s.dropna()
    return float(s.quantile(q)) if len(s) else float("nan")


def _r(x, nd=3):
    if isinstance(x, (list, tuple, np.ndarray)):
        return [None if (v is None or not np.isfinite(v)) else round(float(v), nd) for v in x]
    return None if (x is None or not np.isfinite(x)) else round(float(x), nd)


def select_period(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, col: str = "hour_utc") -> pd.DataFrame:
    return df[(df[col] >= start.tz_convert("UTC")) & (df[col] < end.tz_convert("UTC"))]


def build_apartment_profile(hourly: pd.DataFrame, slots: pd.DataFrame | None = None) -> dict:
    """Tek dairenin (eğitim dönemi) saatlik serisinden profil üretir."""
    h = hourly.copy()
    local = h["hour_utc"].dt.tz_convert(config.LOCAL_TZ)
    h["hour_local"] = local.dt.hour
    h["date_local"] = local.dt.date
    h["dow"] = local.dt.dayofweek
    h["night"] = is_night_hour(h["hour_local"])
    obs = h[h["observed"]]

    # Tam gözlenen yerel günler (DST günleri 23/25 saat olabilir)
    day = h.groupby("date_local").agg(n=("observed", "size"), n_obs=("observed", "sum"),
                                      liters=("consumption_liters", "sum"), dow=("dow", "first"))
    full_days = day[day["n"] == day["n_obs"]]
    daily = full_days["liters"]

    nights = h[h["night"]].groupby("date_local").agg(n_obs=("observed", "sum"), n=("observed", "size"),
                                                    liters=("consumption_liters", "sum"),
                                                    active=("active_slots", "sum"))
    nights = nights[nights["n"] == nights["n_obs"]]

    by_hour = obs.groupby("hour_local")["consumption_liters"]
    hours = range(24)
    hourly_mean = by_hour.mean().reindex(hours)
    # Seyrek saatler için ortalamayı genel saatlik ortalamayla doldur
    hourly_mean = hourly_mean.fillna(obs["consumption_liters"].mean())

    cont = obs["max_run_slots"] * config.SLOT_MINUTES
    cont_night = obs.loc[obs["night"], "max_run_slots"] * config.SLOT_MINUTES
    prof = {
        "n_observed_hours": int(len(obs)),
        "n_total_hours": int(len(h)),
        "observed_fraction": _r(len(obs) / max(len(h), 1), 4),
        "n_full_days": int(len(full_days)),
        "daily": {
            "mean_liters": _r(daily.mean()),
            "median_liters": _r(daily.median()),
            "std_liters": _r(daily.std()),
            "p05_liters": _r(_q(daily, 0.05)),
            "p95_liters": _r(_q(daily, 0.95)),
            "normal_range_liters": [_r(_q(daily, 0.05)), _r(_q(daily, 0.95))],
            "coefficient_of_variation": _r(daily.std() / daily.mean() if daily.mean() else np.nan),
            "zero_consumption_day_fraction": _r((daily == 0).mean(), 4),
        },
        "hourly_mean_liters": _r(hourly_mean.to_numpy()),
        "hourly_median_liters": _r(by_hour.median().reindex(hours).to_numpy()),
        "hourly_std_liters": _r(by_hour.std().reindex(hours).to_numpy()),
        "hourly_p95_liters": _r(by_hour.quantile(0.95).reindex(hours).to_numpy()),
        "hourly_active_probability": _r(obs.groupby("hour_local")["consumption_liters"]
                                        .apply(lambda s: (s > 0).mean()).reindex(hours).to_numpy(), 4),
        "hourly_overall_p99_liters": _r(_q(obs["consumption_liters"], 0.99)),
        "weekday_daily_mean_liters": _r(full_days.groupby("dow")["liters"].mean().reindex(range(7)).to_numpy()),
        "weekday_vs_weekend_daily_mean_liters": {
            "weekday": _r(full_days.loc[full_days["dow"] < 5, "liters"].mean()),
            "weekend": _r(full_days.loc[full_days["dow"] >= 5, "liters"].mean()),
        },
        "night": {
            "hours_local": [config.NIGHT_START_HOUR, config.NIGHT_END_HOUR],
            "mean_liters_per_hour": _r(obs.loc[obs["night"], "consumption_liters"].mean()),
            "p95_liters_per_hour": _r(_q(obs.loc[obs["night"], "consumption_liters"], 0.95)),
            "mean_liters_per_night": _r(nights["liters"].mean()),
            "p95_liters_per_night": _r(_q(nights["liters"], 0.95)),
            "mean_active_slots_per_night": _r(nights["active"].mean()),
            "n_full_nights": int(len(nights)),
        },
        "continuity": {
            "description": "Art arda tüketim kaydı olan 10 dk slotların süresi (gerçek akış süresi değildir)",
            "p95_minutes": _r(_q(cont, 0.95)),
            "p99_minutes": _r(_q(cont, 0.99)),
            "night_p95_minutes": _r(_q(cont_night, 0.95)),
            "night_p99_minutes": _r(_q(cont_night, 0.99)),
        },
    }
    if slots is not None:
        pos = slots.loc[slots["liters"] > 0, "liters"]
        prof["slot_10min"] = {
            "active_fraction": _r((slots["liters"] > 0).mean(), 4),
            "p50_active_liters": _r(_q(pos, 0.5)),
            "p95_active_liters": _r(_q(pos, 0.95)),
            "p99_active_liters": _r(_q(pos, 0.99)),
        }
    return prof


def build_profiles(hourly: pd.DataFrame, slots: pd.DataFrame | None = None,
                   start: pd.Timestamp = config.TRAIN_START,
                   end: pd.Timestamp = config.TRAIN_END) -> dict:
    """Tüm daireler + bina geneli (yedek) profil."""
    h = select_period(hourly, start, end)
    s = select_period(slots, start, end, "slot_utc") if slots is not None else None
    apartments = {}
    for apt, grp in h.groupby("apartment"):
        sg = s[s["apartment"] == apt] if s is not None else None
        apartments[apt] = build_apartment_profile(grp, sg)
    # Bina geneli tipik daire profili: daire profillerinin medyanı
    def med(key):
        return _r(np.nanmedian(np.array([p[key] for p in apartments.values()], dtype=float), axis=0))
    global_profile = {
        "hourly_mean_liters": med("hourly_mean_liters"),
        "hourly_p95_liters": med("hourly_p95_liters"),
        "hourly_active_probability": med("hourly_active_probability"),
        "daily": {"mean_liters": _r(np.nanmedian([p["daily"]["mean_liters"] for p in apartments.values()]))},
        "night": {"mean_liters_per_hour": _r(np.nanmedian([p["night"]["mean_liters_per_hour"] for p in apartments.values()]))},
        "description": "Bilinmeyen/yeni daireler için bina geneli medyan profil",
    }
    return {
        "profile_period_local": {"start": str(start), "end_exclusive": str(end)},
        "timezone": config.LOCAL_TZ,
        "unit": "liters",
        "method": ("Yalnızca eğitim dönemindeki tamamen gözlenen saatler/günler kullanılmıştır. "
                   "Gözlenmeyen (kesinti/veri kaybı) saatler hariç tutulmuş, sıfırla doldurulmamıştır."),
        "apartments": apartments,
        "global": global_profile,
    }


def save_profiles(profiles: Mapping, path=config.PROFILES_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


def load_profiles(path=config.PROFILES_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_profile(profiles: Mapping, apartment_id: str) -> tuple[dict, bool]:
    """(profil, daireye_özel_mi) döndürür; bilinmeyen dairede bina geneli profil."""
    apt = profiles["apartments"].get(apartment_id)
    return (apt, True) if apt is not None else (profiles["global"], False)


if __name__ == "__main__":
    from .data_preprocessing import load_processed
    r = load_processed()
    p = build_profiles(r.hourly, r.slots)
    save_profiles(p)
    print("Profil kaydedildi:", config.PROFILES_FILE, "daire sayısı:", len(p["apartments"]))
