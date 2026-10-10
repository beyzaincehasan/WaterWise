"""Ortak pytest fikstürleri."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

HEADER = ("timestamp;date;hour;day_of_week;day_name;month;year;sensor_id;apartment;cluster_name;"
          "room_number;room_type;type;attached_to;value;aggregated_value")


def _row(ts: str, sensor: str, apt: str | None, value: float, agg: float,
         room_type="Bathroom", fixture="Toilet", wtype="cold water consumption") -> str:
    t = pd.Timestamp(ts)
    cluster = "CL_A" if apt else ""
    return ";".join([
        t.strftime("%Y-%m-%d %H:%M:%S"), t.strftime("%Y-%m-%d"), str(t.hour), str(t.dayofweek),
        t.day_name(), str(t.month), str(t.year), sensor, apt or "", cluster, "R001", room_type,
        wtype, fixture, f"{value:.3f}", f"{agg:.3f}"])


@pytest.fixture
def small_csv(tmp_path: Path) -> Path:
    """Gerçek CSV biçiminde küçük örnek dosya (DST, tekrar, ortak alan, veri kaybı içerir)."""
    rows = [
        _row("2021-10-30 22:00:00", "S0001", "APT_001", 0.002, 10.002),
        _row("2021-10-30 22:00:00", "S0001", "APT_001", 0.002, 10.002),      # tam tekrar
        _row("2021-10-31 01:50:00", "S0001", "APT_001", 0.001, 10.003),
        _row("2021-10-31 02:40:00", "S0001", "APT_001", 0.001, 10.004),      # DST ilk geçiş
        _row("2021-10-31 02:10:00", "S0001", "APT_001", 0.001, 10.005),      # DST ikinci geçiş
        _row("2021-10-31 03:00:00", "S0001", "APT_001", 0.003, 10.008),
        _row("2021-10-31 08:00:00", "S0001", "APT_001", 0.004, 10.062),      # 50 L kaydedilmemiş (veri kaybı)
        _row("2021-10-31 09:00:00", "S0002", None, 0.010, 5.010, "Shared bathroom", "Shower"),
        _row("2021-10-31 09:10:00", "S0002", None, 0.020, 5.030, "Shared bathroom", "Shower"),
    ]
    p = tmp_path / "sample.csv"
    p.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def make_records(start_local: str, hours: int, seed: int = 0, day_rate: float = 4.0,
                 night_rate: float = 0.3) -> pd.DataFrame:
    """Tekrar üretilebilir sahte 10 dk kayıtları (gündüz yoğun, gece seyrek)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(pd.Timestamp(start_local, tz=config.LOCAL_TZ), periods=hours * 6, freq="10min")
    h = idx.hour
    lam = np.where((h >= 0) & (h < 6), night_rate, day_rate) / 6
    liters = rng.poisson(lam * 3)
    df = pd.DataFrame({"timestamp_utc": idx.tz_convert("UTC"), "value_liters": liters.astype(float)})
    return df[df["value_liters"] > 0].reset_index(drop=True)


@pytest.fixture(scope="session")
def detector():
    if not config.MODEL_FILE.exists():
        pytest.skip("Eğitilmiş model yok; önce python -m src.train_model çalıştırın")
    from src.predict import WaterWiseAnomalyDetector
    return WaterWiseAnomalyDetector()
