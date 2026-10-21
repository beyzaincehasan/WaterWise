"""WaterWise Backend - Su Tüketim Analizi ve İstatistikleri (Consumption Router)."""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.schemas import (
    AnomalyPredictionResponse,
    ApartmentStatsResponse,
    DailyConsumptionItem,
    FixtureBreakdownItem,
)
from backend.app.services.ai_service import evaluate_hours_range
from backend.app.services.consumption_service import (
    get_apartment_stats,
    get_daily_consumption,
    get_fixture_breakdown,
)

router = APIRouter(prefix="/apartments", tags=["Tüketim Analizi"])


@router.get(
    "/{apartment_id}/daily-consumption",
    response_model=List[DailyConsumptionItem],
    summary="Günlük Tüketim Serisi",
    description="Dairenin belirtilen tarih aralığındaki günlük toplam, sıcak su ve soğuk su tüketim serisini (Litre) listeler.",
)
def daily_consumption(
    apartment_id: str = Path(..., description="Daire kimliği (ör. APT_011)"),
    start_date: Optional[str] = Query(None, description="Başlangıç tarihi (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Bitiş tarihi (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> List[DailyConsumptionItem]:
    return get_daily_consumption(db, apartment_id, start_date=start_date, end_date=end_date)


@router.get(
    "/{apartment_id}/fixture-breakdown",
    response_model=List[FixtureBreakdownItem],
    summary="Armatür / Kullanım Türü Kırılımı",
    description="Dairenin su tüketimini armatür bazında (Duş, Musluk, Tuvalet, Makine, Diğer) hacim ve yüzde olarak dağıtır.",
)
def fixture_breakdown(
    apartment_id: str = Path(..., description="Daire kimliği (ör. APT_011)"),
    start_date: Optional[str] = Query(None, description="Filtre başlangıç tarihi (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filtre bitiş tarihi (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> List[FixtureBreakdownItem]:
    return get_fixture_breakdown(db, apartment_id, start_date=start_date, end_date=end_date)


@router.get(
    "/{apartment_id}/stats",
    response_model=ApartmentStatsResponse,
    summary="Özet Tüketim İstatistikleri",
    description="Dairenin toplam tüketimi, günlük ortalaması, pik saatlik tüketimi, gece oranı ve normal profil aralığını sunar.",
)
def apartment_stats(
    apartment_id: str = Path(..., description="Daire kimliği (ör. APT_011)"),
    db: Session = Depends(get_db),
) -> ApartmentStatsResponse:
    return get_apartment_stats(db, apartment_id)


@router.get(
    "/{apartment_id}/evaluate-range",
    response_model=List[AnomalyPredictionResponse],
    summary="Zaman Aralığı Saatlik Anomali Değerlendirmesi",
    description="Dashboard için [start_time, end_time] aralığındaki her saat için anomali skoru, tüketim ve durum listesi döndürür.",
)
def evaluate_range(
    apartment_id: str = Path(..., description="Daire kimliği (ör. APT_011)"),
    start_time: str = Query(..., description="Başlangıç zamanı (ISO 8601 UTC veya yerel)"),
    end_time: str = Query(..., description="Bitiş zamanı (ISO 8601 UTC veya yerel)"),
    history_days: int = Query(28, description="Geçmiş bağlam gün sayısı (varsayılan 28)"),
    db: Session = Depends(get_db),
) -> List[AnomalyPredictionResponse]:
    t_start = pd.Timestamp(start_time)
    if t_start.tzinfo is None:
        t_start = t_start.tz_localize(settings.LOCAL_TIMEZONE).tz_convert("UTC")
    else:
        t_start = t_start.tz_convert("UTC")

    t_end = pd.Timestamp(end_time)
    if t_end.tzinfo is None:
        t_end = t_end.tz_localize(settings.LOCAL_TIMEZONE).tz_convert("UTC")
    else:
        t_end = t_end.tz_convert("UTC")

    return evaluate_hours_range(
        db,
        apartment_id=apartment_id,
        start_utc=t_start,
        end_utc=t_end,
        history_days=history_days,
    )

