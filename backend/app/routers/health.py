"""WaterWise Backend - Sistem Sağlık Kontrolü (Health Router)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.schemas import HealthResponse
from backend.app.services.ai_service import get_detector

router = APIRouter(tags=["Sistem & Sağlık"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="API ve Yapay Zekâ Modeli Sağlık Kontrolü",
    description="Sistemin, veritabanı bağlantısının ve eğitilmiş Isolation Forest modelinin hazır olup olmadığını denetler.",
)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    # 1. Veritabanı sorgu testi
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    # 2. AI Modeli durumu
    detector = get_detector()
    known_count = len(detector.known_apartments())

    return HealthResponse(
        status="healthy",
        app_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        model_version=detector.model_version,
        known_apartments_count=known_count,
        database_status=db_status,
    )

