"""Kontrollü, tekrar üretilebilir sentetik anomali senaryoları.

Veri setinde doğrulanmış kaçak etiketi olmadığından model, gerçek tüketim
serisine eklenen sentetik olaylarla değerlendirilir. Sentetik veri gerçek
veriden AYRI tutulur: olaylar yalnızca bellekteki kopyaya eklenir ve olay
kataloğu `data/synthetic/` altına kaydedilir; işlenmiş gerçek veriler değişmez.

Enjeksiyon 10 dakikalık slot düzeyinde yapılır; ardından eğitimde kullanılan
özellik hattının aynısı (slots_to_hourly → compute_features) çalışır.
Eklenen miktarlar sayaçların 1 L çözünürlüğüne uygun olarak tam litredir.

Senaryolar (parametreler SCENARIOS sözlüğünde)
---------------------------------------------
S1 night_continuous_flow : 02:00–05:00 (yerel) boyunca sabit debili sürekli akış,
                           6–30 L/saat (ör. akan rezervuar / açık kalmış musluk).
S2 high_consumption      : Gündüz (07–21) 2 saat boyunca, o saatin normal
                           p95 değerinin 2–4 katı ek tüketim.
S3 unusual_hour          : Dairenin en az aktif olduğu saatlerden birinde
                           20–30 dk süren 30–80 L yoğun kullanım.
S4 short_spike           : Tek 10 dakikalık slotta, dairenin aktif slot p99
                           değerinin 2–4 katı (en az 40 L, en çok 300 L) ani artış.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import config

SCENARIOS = {
    "S1_night_continuous_flow": {
        "description": "Gece 02:00-05:00 (yerel) sürekli akış",
        "start_hour_local": 2, "duration_hours": 3,
        "rate_l_per_hour": [6.0, 30.0],
    },
    "S2_high_consumption": {
        "description": "Gündüz 2 saat, saatlik normal p95'in 2-4 katı ek tüketim",
        "start_hour_range_local": [7, 21], "duration_hours": 2,
        "multiplier": [2.0, 4.0], "min_hourly_base_l": 10.0, "max_l_per_slot": 150.0,
    },
    "S3_unusual_hour": {
        "description": "En az aktif saatlerden birinde 20-30 dk yoğun kullanım",
        "candidate_hours": "dairenin aktiflik olasılığı en düşük 6 saati",
        "n_slots": [2, 3], "volume_l": [30.0, 80.0],
    },
    "S4_short_spike": {
        "description": "Tek 10 dk slotta ani yüksek tüketim",
        "multiplier": [2.0, 4.0], "min_l": 40.0, "max_l": 300.0,
    },
}


@dataclass
class SyntheticEvent:
    event_id: str
    scenario: str
    apartment: str
    start_utc: pd.Timestamp
    n_slots: int
    slot_liters: list[float]
    total_liters: float
    params: dict

    @property
    def end_utc(self) -> pd.Timestamp:   # son slotun başlangıcı
        return self.start_utc + pd.Timedelta(minutes=config.SLOT_MINUTES * (self.n_slots - 1))

    def hours_utc(self) -> pd.DatetimeIndex:
        return pd.date_range(self.start_utc.floor("h"), self.end_utc.floor("h"), freq="h")

    def to_record(self) -> dict:
        d = asdict(self)
        d["start_utc"] = self.start_utc.isoformat()
        d["start_local"] = self.start_utc.tz_convert(config.LOCAL_TZ).isoformat()
        d["end_utc"] = self.end_utc.isoformat()
        return d


def pulse_liters(rate_l_per_hour: float, n_slots: int, rng: np.random.Generator) -> np.ndarray:
    """Sabit debiyi 1 L çözünürlüklü darbe sayaçlarına uygun slot değerlerine çevirir."""
    per_slot = rate_l_per_hour / config.SLOTS_PER_HOUR
    phase = rng.uniform(0, 1)
    cum = np.floor(phase + per_slot * np.arange(n_slots + 1))
    return np.diff(cum)


def _split_volume(total: float, n: int, rng: np.random.Generator, cap: float | None = None) -> np.ndarray:
    w = rng.dirichlet(np.full(n, 4.0))
    vals = np.round(total * w)
    if cap is not None:
        vals = np.minimum(vals, cap)
    vals[vals < 1] = 1
    return vals


def _local_start(day_local: pd.Timestamp, hour: int, minute: int = 0) -> pd.Timestamp:
    ts = pd.Timestamp(day_local.year, day_local.month, day_local.day, hour, minute)
    return ts.tz_localize(config.LOCAL_TZ, ambiguous=True, nonexistent="shift_forward").tz_convert("UTC")


# Ana değerlendirmeye girmeyen stres testi: sayaç çözünürlüğünün altındaki
# (< 6 L/saat → her 10 dk'da 1 darbeden az) düşük debili gece sızıntıları.
STRESS_SCENARIOS = {
    "S1L_low_rate_night_flow": {
        "description": "Gece 02:00-05:00 düşük debili sızıntı (1-6 L/saat, darbeler aralıklı)",
        "start_hour_local": 2, "duration_hours": 3,
        "rate_l_per_hour": [1.0, 6.0],
    },
}
ALL_SCENARIOS = {**SCENARIOS, **STRESS_SCENARIOS}


def make_event(scenario: str, apartment: str, day_local: pd.Timestamp, profile: dict,
               rng: np.random.Generator, event_id: str) -> SyntheticEvent:
    p = ALL_SCENARIOS[scenario]
    if scenario in ("S1_night_continuous_flow", "S1L_low_rate_night_flow"):
        rate = float(rng.uniform(*p["rate_l_per_hour"]))
        n = p["duration_hours"] * config.SLOTS_PER_HOUR
        start = _local_start(day_local, p["start_hour_local"])
        liters = pulse_liters(rate, n, rng)
        params = {"rate_l_per_hour": round(rate, 2)}
    elif scenario == "S2_high_consumption":
        h0 = int(rng.integers(p["start_hour_range_local"][0], p["start_hour_range_local"][1]))
        m = float(rng.uniform(*p["multiplier"]))
        p95 = np.asarray(profile["hourly_p95_liters"], dtype=float)
        n_h = p["duration_hours"]
        liters = []
        for k in range(n_h):
            base = max(float(np.nan_to_num(p95[(h0 + k) % 24])), p["min_hourly_base_l"])
            liters.append(_split_volume(m * base, config.SLOTS_PER_HOUR, rng, p["max_l_per_slot"]))
        liters = np.concatenate(liters)
        n = len(liters)
        start = _local_start(day_local, h0)
        params = {"start_hour_local": h0, "multiplier": round(m, 2)}
    elif scenario == "S3_unusual_hour":
        prob = np.nan_to_num(np.asarray(profile["hourly_active_probability"], dtype=float), nan=0.0)
        candidates = np.argsort(prob, kind="stable")[:6]
        h0 = int(rng.choice(candidates))
        n = int(rng.integers(p["n_slots"][0], p["n_slots"][1] + 1))
        vol = float(rng.uniform(*p["volume_l"]))
        minute = int(rng.integers(0, config.SLOTS_PER_HOUR - n + 1)) * config.SLOT_MINUTES
        start = _local_start(day_local, h0, minute)
        liters = _split_volume(vol, n, rng)
        params = {"hour_local": h0, "volume_l": round(vol, 1),
                  "hour_active_probability": round(float(prob[h0]), 4)}
    elif scenario == "S4_short_spike":
        h0 = int(rng.integers(0, 24))
        minute = int(rng.integers(0, config.SLOTS_PER_HOUR)) * config.SLOT_MINUTES
        m = float(rng.uniform(*p["multiplier"]))
        p99 = float((profile.get("slot_10min") or {}).get("p99_active_liters") or 20.0)
        vol = float(np.clip(round(m * p99), p["min_l"], p["max_l"]))
        start = _local_start(day_local, h0, minute)
        liters = np.array([vol])
        n = 1
        params = {"hour_local": h0, "multiplier": round(m, 2), "slot_p99_l": p99}
    else:
        raise ValueError(f"Bilinmeyen senaryo: {scenario}")
    liters = np.asarray(liters, dtype=float)
    return SyntheticEvent(event_id, scenario, apartment, start, int(n), liters.tolist(),
                          float(liters.sum()), params)


def inject(slots: pd.DataFrame, event: SyntheticEvent) -> pd.DataFrame:
    """Olayı bir dairenin slot serisinin KOPYASINA ekler (gözlenen slotlara)."""
    out = slots.copy()
    times = pd.date_range(event.start_utc, periods=event.n_slots, freq=f"{config.SLOT_MINUTES}min")
    pos = out["slot_utc"].searchsorted(times)
    if (pos >= len(out)).any() or not (out["slot_utc"].to_numpy()[pos] == times.to_numpy()).all():
        raise ValueError("Olay slotları seride bulunamadı")
    col = out.columns.get_loc("liters")
    vals = out.iloc[pos, col].to_numpy()
    if np.isnan(vals).any():
        raise ValueError("Olay gözlenmeyen bir aralığa denk geliyor")
    out.iloc[pos, col] = vals + np.asarray(event.slot_liters)
    for c in ("active", "run_slots"):
        if c in out:
            out = out.drop(columns=c)
    return out


def generate_events(hourly: pd.DataFrame, profiles: dict, start: pd.Timestamp, end: pd.Timestamp,
                    n_per_scenario: int, seed: int, prefix: str,
                    history_days: int = config.HISTORY_DAYS,
                    scenarios: list[str] | None = None) -> list[SyntheticEvent]:
    """Dönem içinde, olay günü ve önceki `history_days` gün yeterince gözlenmiş
    daire-günlerine rastgele olaylar yerleştirir."""
    rng = np.random.default_rng(seed)
    h = hourly[(hourly["hour_utc"] >= start.tz_convert("UTC")) & (hourly["hour_utc"] < end.tz_convert("UTC"))]
    local = h["hour_utc"].dt.tz_convert(config.LOCAL_TZ)
    h = h.assign(day=local.dt.tz_localize(None).dt.normalize())
    day_obs = h.groupby(["apartment", "day"])["observed"].agg(["sum", "size"])
    # Tam gün: tüm saatler gözlenmiş VE gün serinin kesik bir ucu değil (>= 23 saat; DST günleri 23/25)
    full = day_obs[(day_obs["sum"] == day_obs["size"]) & (day_obs["size"] >= 23)].reset_index()

    # Geçmiş bağlam: önceki history_days günün en az %70'i gözlenmiş olmalı
    all_local = hourly["hour_utc"].dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()
    obs_day = hourly.assign(day=all_local).groupby(["apartment", "day"])["observed"].mean()
    eligible = []
    for apt, grp in full.groupby("apartment"):
        s = obs_day.loc[apt]
        s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"), fill_value=0.0)
        hist = s.rolling(history_days, min_periods=history_days).mean().shift(1)
        for d in grp["day"]:
            if hist.get(d, 0) >= 0.7:
                eligible.append((apt, d))
    if not eligible:
        raise ValueError("Uygun daire-günü bulunamadı")
    events = []
    for scen in (scenarios or list(SCENARIOS)):
        idx = rng.choice(len(eligible), size=n_per_scenario, replace=len(eligible) < n_per_scenario)
        for k, i in enumerate(idx):
            apt, day = eligible[i]
            prof = profiles["apartments"].get(apt, profiles["global"])
            events.append(make_event(scen, apt, day, prof, rng, f"{prefix}_{scen.split('_')[0]}_{k:04d}"))
    return events


def save_events(events: list[SyntheticEvent], name: str) -> None:
    config.SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    recs = [e.to_record() for e in events]
    pd.DataFrame(recs).to_csv(config.SYNTHETIC_DIR / f"{name}_events.csv", index=False)
    with open(config.SYNTHETIC_DIR / "scenario_parameters.json", "w", encoding="utf-8") as f:
        json.dump({"main": SCENARIOS, "stress_test": STRESS_SCENARIOS}, f, ensure_ascii=False, indent=2)


def make_demo_leak_records(start: str | pd.Timestamp, hours: float = 3.0,
                           rate_l_per_hour: float = 18.0, seed: int = 0) -> list[dict]:
    """Demo için sürekli akış (kaçak) kayıtları üretir.

    Backend, demo sırasında bu kayıtları gerçek kayıtların arkasına ekleyerek
    dashboard'un Normal → Anormal geçişini gösterebilir. Çıktı, predict_anomaly
    `records` biçimindedir: [{"timestamp": ISO-8601 UTC, "consumption_liters": float}, ...]
    """
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp(start)
    if t0.tzinfo is None:
        t0 = t0.tz_localize(config.LOCAL_TZ)
    t0 = t0.tz_convert("UTC").floor(f"{config.SLOT_MINUTES}min")
    n = int(round(hours * config.SLOTS_PER_HOUR))
    liters = pulse_liters(rate_l_per_hour, n, rng)
    times = pd.date_range(t0, periods=n, freq=f"{config.SLOT_MINUTES}min")
    return [{"timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "consumption_liters": float(v)}
            for t, v in zip(times, liters) if v > 0]
