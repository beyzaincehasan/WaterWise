"""WaterWise AI modülü – backend için örnek kullanım.

Çalıştırma (proje kök dizininde):
    venv\\Scripts\\python.exe examples\\backend_usage_example.py

Bu betik veritabanı yerine `data/processed/apartment_records.parquet` dosyasını
kullanır. Backend'de aynı kayıtlar PostgreSQL'den okunacaktır.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.predict import WaterWiseInputError, load_detector, predict_anomaly  # noqa: E402
from src.synthetic_anomalies import make_demo_leak_records  # noqa: E402

LOCAL_TZ = "Europe/Stockholm"


def fetch_records_from_db(apartment_id: str, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    """Backend'deki SELECT sorgusunun yerine geçen örnek fonksiyon.

    SELECT timestamp_utc, value_liters FROM consumption
    WHERE apartment = :apt AND timestamp_utc >= :start AND timestamp_utc < :end
    """
    df = pd.read_parquet(ROOT / "data" / "processed" / "apartment_records.parquet",
                         columns=["apartment", "timestamp_utc", "value_liters"])
    df = df[(df["apartment"] == apartment_id) & (df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end)]
    return [{"timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "consumption_liters": float(v)}
            for t, v in zip(df["timestamp_utc"], df["value_liters"])]


def main() -> None:
    detector = load_detector()           # uygulama açılışında BİR KEZ
    print("Model sürümü:", detector.model_version, "| bilinen daire sayısı:", len(detector.known_apartments()))

    apartment = "APT_011"
    target = pd.Timestamp("2022-11-24 03:00", tz=LOCAL_TZ)      # değerlendirilecek saat
    history_start = target - pd.Timedelta(days=28)               # 28 gün geçmiş bağlam
    records = fetch_records_from_db(apartment, history_start, target + pd.Timedelta(hours=1))
    print(f"\n{apartment}: {len(records)} kayıt ({history_start:%Y-%m-%d} → {target:%Y-%m-%d %H:%M})")

    # 1) Normal bir saat için tahmin
    result = predict_anomaly(apartment, records, target_timestamp=target.isoformat(),
                             history_start=history_start.isoformat(), detector=detector)
    print("\n[1] Gerçek veri, tek saat:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 2) Demo senaryosu: 01:00'dan itibaren 18 L/saat sürekli akış eklenir
    leak = make_demo_leak_records(target - pd.Timedelta(hours=2), hours=3, rate_l_per_hour=18)
    demo = predict_anomaly(apartment, records + leak, target_timestamp=target.isoformat(),
                           history_start=history_start.isoformat(), detector=detector)
    print("\n[2] Demo: gece sürekli akış eklendi:")
    print(json.dumps({k: demo[k] for k in ["timestamp_local", "consumption_liters", "status",
                                           "anomaly_score", "message", "reasons"]}, ensure_ascii=False, indent=2))

    # 3) Dashboard için son 24 saatin toplu değerlendirmesi
    rows = detector.evaluate(apartment, records + leak, start=target - pd.Timedelta(hours=23), end=target,
                             history_start=history_start)
    print("\n[3] Son 24 saat (yerel saat | L | durum | skor):")
    for r in rows:
        print(f"  {r['timestamp_local'][:16]} | {r['consumption_liters']:6.1f} | {r['status']:8s} | {r['anomaly_score']:.3f}")

    # 4) Hata yönetimi
    print("\n[4] Hatalı girdi örneği:")
    try:
        predict_anomaly(apartment, [{"timestamp": "2022-11-24T02:00:00Z", "consumption_liters": -5}],
                        detector=detector)
    except WaterWiseInputError as e:
        print(f"  WaterWiseInputError code={e.code!r} message={e.message!r}")


if __name__ == "__main__":
    main()
