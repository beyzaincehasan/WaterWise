"""WaterWise Backend - Ana FastAPI Uygulaması (main.py).

Özellikler:
- FastAPI yaşam döngüsü (lifespan) ile modelin açılışta yüklenmesi.
- React frontend (http://localhost:5173, http://localhost:3000) için CORS yapılandırması.
- Global hata yakalayıcılar (WaterWiseInputError -> 422/409, WaterWiseModelError -> 500).
- Modüler router yapısı (/health, /api/v1/apartments, /api/v1/anomalies).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from backend.app.config import settings
from backend.app.database import init_db
from backend.app.routers import anomalies, apartments, consumption, health
from backend.app.services.ai_service import get_detector
from src.predict import WaterWiseInputError, WaterWiseModelError

# Loglama ayarı
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("waterwise.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Uygulama açılışında ve kapanışında çalışan yaşam döngüsü yöneticisi."""
    logger.info("WaterWise Backend başlatılıyor...")
    
    # 1. Veritabanı tablolarını oluştur
    init_db()
    logger.info("Veritabanı tabloları doğrulandı.")

    # 2. AI modelini uygulama açılışında BİR KEZ belleğe yükle (soğuk başlatmayı önler)
    try:
        detector = get_detector()
        logger.info(
            f"AI Modeli başarıyla yüklendi. Sürüm: {detector.model_version}, "
            f"Tanımlı Daire Sayısı: {len(detector.known_apartments())}"
        )
    except Exception as e:
        logger.error(f"AI Modeli yüklenirken hata oluştu: {e}")

    yield

    logger.info("WaterWise Backend kapatılıyor...")


# FastAPI Uygulama Tanımı
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
# WaterWise 💧 Su Tüketim Analizi ve Anomali Tespit API

Evsel su tüketiminin analiz edilmesini, geçmiş kullanım örüntülerinin öğrenilmesini ve
**Isolation Forest** makine öğrenmesi algoritmasıyla olağandışı tüketim davranışlarının
(gece sürekli akışı, açık kalan musluk, olası su kaçağı vb.) tespit edilmesini sağlar.

## Temel Modüller
- **Sistem & Sağlık (`/health`)**: API ve modelin operasyonel durumu.
- **Daireler (`/api/v1/apartments`)**: Daire listesi ve profil normal tüketim aralıkları.
- **Tüketim Analizi (`/api/v1/apartments/{id}/...`)**: Günlük tüketim serisi, armatür kırılımı ve özet istatistikler.
- **Anomali Tespiti (`/api/v1/anomalies`)**: 28 günlük geçmişi değerlendirerek tahmin yürütme ve kayıtlı uyarıları listeleme.
- **Demo Kaçak Simülatörü (`/api/v1/anomalies/simulate-demo`)**: Sunum ve test için yapay kaçak senaryosu.

> **Önemli Not:** Modelin ürettiği `anomaly_score` skoru (0, 1] aralığında göreli bir göstergedir; kesinlikle bir olasılık (% kaçak olasılığı) olarak yorumlanmamalıdır.
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Yapılandırması (React frontend için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Hata Yakalayıcılar
@app.exception_handler(WaterWiseInputError)
async def waterwise_input_error_handler(request: Request, exc: WaterWiseInputError):
    """AI modülünden dönen girdi doğrulama hatalarını HTTP 422 veya 409'a çevirir."""
    status_code = (
        status.HTTP_409_CONFLICT
        if exc.code == "TARGET_NOT_OBSERVED"
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": exc.code, "detail": exc.message},
    )


@app.exception_handler(WaterWiseModelError)
async def waterwise_model_error_handler(request: Request, exc: WaterWiseModelError):
    """Eksik model veya uyumsuzluk durumunda HTTP 500 döner."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "MODEL_ERROR", "detail": str(exc)},
    )


# Router Kayıtları
app.include_router(health.router)
app.include_router(apartments.router, prefix=settings.API_V1_STR)
app.include_router(consumption.router, prefix=settings.API_V1_STR)
app.include_router(anomalies.router, prefix=settings.API_V1_STR)


@app.get("/", include_in_schema=False)
def root():
    """Kök dizin Swagger dokümantasyonuna yönlendirir."""
    return RedirectResponse(url="/docs")

