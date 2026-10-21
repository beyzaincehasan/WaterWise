"""WaterWise Backend - SQLAlchemy Veritabanı Modelleri.

Tablolar:
- ConsumptionRecord: 10 dakikalık ham su tüketim kayıtları.
- AnomalyLog: Tespit edilen anomaliler ve uyarı kayıtları.
- Apartment: Daire listesi ve temel bilgileri.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)

from backend.app.database import Base


class ConsumptionRecord(Base):
    """Ham sensör tüketim kayıtları.
    
    Önemli Kurallar:
    - value_liters: CSV'deki 'value' m³ değerinin 1000 ile çarpılmış litre karşılığıdır.
    - aggregated_value: Yalnızca kümülatif sayaç endeksidir, tüketime eklenmez.
    - timestamp_utc: UTC saat diliminde saklanır; model sorguları bu sütunu kullanır.
    - (apartment, timestamp_utc) üzerinde bileşik index bulunmaktadır.
    """
    __tablename__ = "consumption_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    apartment = Column(String(20), nullable=True, index=True)  # APT_001..APT_028 veya NULL (ortak alan)
    timestamp_utc = Column(DateTime(timezone=True), nullable=False, index=True)
    timestamp_local = Column(DateTime, nullable=True)  # Europe/Stockholm duvar saati (kolay sorgulama için)
    value_liters = Column(Float, nullable=False)  # Litre cinsinden net tüketim
    value_m3 = Column(Float, nullable=True)  # Orijinal m³ değeri
    aggregated_value = Column(Float, nullable=True)  # Kümülatif sayaç endeksi (m³)
    sensor_id = Column(String(20), nullable=True, index=True)  # S0001..S0214
    cluster_name = Column(String(20), nullable=True)  # CL_A..CL_I
    room_number = Column(String(20), nullable=True)  # R001 vb.
    room_type = Column(String(50), nullable=True)  # Kitchen, Bathroom vb.
    water_type = Column(String(20), nullable=True)  # 'cold' veya 'hot'
    attached_to = Column(String(50), nullable=True)  # Shower, Kitchen tap vb.
    usage_category = Column(String(50), nullable=True, index=True)  # Duş, Musluk, Tuvalet, Makine, Diğer
    created_at = Column(DateTime, default=datetime.utcnow)

    # 28 günlük geriye dönük sorguların ve kategori filtrelerinin yüksek performanslı çalışması için indeksler:
    __table_args__ = (
        Index("ix_consumption_apartment_timestamp", "apartment", "timestamp_utc"),
        Index("ix_consumption_apartment_usage", "apartment", "usage_category"),
        Index("ix_consumption_apartment_watertype", "apartment", "water_type"),
    )


class AnomalyLog(Base):
    """Model tarafından tespit edilen ve veritabanına kaydedilen anomali kayıtları."""
    __tablename__ = "anomaly_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    apartment_id = Column(String(20), nullable=False, index=True)
    timestamp_utc = Column(DateTime(timezone=True), nullable=False, index=True)
    timestamp_local = Column(String(50), nullable=False)
    period_minutes = Column(Integer, default=60)
    consumption_liters = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, index=True)  # 'Normal', 'Şüpheli', 'Anormal'
    anomaly_score = Column(Float, nullable=False)  # Isolation Forest anomali skoru (0, 1]
    suspicious_threshold = Column(Float, nullable=True)
    anomalous_threshold = Column(Float, nullable=True)
    threshold_scope = Column(String(20), nullable=True)  # 'apartment' veya 'global'
    normal_consumption_liters = Column(Float, nullable=True)
    normal_upper_liters = Column(Float, nullable=True)
    historical_same_hour_mean_liters = Column(Float, nullable=True)
    rolling_24h_mean_liters = Column(Float, nullable=True)
    rolling_7d_mean_liters = Column(Float, nullable=True)
    active_10min_intervals = Column(Integer, nullable=True)
    continuous_activity_minutes = Column(Integer, nullable=True)
    is_night = Column(Boolean, nullable=True)
    reasons_json = Column(Text, nullable=True)  # JSON kodlanmış neden listesi
    message = Column(Text, nullable=False)  # Kullanıcıya gösterilecek Türkçe metin
    warnings_json = Column(Text, nullable=True)
    model_version = Column(String(20), nullable=True)
    is_demo = Column(Boolean, default=False)  # Demo/simülasyon kaydı mı?
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_anomaly_apt_ts", "apartment_id", "timestamp_utc"),
        Index("ix_anomaly_status", "status"),
    )


class Apartment(Base):
    """Sistemde kayıtlı daireler ve özet bilgileri."""
    __tablename__ = "apartments"

    id = Column(String(20), primary_key=True)  # APT_001..APT_028
    cluster_name = Column(String(20), nullable=True)
    has_profile = Column(Boolean, default=True)  # Eğitilmiş normal profili var mı?
    created_at = Column(DateTime, default=datetime.utcnow)

