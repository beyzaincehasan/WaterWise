"""WaterWise AI modülü için merkezi yapılandırma.

Tüm yollar, zaman dilimi kararları, zamansal veri ayrımı ve model
hiperparametreleri burada tanımlanır; diğer modüller değerleri buradan okur.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Yollar
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_CSV = DATA_DIR / "HSB_Living_Lab_Water_Consumption_Anonymized.csv"
PROCESSED_DIR = DATA_DIR / "processed"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
MODELS_DIR = PROJECT_ROOT / "models"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
ANOMALIES_DIR = OUTPUTS_DIR / "anomalies"
REPORTS_DIR = OUTPUTS_DIR / "reports"

MODEL_FILE = MODELS_DIR / "isolation_forest.joblib"
METADATA_FILE = MODELS_DIR / "model_metadata.json"
PROFILES_FILE = MODELS_DIR / "normal_profiles.json"

# --------------------------------------------------------------------------
# Veri semantiği
# --------------------------------------------------------------------------
CSV_SEPARATOR = ";"
# Ham `value` sütunu m³ cinsindendir (bkz. docs/ai_methodology.md, bölüm 3).
M3_TO_LITERS = 1000.0
# CSV'deki zaman damgaları yerel duvar saatidir (DST davranışıyla doğrulandı).
LOCAL_TZ = "Europe/Stockholm"
SLOT_MINUTES = 10
SLOTS_PER_HOUR = 60 // SLOT_MINUTES
# Bina genelinde bu süreden uzun kayıtsız aralık = veri toplama sistemi kesintisi.
BUILDING_OUTAGE_HOURS = 6.0
# Sensör boşluğunda kümülatif sayaç bu kadar m³'ten fazla ilerlediyse
# boşlukta kaydedilmemiş tüketim vardır (veri kaybı). 0.0005 m³ = 0.5 L (< 1 L çözünürlük).
UNRECORDED_TOLERANCE_M3 = 0.0005

# Gece saatleri (yerel saat, [başlangıç, bitiş) ).
NIGHT_START_HOUR = 0
NIGHT_END_HOUR = 6

# --------------------------------------------------------------------------
# Zamansal ayrım (yerel tarih sınırları, UTC'ye çevrilerek kullanılır)
# Uzun sistem kesintileri doğal ayrım noktası olarak kullanılmıştır.
# --------------------------------------------------------------------------
TRAIN_START = pd.Timestamp("2020-01-01", tz=LOCAL_TZ)
TRAIN_END = pd.Timestamp("2021-11-23", tz=LOCAL_TZ)        # 2021-11-23 → 2022-02-17 kesinti
VALID_START = pd.Timestamp("2022-02-17", tz=LOCAL_TZ)
VALID_END = pd.Timestamp("2022-07-01", tz=LOCAL_TZ)
TEST_START = pd.Timestamp("2022-07-01", tz=LOCAL_TZ)
TEST_END = pd.Timestamp("2023-02-01", tz=LOCAL_TZ)

# --------------------------------------------------------------------------
# Özellik mühendisliği
# --------------------------------------------------------------------------
HISTORY_DAYS = 28                 # aynı-saat geçmiş ortalaması penceresi
MIN_SAME_HOUR_OBS = 7             # aynı-saat ortalaması için gereken en az gözlem
MIN_24H_OBS = 12                  # 24 saatlik ortalama için en az gözlenen saat
MIN_7D_OBS = 72                   # 7 günlük ortalama için en az gözlenen saat
RUN_CAP_SLOTS = 72                # süreklilik göstergesi üst sınırı (12 saat)

# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
RANDOM_STATE = 42
IFOREST_PARAMS = {
    "n_estimators": 300,
    "max_samples": 512,
    "max_features": 1.0,
    "contamination": "auto",
    "bootstrap": False,
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}
# Eşik kalibrasyonu: doğrulama dönemindeki gerçek saatlerin skor yüzdelikleri.
SUSPICIOUS_QUANTILE = 0.97
ANOMALOUS_QUANTILE = 0.995
# Daireye uyarlanmış (yalnızca yukarı yönlü) eşik için gereken en az doğrulama saati
MIN_APARTMENT_CALIBRATION_HOURS = 500

STATUS_NORMAL = "Normal"
STATUS_SUSPICIOUS = "Şüpheli"
STATUS_ANOMALOUS = "Anormal"

MODEL_VERSION = "1.0.0"
