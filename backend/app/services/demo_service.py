"""WaterWise Backend - Demo Kaçak Simülasyon Servisi (demo_service.py).

Proje öneri formundaki Normal -> Anormal geçişini canlı göstermek için:
- 'src.synthetic_anomalies.make_demo_leak_records' fonksiyonunu çağırarak kontrollü
  gece sürekli akış (kaçak) darbeleri üretir.
- Gerçek geçmiş kayıtların arkasına bu kaçak kayıtlarını ekler.
- Modelin her saat için ürettiği skorları ve Anormal uyarılarını döndürür.
"""
from __future__ import annotations

from typing import List

import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import ConsumptionRecord
from backend.app.schemas import (
    AnomalyPredictionResponse,
    DemoSimulateRequest,
    DemoSimulateResponse,
)
from backend.app.services.ai_service import (
    fetch_apartment_records,
    get_detector,
    save_anomaly_log,
)
from src.predict import WaterWiseInputError
from src.synthetic_anomalies import make_demo_leak_records


def simulate_leak_scenario(
    db: Session,
    request: DemoSimulateRequest,
) -> DemoSimulateResponse:
    """Belirtilen daireye kontrollü sentetik gece sürekli akışı (kaçak) enjekte eder."""
    detector = get_detector()

    # Başlangıç saati belirleme (yerel saat Europe/Stockholm)
    if request.start_time:
        t0 = pd.Timestamp(request.start_time)
        if t0.tzinfo is None:
            t0 = t0.tz_localize(settings.LOCAL_TIMEZONE)
        else:
            t0 = t0.tz_convert(settings.LOCAL_TIMEZONE)
    else:
        # Veritabanındaki en son güne ait saat 01:00
        latest = (
            db.query(ConsumptionRecord.timestamp_utc)
            .filter(ConsumptionRecord.apartment == request.apartment_id)
            .order_by(ConsumptionRecord.timestamp_utc.desc())
            .first()
        )
        if latest and latest[0]:
            t_lat = pd.Timestamp(latest[0], tz="UTC").tz_convert(settings.LOCAL_TIMEZONE)
            t0 = t_lat.normalize() + pd.Timedelta(hours=1)
        else:
            t0 = pd.Timestamp("2022-11-24 01:00", tz=settings.LOCAL_TIMEZONE)

    # 1. Demo kaçak kayıtlarını üret (her 10 dakikada darbeler halinde, ör. saatte 18 L)
    leak_records = make_demo_leak_records(
        start=t0,
        hours=request.hours,
        rate_l_per_hour=request.rate_l_per_hour,
    )

    # 2. Veritabanından önceki 28 günlük geçmişi çek
    history_start = (t0 - pd.Timedelta(days=28)).tz_convert("UTC")
    target_end = (t0 + pd.Timedelta(hours=request.hours + 1)).tz_convert("UTC")

    db_records = fetch_apartment_records(db, request.apartment_id, history_start, target_end)

    # 3. Gerçek kayıtlar ile demo kaçak kayıtlarını birleştir
    combined_records = db_records + leak_records

    # 4. Kaçak dönemini saat saat değerlendir
    eval_start = t0.tz_convert("UTC").floor("h")
    eval_end = (t0 + pd.Timedelta(hours=request.hours - 1)).tz_convert("UTC").floor("h")

    try:
        raw_results = detector.evaluate(
            apartment_id=request.apartment_id,
            records=combined_records,
            start=eval_start.isoformat(),
            end=eval_end.isoformat(),
            history_start=history_start.isoformat(),
        )
    except WaterWiseInputError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Simülasyon hatası: [{e.code}] {e.message}",
        )

    # 5. Sonuçları log tablosuna demo işaretiyle kaydet
    response_items = []
    for r in raw_results:
        save_anomaly_log(db, r, is_demo=True)
        response_items.append(AnomalyPredictionResponse(**r))

    summary = (
        f"{request.apartment_id} dairesi için {t0.strftime('%Y-%m-%d %H:%M')} yerel saatinden "
        f"itibaren {request.hours:.0f} saatlik {request.rate_l_per_hour:.0f} L/saat debili sürekli akış "
        f"başarıyla simüle edildi. {len(response_items)} saatin değerlendirme sonuçları üretildi."
    )

    return DemoSimulateResponse(
        apartment_id=request.apartment_id,
        simulated_hours=request.hours,
        rate_l_per_hour=request.rate_l_per_hour,
        start_time_local=t0.isoformat(),
        results=response_items,
        summary=summary,
    )

