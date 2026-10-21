"""WaterWise Backend - Tüketim Analizi ve İstatistik Servisi (consumption_service.py).

Günlük tüketim, armatür kırılımı ve özet istatistik sorgularını yönetir.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import case, extract, func
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import Apartment, ConsumptionRecord
from backend.app.schemas import (
    ApartmentListItem,
    ApartmentStatsResponse,
    DailyConsumptionItem,
    FixtureBreakdownItem,
)

# Profilleri bellekte tut
_profiles_cache: Optional[dict] = None


def get_profiles_data() -> dict:
    """models/normal_profiles.json dosyasını okur ve önbelleğe alır."""
    global _profiles_cache
    if _profiles_cache is None:
        p_file = settings.PROFILES_FILE
        if p_file.exists():
            with open(p_file, encoding="utf-8") as f:
                _profiles_cache = json.load(f)
        else:
            _profiles_cache = {"apartments": {}, "global": {}}
    return _profiles_cache


def get_apartments_list(db: Session) -> List[ApartmentListItem]:
    """Sistemdeki tüm daireleri ve normal tüketim aralıklarını listeler."""
    apts = db.query(Apartment).order_by(Apartment.id.asc()).all()
    profiles = get_profiles_data().get("apartments", {})

    items = []
    for apt in apts:
        prof = profiles.get(apt.id, {})
        daily = prof.get("daily", {})
        mean_l = daily.get("mean_liters")
        norm_range = daily.get("normal_range_liters")

        items.append(
            ApartmentListItem(
                id=apt.id,
                cluster_name=apt.cluster_name,
                has_profile=apt.has_profile,
                normal_daily_mean_liters=round(mean_l, 1) if mean_l is not None else None,
                normal_range_liters=[round(x, 1) for x in norm_range] if norm_range else None,
            )
        )
    return items


def get_daily_consumption(
    db: Session,
    apartment_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[DailyConsumptionItem]:
    """Belirli bir dairenin günlük su tüketim geçmişini (sıcak/soğuk kırılımıyla) getirir."""
    # Tarih bazında gruplama (SQLite ve PostgreSQL uyumlu func.date)
    date_col = func.date(ConsumptionRecord.timestamp_utc).label("date_str")

    query = (
        db.query(
            date_col,
            func.sum(ConsumptionRecord.value_liters).label("total"),
            func.sum(
                case(
                    (ConsumptionRecord.water_type == "cold", ConsumptionRecord.value_liters),
                    else_=0.0,
                )
            ).label("cold_total"),
            func.sum(
                case(
                    (ConsumptionRecord.water_type == "hot", ConsumptionRecord.value_liters),
                    else_=0.0,
                )
            ).label("hot_total"),
            func.count(ConsumptionRecord.id).label("count"),
        )
        .filter(ConsumptionRecord.apartment == apartment_id)
        .group_by(date_col)
        .order_by(date_col.asc())
    )

    if start_date:
        query = query.filter(date_col >= start_date)
    if end_date:
        query = query.filter(date_col <= end_date)

    rows = query.all()

    items = []
    for d_str, tot, cold, hot, cnt in rows:
        items.append(
            DailyConsumptionItem(
                date=str(d_str),
                total_liters=round(float(tot or 0.0), 1),
                cold_water_liters=round(float(cold or 0.0), 1),
                hot_water_liters=round(float(hot or 0.0), 1),
                record_count=int(cnt),
            )
        )
    return items


def get_fixture_breakdown(
    db: Session,
    apartment_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[FixtureBreakdownItem]:
    """Dairenin armatür/kullanım kategorisi bazındaki (Duş, Musluk vb.) tüketim dağılımı."""
    query = db.query(
        ConsumptionRecord.usage_category,
        func.sum(ConsumptionRecord.value_liters).label("total"),
        func.count(ConsumptionRecord.id).label("count"),
    ).filter(ConsumptionRecord.apartment == apartment_id)

    if start_date:
        query = query.filter(func.date(ConsumptionRecord.timestamp_utc) >= start_date)
    if end_date:
        query = query.filter(func.date(ConsumptionRecord.timestamp_utc) <= end_date)

    rows = (
        query.group_by(ConsumptionRecord.usage_category)
        .order_by(func.sum(ConsumptionRecord.value_liters).desc())
        .all()
    )

    grand_total = sum(float(r[1] or 0.0) for r in rows)

    items = []
    for cat, tot, cnt in rows:
        t_val = float(tot or 0.0)
        pct = (t_val / grand_total * 100.0) if grand_total > 0 else 0.0
        items.append(
            FixtureBreakdownItem(
                fixture=cat or "Diğer",
                total_liters=round(t_val, 1),
                percentage=round(pct, 1),
                record_count=int(cnt),
            )
        )
    return items


def get_apartment_stats(db: Session, apartment_id: str) -> ApartmentStatsResponse:
    """Daire için genel özet tüketim istatistiklerini hesaplar."""
    # Toplam tüketim ve tarih sınırları
    basic = (
        db.query(
            func.sum(ConsumptionRecord.value_liters),
            func.min(ConsumptionRecord.timestamp_utc),
            func.max(ConsumptionRecord.timestamp_utc),
            func.count(func.distinct(func.date(ConsumptionRecord.timestamp_utc))),
        )
        .filter(ConsumptionRecord.apartment == apartment_id)
        .first()
    )

    total_liters = float(basic[0] or 0.0)
    first_date = str(basic[1])[:10] if basic[1] else None
    last_date = str(basic[2])[:10] if basic[2] else None
    day_count = int(basic[3] or 1)

    daily_mean = round(total_liters / max(day_count, 1), 1)

    # Gece saatleri tüketimi (00:00 - 06:00 UTC)
    hour_col = extract("hour", ConsumptionRecord.timestamp_utc)
    night_query = (
        db.query(func.sum(ConsumptionRecord.value_liters))
        .filter(
            ConsumptionRecord.apartment == apartment_id,
            hour_col >= 0,
            hour_col < 6,
        )
        .scalar()
    )
    night_liters = float(night_query or 0.0)
    night_ratio = round((night_liters / total_liters * 100.0), 1) if total_liters > 0 else 0.0

    # En yüksek saatlik tüketim (1 saatlik dilimler)
    date_part = func.date(ConsumptionRecord.timestamp_utc)
    max_hour_query = (
        db.query(func.sum(ConsumptionRecord.value_liters))
        .filter(ConsumptionRecord.apartment == apartment_id)
        .group_by(date_part, hour_col)
        .order_by(func.sum(ConsumptionRecord.value_liters).desc())
        .first()
    )
    max_hourly = round(float(max_hour_query[0] or 0.0), 1) if max_hour_query else 0.0

    # Normal profil istatistikleri
    profiles = get_profiles_data().get("apartments", {})
    prof = profiles.get(apartment_id, {})
    prof_daily = prof.get("daily", {})
    p_mean = prof_daily.get("mean_liters")
    p_range = prof_daily.get("normal_range_liters")

    return ApartmentStatsResponse(
        apartment_id=apartment_id,
        total_consumption_liters=round(total_liters, 1),
        daily_mean_liters=daily_mean,
        max_hourly_liters=max_hourly,
        night_consumption_ratio=night_ratio,
        normal_daily_mean_liters=round(p_mean, 1) if p_mean is not None else None,
        normal_range_liters=[round(x, 1) for x in p_range] if p_range else None,
        first_recorded_date=first_date,
        last_recorded_date=last_date,
    )

