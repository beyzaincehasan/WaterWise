"""WaterWise Backend - AI Modülü Entegrasyon Servisi (ai_service.py).

Eğitilmiş Isolation Forest modelini (src/predict.py) backend veritabanına bağlar:
- load_detector(): Modeli uygulama açılışında bir kez yükler ve önbelleğe alır.
- predict_anomaly(): Belirtilen daire ve saat için anomali skoru ve durumunu hesaplar.
- detector.evaluate(): Çoklu saat analizi (son 24 saat dashboard görünümü vb.) yapar.
- WaterWiseInputError -> HTTP 422 / HTTP 409 hata eşlemesini yönetir.
- Anormal/Şüpheli sonuçları veritabanındaki 'anomaly_logs' tablosuna kaydeder.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import AnomalyLog, ConsumptionRecord
from backend.app.schemas import AnomalyDetectRequest, AnomalyPredictionResponse
from src.predict import (
    WaterWiseAnomalyDetector,
    WaterWiseInputError,
    WaterWiseModelError,
    load_detector,
    predict_anomaly,
)

# Dedektör önbelleği
_detector: Optional[WaterWiseAnomalyDetector] = None


def get_detector() -> WaterWiseAnomalyDetector:
    """Uygulama açılışında modeli yükler ve tekil (singleton) nesneyi döndürür."""
    global _detector
    if _detector is None:
        try:
            _detector = load_detector(model_dir=settings.MODELS_DIR)
        except WaterWiseModelError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Model dosyaları yüklenemedi: {str(e)}",
            )
    return _detector


def fetch_apartment_records(
    db: Session,
    apartment_id: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> List[Dict[str, Any]]:
    """Veritabanından belirtilen daire ve tarih aralığı için 10 dk kayıtlarını çeker.
    
    Model girdi sözleşmesine uygun format:
    [{ "timestamp": "YYYY-MM-DDTHH:MM:SSZ", "consumption_liters": float }, ...]
    """
    # Tarihleri Python datetime objesine çevir
    start_dt = start_utc.to_pydatetime()
    end_dt = end_utc.to_pydatetime()

    rows = (
        db.query(ConsumptionRecord.timestamp_utc, ConsumptionRecord.value_liters)
        .filter(
            ConsumptionRecord.apartment == apartment_id,
            ConsumptionRecord.timestamp_utc >= start_dt,
            ConsumptionRecord.timestamp_utc < end_dt,
        )
        .order_by(ConsumptionRecord.timestamp_utc.asc())
        .all()
    )

    records = []
    for ts, val in rows:
        # Zaman damgasını UTC ISO formatında hazırla
        ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(ts, "strftime") else str(ts)
        records.append({
            "timestamp": ts_str,
            "consumption_liters": float(val),
        })

    return records


def run_anomaly_detection(
    db: Session,
    request: AnomalyDetectRequest,
) -> AnomalyPredictionResponse:
    """Belirtilen daire ve saat için Isolation Forest anomali tahminini yürütür."""
    detector = get_detector()

    # 1. Hedef saati belirle (verilmemişse en son kayıt saati)
    if request.target_timestamp:
        try:
            target_ts = pd.Timestamp(request.target_timestamp)
            if target_ts.tzinfo is None:
                target_ts = target_ts.tz_localize(settings.LOCAL_TIMEZONE).tz_convert("UTC")
            else:
                target_ts = target_ts.tz_convert("UTC")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Geçersiz hedef zaman damgası: {request.target_timestamp}",
            ) from exc
    else:
        latest = (
            db.query(ConsumptionRecord.timestamp_utc)
            .filter(ConsumptionRecord.apartment == request.apartment_id)
            .order_by(ConsumptionRecord.timestamp_utc.desc())
            .first()
        )
        if not latest or not latest[0]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{request.apartment_id}' dairesine ait tüketim kaydı bulunamadı.",
            )
        target_ts = pd.Timestamp(latest[0], tz="UTC")

    # Saatin başlangıcına yuvarla
    target_hour = target_ts.floor("h")

    # 2. 28 günlük geçmiş bağlam başlangıcı (T - 28 gün)
    history_start = target_hour - pd.Timedelta(days=request.history_days)
    target_end = target_hour + pd.Timedelta(hours=1)

    # 3. Veritabanından [history_start, target_end) aralığındaki ham kayıtları çek
    records = fetch_apartment_records(db, request.apartment_id, history_start, target_end)
    if not records:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{request.apartment_id}' için {history_start} ve {target_end} aralığında hiç tüketim kaydı bulunamadı.",
        )

    # 4. Model tahminini çağır
    try:
        raw_result = predict_anomaly(
            apartment_id=request.apartment_id,
            records=records,
            target_timestamp=target_hour.isoformat(),
            history_start=history_start.isoformat(),
            detector=detector,
        )
    except WaterWiseInputError as e:
        if e.code == "TARGET_NOT_OBSERVED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"[{e.code}] {e.message}",
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"[{e.code}] {e.message}",
        )
    except WaterWiseModelError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model yapılandırma hatası: {str(e)}",
        )

    # 5. Loglama (Şüpheli veya Anormal ise veritabanına kaydet)
    if request.save_log and raw_result["status"] in ("Şüpheli", "Anormal"):
        save_anomaly_log(db, raw_result, is_demo=False)

    return AnomalyPredictionResponse(**raw_result)


def evaluate_hours_range(
    db: Session,
    apartment_id: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    history_days: int = 28,
) -> List[AnomalyPredictionResponse]:
    """Dashboard için belirtilen saat aralığını toplu olarak değerlendirir (örn. son 24 saat)."""
    detector = get_detector()

    start_h = start_utc.floor("h")
    end_h = end_utc.floor("h")
    history_start = start_h - pd.Timedelta(days=history_days)
    target_end = end_h + pd.Timedelta(hours=1)

    records = fetch_apartment_records(db, apartment_id, history_start, target_end)
    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{apartment_id}' için incelenen aralıkta kayıt bulunamadı.",
        )

    try:
        rows = detector.evaluate(
            apartment_id=apartment_id,
            records=records,
            start=start_h.isoformat(),
            end=end_h.isoformat(),
            history_start=history_start.isoformat(),
        )
    except WaterWiseInputError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"[{e.code}] {e.message}",
        )

    return [AnomalyPredictionResponse(**r) for r in rows]


def save_anomaly_log(db: Session, res: Dict[str, Any], is_demo: bool = False) -> AnomalyLog:
    """Anomali sonucunu 'anomaly_logs' tablosuna kaydeder veya günceller."""
    ts_utc = pd.Timestamp(res["timestamp"]).to_pydatetime()
    apt_id = res["apartment_id"]

    existing = (
        db.query(AnomalyLog)
        .filter(AnomalyLog.apartment_id == apt_id, AnomalyLog.timestamp_utc == ts_utc)
        .first()
    )

    if existing:
        log_entry = existing
    else:
        log_entry = AnomalyLog(apartment_id=apt_id, timestamp_utc=ts_utc)
        db.add(log_entry)

    log_entry.timestamp_local = res["timestamp_local"]
    log_entry.period_minutes = res["period_minutes"]
    log_entry.consumption_liters = res["consumption_liters"]
    log_entry.status = res["status"]
    log_entry.anomaly_score = res["anomaly_score"]
    log_entry.suspicious_threshold = res["thresholds"]["suspicious"]
    log_entry.anomalous_threshold = res["thresholds"]["anomalous"]
    log_entry.threshold_scope = res["thresholds"]["scope"]
    log_entry.normal_consumption_liters = res.get("normal_consumption_liters")
    log_entry.normal_upper_liters = res.get("normal_upper_liters")
    log_entry.historical_same_hour_mean_liters = res.get("historical_same_hour_mean_liters")
    log_entry.rolling_24h_mean_liters = res.get("rolling_24h_mean_liters")
    log_entry.rolling_7d_mean_liters = res.get("rolling_7d_mean_liters")
    log_entry.active_10min_intervals = res["active_10min_intervals"]
    log_entry.continuous_activity_minutes = res["continuous_activity_minutes"]
    log_entry.is_night = res["is_night"]
    log_entry.reasons_json = json.dumps(res.get("reasons", []), ensure_ascii=False)
    log_entry.message = res["message"]
    log_entry.warnings_json = json.dumps(res.get("warnings", []), ensure_ascii=False)
    log_entry.model_version = res["model_version"]
    log_entry.is_demo = is_demo

    db.commit()
    db.refresh(log_entry)
    return log_entry

