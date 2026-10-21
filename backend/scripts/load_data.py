"""WaterWise Backend - Veri Yükleme Betiği (load_data.py).

Ham CSV veya işlenmiş Parquet dosyasını okur:
- 'value' m³ değerini 1000 ile çarparak litreye çevirir (value_liters).
- 'aggregated_value' kümülatif sayaç endeksi olarak saklanır, tüketime eklenmez.
- Europe/Stockholm yerel saat damgalarını DST-doğru şekilde UTC'ye dönüştürür.
- Kayıtları toplu (bulk) olarak SQLite veya PostgreSQL veritabanına yazar.
- Daire tablosunu (apartments) otomatik olarak günceller.

Kullanım:
    python backend/scripts/load_data.py --csv data/HSB_Living_Lab_Water_Consumption_Anonymized.csv
veya
    python backend/scripts/load_data.py --parquet data/processed/apartment_records.parquet
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Proje kök dizinini ve backend dizinini sys.path'e ekle
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

USAGE_CATEGORY_MAP = {
    "Shower": "Duş",
    "Kitchen tap": "Musluk",
    "Washbasin": "Musluk",
    "Toilet": "Tuvalet",
    "Washing machine": "Makine",
    "Dishwasher": "Makine",
    "Other": "Diğer",
}

WATER_TYPE_MAP = {
    "cold water consumption": "cold",
    "hot water consumption": "hot",
}


def load_from_parquet(path: Path, db: Session, batch_size: int = 15000) -> None:
    """İşlenmiş parquet dosyasından hızlı veri aktarımı."""
    print(f"[*] Parquet dosyası okunuyor: {path}")
    df = pd.read_parquet(path)
    print(f"[*] Toplam {len(df):,} satır bulundu.")

    # Gerekli sütun kontrolleri
    if "timestamp_utc" not in df.columns:
        df["timestamp_utc"] = to_utc(df["timestamp"])
    else:
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)

    if "value_liters" not in df.columns and "value" in df.columns:
        df["value_liters"] = (df["value"] * 1000.0).round(3)

    insert_records_dataframe(df, db, batch_size=batch_size)


def load_from_csv(path: Path, db: Session, batch_size: int = 15000) -> None:
    """Ham CSV dosyasından (HSB_Living_Lab_Water_Consumption_Anonymized.csv) veri aktarımı."""
    print(f"[*] CSV dosyası okunuyor (noktalı virgül ayırıcı): {path}")
    df = pd.read_csv(
        path,
        sep=";",
        dtype={
            "sensor_id": "str",
            "apartment": "str",
            "cluster_name": "str",
            "room_number": "str",
        },
    )
    print(f"[*] CSV okundu. Satır sayısı: {len(df):,}")

    # 1. Tam tekrar satırları ayıkla
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        print(f"[*] {dup_count} adet yinelenen satır temizleniyor...")
        df = df.drop_duplicates()

    # 2. Zaman damgalarını yerel saatten (Europe/Stockholm) UTC'ye dönüştür
    print("[*] Zaman damgaları UTC'ye dönüştürülüyor (Europe/Stockholm DST)...")
    df["timestamp_utc"] = to_utc(df["timestamp"])
    df["timestamp_local"] = pd.to_datetime(df["timestamp"])

    # 3. 'value' m³ değerini litreye çevir (value * 1000)
    print("[*] 'value' (m³) -> 'value_liters' (L) hesaplanıyor...")
    df["value_m3"] = df["value"].astype(float)
    df["value_liters"] = (df["value_m3"] * 1000.0).round(3)

    # 4. Kategori ve su tipi eşleştirmeleri
    if "attached_to" in df.columns:
        df["usage_category"] = df["attached_to"].map(USAGE_CATEGORY_MAP).fillna("Diğer")
    if "type" in df.columns:
        df["water_type"] = df["type"].map(WATER_TYPE_MAP).fillna("unknown")

    insert_records_dataframe(df, db, batch_size=batch_size)


def insert_records_dataframe(df: pd.DataFrame, db: Session, batch_size: int = 15000) -> None:
    """Hazırlanan DataFrame'i toplu olarak veritabanına ekler."""
    # Daire tablosunu güncelle
    unique_apts = df["apartment"].dropna().unique()
    print(f"[*] Tespit edilen daire sayısı: {len(unique_apts)}")
    for apt in sorted(unique_apts):
        existing = db.query(Apartment).filter_by(id=apt).first()
        if not existing:
            c_name = df.loc[df["apartment"] == apt, "cluster_name"].dropna().iloc[0] if "cluster_name" in df.columns else None
            db.add(Apartment(id=apt, cluster_name=c_name, has_profile=True))
    db.commit()

    total_rows = len(df)
    print(f"[*] Veritabanına {total_rows:,} kayıt ekleniyor (Parti boyutu: {batch_size:,})...")
    t0 = time.time()

    inserted = 0
    records_to_insert = []

    for row in df.itertuples(index=False):
        # Alanları hazırla
        r_dict = {
            "apartment": getattr(row, "apartment", None) if pd.notna(getattr(row, "apartment", None)) else None,
            "timestamp_utc": getattr(row, "timestamp_utc").to_pydatetime() if pd.notna(getattr(row, "timestamp_utc", None)) else None,
            "timestamp_local": getattr(row, "timestamp_local").to_pydatetime() if hasattr(row, "timestamp_local") and pd.notna(getattr(row, "timestamp_local", None)) else None,
            "value_liters": float(getattr(row, "value_liters", 0.0)),
            "value_m3": float(getattr(row, "value_m3", 0.0)) if hasattr(row, "value_m3") and pd.notna(getattr(row, "value_m3", None)) else None,
            "aggregated_value": float(getattr(row, "aggregated_value", 0.0)) if hasattr(row, "aggregated_value") and pd.notna(getattr(row, "aggregated_value", None)) else None,
            "sensor_id": getattr(row, "sensor_id", None) if hasattr(row, "sensor_id") and pd.notna(getattr(row, "sensor_id", None)) else None,
            "cluster_name": getattr(row, "cluster_name", None) if hasattr(row, "cluster_name") and pd.notna(getattr(row, "cluster_name", None)) else None,
            "room_number": getattr(row, "room_number", None) if hasattr(row, "room_number") and pd.notna(getattr(row, "room_number", None)) else None,
            "room_type": getattr(row, "room_type", None) if hasattr(row, "room_type") and pd.notna(getattr(row, "room_type", None)) else None,
            "water_type": getattr(row, "water_type", None) if hasattr(row, "water_type") and pd.notna(getattr(row, "water_type", None)) else None,
            "attached_to": getattr(row, "attached_to", None) if hasattr(row, "attached_to") and pd.notna(getattr(row, "attached_to", None)) else None,
            "usage_category": getattr(row, "usage_category", "Diğer") if hasattr(row, "usage_category") and pd.notna(getattr(row, "usage_category", None)) else "Diğer",
        }
        records_to_insert.append(r_dict)

        if len(records_to_insert) >= batch_size:
            db.bulk_insert_mappings(ConsumptionRecord, records_to_insert)
            db.commit()
            inserted += len(records_to_insert)
            records_to_insert.clear()
            elapsed = time.time() - t0
            print(f"    - Aktarılan: {inserted:,} / {total_rows:,} (%{100 * inserted / total_rows:.1f}) [{elapsed:.1f} sn]")

    if records_to_insert:
        db.bulk_insert_mappings(ConsumptionRecord, records_to_insert)
        db.commit()
        inserted += len(records_to_insert)

    elapsed = time.time() - t0
    print(f"[+] Başarıyla tamamlandı! Toplam {inserted:,} satır {elapsed:.1f} saniyede kaydedildi.")


def main():
    parser = argparse.ArgumentParser(description="WaterWise Su Tüketim Verisi Yükleyici")
    parser.add_argument("--csv", type=str, help="Ham CSV dosyası yolu (HSB Living Lab)")
    parser.add_argument("--parquet", type=str, help="İşlenmiş parquet dosyası yolu")
    parser.add_argument("--batch-size", type=int, default=15000, help="Toplu ekleme parti büyüklüğü")
    args = parser.parse_args()

    # Tabloları oluştur
    print("[*] Veritabanı tabloları başlatılıyor...")
    init_db()

    db: Session = SessionLocal()
    try:
        csv_path = Path(args.csv) if args.csv else PROJECT_ROOT / "data" / "HSB_Living_Lab_Water_Consumption_Anonymized.csv"
        parquet_path = Path(args.parquet) if args.parquet else PROJECT_ROOT / "data" / "processed" / "apartment_records.parquet"

        if args.parquet or (not args.csv and parquet_path.exists()):
            load_from_parquet(parquet_path, db, batch_size=args.batch_size)
        elif csv_path.exists():
            load_from_csv(csv_path, db, batch_size=args.batch_size)
        else:
            print(f"[!] Belirtilen veri dosyası bulunamadı:")
            print(f"    CSV aranan: {csv_path}")
            print(f"    Parquet aranan: {parquet_path}")
            print("    Hızlı test için demo verisi yüklemek isterseniz: python backend/scripts/seed_demo_data.py")
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

