"""WaterWise Backend - Demo Verisi Tohumlama Betiği (seed_demo_data.py).

Ham CSV dosyası henüz mevcut olmadığında veya hızlı geliştirme/sunum için:
- 28 dairenin (APT_001..APT_028) tamamını 'apartments' tablosuna kaydeder.
- 'models/normal_profiles.json' dosyasındaki gerçek tüketim istatistiklerini baz alarak
  APT_011 (ve APT_001..APT_005) için 28 günlük gerçekçi 10 dakikalık su tüketim kayıtları üretir.
- Duş, Musluk, Tuvalet, Makine gibi armatür ve sıcak/soğuk su dağılımlarını ekler.
- Değerleri m³ ve Litre (value_liters = value_m3 * 1000) olarak saklar.
- Zaman damgalarını Europe/Stockholm'den UTC'ye dönüştürerek kaydeder.

Kullanım:
    python backend/scripts/seed_demo_data.py
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime
from pathlib import Path

# Dizin yolları
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import SessionLocal, init_db
from backend.app.models import Apartment, ConsumptionRecord
from src.feature_engineering import to_utc

LOCAL_TZ = settings.LOCAL_TIMEZONE


def seed_apartments(db: Session, profiles_path: Path) -> None:
    """Tüm bilinen 28 daireyi 'apartments' tablosuna ekler."""
    print("[*] Daireler (apartments) tablosu güncelleniyor...")
    known_apts = [f"APT_{i:03d}" for i in range(1, 29)]
    
    cluster_map = {
        "APT_001": "CL_A", "APT_002": "CL_A", "APT_003": "CL_A",
        "APT_004": "CL_B", "APT_005": "CL_B", "APT_006": "CL_B",
        "APT_007": "CL_C", "APT_008": "CL_C", "APT_009": "CL_C",
        "APT_010": "CL_D", "APT_011": "CL_D", "APT_012": "CL_D",
    }

    for apt_id in known_apts:
        existing = db.query(Apartment).filter_by(id=apt_id).first()
        if not existing:
            c_name = cluster_map.get(apt_id, "CL_E")
            db.add(Apartment(id=apt_id, cluster_name=c_name, has_profile=True))
    db.commit()
    print(f"[+] 28 daire veritabanına kaydedildi.")


def generate_records_for_apartment(apt_id: str, profile: dict, start_time: pd.Timestamp, end_time: pd.Timestamp) -> list[dict]:
    """Belirli bir daire için profil istatistiklerine uygun 10 dakikalık kayıtlar üretir."""
    records = []
    hourly_mean = profile.get("hourly_mean_liters", [0.5] * 24)
    hourly_prob = profile.get("hourly_active_probability", [0.2] * 24)
    
    current_time = start_time
    cumulative_m3 = 10.0 + random.uniform(1.0, 50.0)

    # 10 dakikalık frekansta adımlar
    time_index = pd.date_range(start_time, end_time, freq="10min")
    rng = np.random.default_rng(seed=int(apt_id.split("_")[1]))

    for ts_local in time_index:
        h = ts_local.hour
        mean_l = hourly_mean[h]
        prob = hourly_prob[h] if hourly_prob[h] is not None else 0.2

        # Gece saatlerinde tüketim ihtimali çok düşüktür
        if 0 <= h < 6:
            prob = max(prob * 0.3, 0.02)

        # Bu 10 dakikalık dilimde tüketim oldu mu?
        if rng.random() < prob:
            # Armatür türü seçimi
            r = rng.random()
            if 6 <= h <= 9 or 19 <= h <= 22:
                # Sabah veya akşam: duş olasılığı yüksek
                if r < 0.35:
                    fixture = "Shower"
                    category = "Duş"
                    liters = round(rng.uniform(15.0, 45.0), 1)
                    water_type = "hot" if rng.random() < 0.7 else "cold"
                elif r < 0.65:
                    fixture = "Washbasin"
                    category = "Musluk"
                    liters = round(rng.uniform(2.0, 6.0), 1)
                    water_type = "hot" if rng.random() < 0.5 else "cold"
                elif r < 0.85:
                    fixture = "Toilet"
                    category = "Tuvalet"
                    liters = round(rng.choice([3.0, 6.0]), 1)
                    water_type = "cold"
                else:
                    fixture = "Kitchen tap"
                    category = "Musluk"
                    liters = round(rng.uniform(1.0, 8.0), 1)
                    water_type = "hot" if rng.random() < 0.4 else "cold"
            else:
                if r < 0.45:
                    fixture = "Toilet"
                    category = "Tuvalet"
                    liters = round(rng.choice([3.0, 6.0]), 1)
                    water_type = "cold"
                elif r < 0.80:
                    fixture = "Kitchen tap"
                    category = "Musluk"
                    liters = round(rng.uniform(1.0, 7.0), 1)
                    water_type = "hot" if rng.random() < 0.4 else "cold"
                elif r < 0.95:
                    fixture = "Dishwasher"
                    category = "Makine"
                    liters = round(rng.uniform(8.0, 15.0), 1)
                    water_type = "cold"
                else:
                    fixture = "Washbasin"
                    category = "Musluk"
                    liters = round(rng.uniform(1.0, 4.0), 1)
                    water_type = "cold"

            # Değerleri hesapla
            val_m3 = round(liters / 1000.0, 6)
            cumulative_m3 += val_m3

            records.append({
                "apartment": apt_id,
                "timestamp_local_str": ts_local.strftime("%Y-%m-%d %H:%M:%S"),
                "value_liters": liters,
                "value_m3": val_m3,
                "aggregated_value": round(cumulative_m3, 6),
                "sensor_id": f"S{int(apt_id.split('_')[1]):04d}",
                "water_type": water_type,
                "attached_to": fixture,
                "usage_category": category,
            })

    return records


def seed_demo_data(target_apartments: list[str] | None = None) -> None:
    """Demo verisi üretir ve veritabanına aktarır."""
    init_db()
    db: Session = SessionLocal()

    if target_apartments is None:
        # APT_011 (örnek senaryodaki daire) + ilk birkaç daire
        target_apartments = ["APT_011", "APT_001", "APT_002", "APT_003", "APT_004", "APT_005"]

    profiles_file = settings.PROFILES_FILE
    if not profiles_file.exists():
        print(f"[!] normal_profiles.json bulunamadı: {profiles_file}")
        return

    with open(profiles_file, encoding="utf-8") as f:
        profiles_data = json.load(f)

    seed_apartments(db, profiles_file)

    # 28 günlük geçmiş + hedef saat (backend_usage_example.py ile uyumlu: 2022-10-27 -> 2022-11-24)
    target_time_local = pd.Timestamp("2022-11-24 04:00", tz=LOCAL_TZ)
    history_start_local = target_time_local - pd.Timedelta(days=29)

    print(f"[*] Demo kayıtları oluşturuluyor:")
    print(f"    - Tarih aralığı: {history_start_local:%Y-%m-%d %H:%M} -> {target_time_local:%Y-%m-%d %H:%M} (Yerel: {LOCAL_TZ})")
    print(f"    - Daireler: {', '.join(target_apartments)}")

    all_records = []
    for apt_id in target_apartments:
        prof = profiles_data["apartments"].get(apt_id, profiles_data["global"])
        apt_recs = generate_records_for_apartment(apt_id, prof, history_start_local, target_time_local)
        all_records.extend(apt_recs)
        print(f"    - {apt_id}: {len(apt_recs):,} sensör kaydı üretildi.")

    print(f"[*] Toplam {len(all_records):,} kayıt için UTC dönüşümü yapılıyor...")
    df = pd.DataFrame(all_records)
    # Yerel saatten UTC'ye DST duyarlı çeviri
    df["timestamp_utc"] = to_utc(df["timestamp_local_str"])
    df["timestamp_local"] = pd.to_datetime(df["timestamp_local_str"])

    print("[*] Veritabanına toplu kayıt ekleniyor...")
    records_to_insert = []
    for row in df.itertuples(index=False):
        records_to_insert.append({
            "apartment": row.apartment,
            "timestamp_utc": row.timestamp_utc.to_pydatetime(),
            "timestamp_local": row.timestamp_local.to_pydatetime(),
            "value_liters": float(row.value_liters),
            "value_m3": float(row.value_m3),
            "aggregated_value": float(row.aggregated_value),
            "sensor_id": row.sensor_id,
            "water_type": row.water_type,
            "attached_to": row.attached_to,
            "usage_category": row.usage_category,
        })

    # Eski demo kayıtlarını temizle ve yenilerini ekle
    for apt_id in target_apartments:
        db.query(ConsumptionRecord).filter(ConsumptionRecord.apartment == apt_id).delete()
    db.commit()

    # Bulk insert
    batch_size = 10000
    for i in range(0, len(records_to_insert), batch_size):
        batch = records_to_insert[i:i + batch_size]
        db.bulk_insert_mappings(ConsumptionRecord, batch)
        db.commit()

    count = db.query(ConsumptionRecord).count()
    apt_count = db.query(Apartment).count()
    print(f"[+] Başarılı! Veritabanında {apt_count} daire ve toplam {count:,} tüketim kaydı mevcut.")
    db.close()


if __name__ == "__main__":
    seed_demo_data()

