"""WaterWise Backend - Yapılandırma Modülü.

Ortam değişkenlerini (.env) okur, varsayılan SQLite/PostgreSQL veritabanı yollarını
ve proje genelindeki dizin hiyerarşisini belirler.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# Dizin yolları:
# BACKEND_DIR: WaterWise/backend
# PROJECT_ROOT: WaterWise (kök dizin; src/ ve models/ burada yer alır)
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

# Kök dizini sys.path'e ekleyelim; böylece 'src.predict' doğrudan import edilebilir.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class Settings(BaseSettings):
    """Uygulama ayarları (ortam değişkenlerinden veya .env dosyasından beslenir)."""

    # Veritabanı bağlantı adresi (varsayılan: backend dizininde yerel SQLite)
    DATABASE_URL: str = f"sqlite:///{BACKEND_DIR / 'waterwise.db'}"

    # React frontend için CORS izinleri (virgülle ayrılmış liste)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # API başlığı ve versiyonu
    PROJECT_NAME: str = "WaterWise Su Tüketim Analizi ve Anomali Tespit API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # AI Model yolları (Kök dizindeki models/ klasörü)
    MODELS_DIR: Path = PROJECT_ROOT / "models"
    MODEL_FILE: Path = MODELS_DIR / "isolation_forest.joblib"
    PROFILES_FILE: Path = MODELS_DIR / "normal_profiles.json"
    METADATA_FILE: Path = MODELS_DIR / "model_metadata.json"

    # Zaman dilimi standardı
    LOCAL_TIMEZONE: str = "Europe/Stockholm"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        """CORS_ORIGINS dizesini liste haline getirir."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


# Tekil ayar nesnesi
settings = Settings()

