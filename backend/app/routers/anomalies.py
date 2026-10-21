"""WaterWise Backend - Anomali Tespiti ve Uyarı Yönetimi (Anomalies Router)."""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import AnomalyLog
from backend.app.schemas import (
    AnomalyDetectRequest,
    AnomalyLogItem,
    AnomalyPredictionResponse,
    DemoSimulateRequest,
    DemoSimulateResponse,
)
from backend.app.services.ai_service import run_anomaly_detection
from backend.app.services.demo_service import simulate_leak_scenario

router = APIRouter(prefix="/anomalies", tags=["Anomali Tespiti"])


@router.post(
    "/detect",
    response_model=AnomalyPredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="Anomali Tespiti Çalıştır",
    description="Eğitilmiş Isolation Forest modelini kullanarak, belirtilen daire ve saat için tüketim anomalisi tespiti yapar. "
                "28 günlük geçmiş bağlamı veritabanından otomatik çeker.",
)
def detect_anomaly(
    request: AnomalyDetectRequest,
    db: Session = Depends(get_db),
) -> AnomalyPredictionResponse:
    return run_anomaly_detection(db, request)


@router.get(
    "",
    response_model=List[AnomalyLogItem],
    summary="Kayıtlı Anomalileri Listele",
    description="Veritabanına kaydedilmiş anomali ve uyarı kayıtlarını filtreleyerek listeler.",
)
def list_anomaly_logs(
    apartment_id: Optional[str] = Query(None, description="Daire filtresi (ör. APT_011)"),
    anomaly_status: Optional[str] = Query(None, alias="status", description="Durum filtresi ('Anormal', 'Şüpheli')"),
    start_date: Optional[str] = Query(None, description="Başlangıç tarihi (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Bitiş tarihi (YYYY-MM-DD)"),
    limit: int = Query(50, ge=1, le=500, description="Sayfa başına kayıt sayısı"),
    offset: int = Query(0, ge=0, description="Kayıt başlangıç ofseti"),
    db: Session = Depends(get_db),
) -> List[AnomalyLogItem]:
    query = db.query(AnomalyLog)

    if apartment_id:
        query = query.filter(AnomalyLog.apartment_id == apartment_id)
    if anomaly_status:
        query = query.filter(AnomalyLog.status == anomaly_status)
    if start_date:
        query = query.filter(AnomalyLog.timestamp_utc >= start_date)
    if end_date:
        query = query.filter(AnomalyLog.timestamp_utc <= end_date)

    logs = query.order_by(AnomalyLog.timestamp_utc.desc()).offset(offset).limit(limit).all()

    items = []
    for log in logs:
        reasons_list = json.loads(log.reasons_json) if log.reasons_json else []
        items.append(
            AnomalyLogItem(
                id=log.id,
                apartment_id=log.apartment_id,
                timestamp_utc=log.timestamp_utc,
                timestamp_local=log.timestamp_local,
                consumption_liters=log.consumption_liters,
                status=log.status,
                anomaly_score=log.anomaly_score,
                message=log.message,
                reasons=reasons_list,
                created_at=log.created_at,
                is_demo=log.is_demo,
            )
        )
    return items


@router.post(
    "/simulate-demo",
    response_model=DemoSimulateResponse,
    status_code=status.HTTP_200_OK,
    summary="Demo Kaçak Senaryosu Simülasyonu",
    description="Sunum ve arayüz testi için seçilen gece saatine sürekli akış (18 L/saat) enjekte ederek "
                "Normal -> Anormal durum geçişini canlı simüle eder.",
)
def simulate_demo(
    request: DemoSimulateRequest,
    db: Session = Depends(get_db),
) -> DemoSimulateResponse:
    return simulate_leak_scenario(db, request)

