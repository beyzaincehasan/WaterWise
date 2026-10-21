"""WaterWise Backend - Pydantic Veri Şemaları (Schemas).

API girdi/çıktı sözleşmelerini tanımlar.
Not: anomaly_score bir olasılık değildir; (0, 1] aralığında göreli bir anomali göstergesidir.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sağlık ve Sistem Durumu
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = Field(..., description="API çalışma durumu (healthy/ok)")
    app_name: str = Field(..., description="Uygulama adı")
    version: str = Field(..., description="Backend sürümü")
    model_version: str = Field(..., description="Yapay zekâ modeli sürümü")
    known_apartments_count: int = Field(..., description="Normal profili olan kayıtlı daire sayısı")
    database_status: str = Field(..., description="Veritabanı bağlantı durumu")


# ---------------------------------------------------------------------------
# Daire Bilgisi ve Profili
# ---------------------------------------------------------------------------
class ApartmentListItem(BaseModel):
    id: str = Field(..., description="Daire kimliği (ör. APT_001)")
    cluster_name: Optional[str] = Field(None, description="Bağlı olduğu bina kümesi (CL_A..CL_I)")
    has_profile: bool = Field(True, description="Eğitilmiş normal profili var mı?")
    normal_daily_mean_liters: Optional[float] = Field(None, description="Profildeki günlük ortalama tüketim (L)")
    normal_range_liters: Optional[List[float]] = Field(None, description="Günlük normal tüketim aralığı [p05, p95]")


# ---------------------------------------------------------------------------
# Tüketim Analizi Şemaları
# ---------------------------------------------------------------------------
class DailyConsumptionItem(BaseModel):
    date: str = Field(..., description="Tarih (YYYY-MM-DD)")
    total_liters: float = Field(..., description="Günlük toplam tüketim (Litre)")
    cold_water_liters: float = Field(..., description="Soğuk su tüketimi (Litre)")
    hot_water_liters: float = Field(..., description="Sıcak su tüketimi (Litre)")
    record_count: int = Field(..., description="Güne ait sensör okuma adedi")


class FixtureBreakdownItem(BaseModel):
    fixture: str = Field(..., description="Armatür/kullanım kategorisi (Duş, Musluk, Tuvalet, Makine, Diğer)")
    total_liters: float = Field(..., description="Toplam tüketim (Litre)")
    percentage: float = Field(..., description="Dairenin toplam tüketimi içindeki yüzdesi (%0-100)")
    record_count: int = Field(..., description="İlgili armatüre ait okuma sayısı")


class ApartmentStatsResponse(BaseModel):
    apartment_id: str = Field(..., description="Daire kimliği")
    total_consumption_liters: float = Field(..., description="Tüm kayıtlı dönemdeki toplam tüketim (L)")
    daily_mean_liters: float = Field(..., description="Kayıtlı günlerin ortalama günlük tüketimi (L)")
    max_hourly_liters: float = Field(..., description="Gözlemlenen en yüksek saatlik tüketim (L)")
    night_consumption_ratio: float = Field(..., description="Gece (00:00-06:00) saatlerindeki tüketimin toplam tüketime oranı (%)")
    normal_daily_mean_liters: Optional[float] = Field(None, description="Eğitim profilindeki günlük ortalama (L)")
    normal_range_liters: Optional[List[float]] = Field(None, description="Profildeki normal aralık [p05, p95] (L)")
    first_recorded_date: Optional[str] = Field(None, description="İlk kayıt tarihi")
    last_recorded_date: Optional[str] = Field(None, description="Son kayıt tarihi")


# ---------------------------------------------------------------------------
# Anomali Tespiti Şemaları (backend_integration.md sözleşmesine birebir uygun)
# ---------------------------------------------------------------------------
class AnomalyReason(BaseModel):
    code: str = Field(..., description="Gerekçe kodu (NIGHT_CONTINUOUS_FLOW, HIGH_CONSUMPTION vb.)")
    text: str = Field(..., description="Kullanıcıya yönelik açıklayıcı Türkçe gerekçe metni")


class ThresholdsSchema(BaseModel):
    suspicious: float = Field(..., description="Şüpheli durum eşiği")
    anomalous: float = Field(..., description="Anormal durum eşiği")
    scope: str = Field(..., description="Eşik kapsamı ('apartment' veya 'global')")


class AnomalyHistoryInfo(BaseModel):
    sufficient: bool = Field(..., description="Geçmiş veri miktarı yeterli mi?")
    profile_fallback_used: bool = Field(..., description="Eksik geçmiş nedeniyle eğitim profili yedek olarak kullanıldı mı?")
    apartment_profile_available: bool = Field(..., description="Daireye özel profil var mı?")


class AnomalyPredictionResponse(BaseModel):
    apartment_id: str = Field(..., description="Değerlendirilen daire kimliği")
    timestamp: str = Field(..., description="Değerlendirilen saatin başlangıcı (UTC, ISO-8601 'Z')")
    timestamp_local: str = Field(..., description="Değerlendirilen anın yerel saati (Europe/Stockholm)")
    period_minutes: int = Field(60, description="Analiz periyodu (saatlik analiz için her zaman 60)")
    consumption_liters: float = Field(..., description="O saatteki toplam tüketim (L)")
    status: str = Field(..., description="Anomali durumu ('Normal', 'Şüpheli', 'Anormal')")
    anomaly_score: float = Field(
        ...,
        description="Isolation Forest anomali skoru (0, 1]. Yüksek skor = daha olağandışı kullanım. "
                    "ÖNEMLİ: Bu değer kesinlikle bir olasılık (% kaçak olasılığı) DEĞİLDİR."
    )
    thresholds: ThresholdsSchema = Field(..., description="Uygulanan eşik değerleri")
    normal_consumption_liters: Optional[float] = Field(None, description="Bu saat için profil ortalama tüketimi (L)")
    normal_upper_liters: Optional[float] = Field(None, description="Bu saat için profil p95 üst sınırı (L)")
    historical_same_hour_mean_liters: Optional[float] = Field(None, description="Dairenin son 28 gündeki aynı saat ortalaması (L)")
    rolling_24h_mean_liters: Optional[float] = Field(None, description="Önceki 24 saat ortalaması (L)")
    rolling_7d_mean_liters: Optional[float] = Field(None, description="Önceki 7 gün ortalaması (L)")
    active_10min_intervals: int = Field(..., description="Saatteki tüketimli 10 dk dilim sayısı (0-6)")
    continuous_activity_minutes: int = Field(..., description="Art arda tüketimli dilim süresi (dk, bir süreklilik göstergesidir)")
    is_night: bool = Field(..., description="Gece saati mi? (Yerel 00:00-06:00)")
    reasons: List[AnomalyReason] = Field(default_factory=list, description="Anomali gerekçeleri (Normal ise boş)")
    message: str = Field(..., description="Kullanıcıya gösterilecek Türkçe durum/uyarı mesajı")
    history: AnomalyHistoryInfo = Field(..., description="Geçmiş bağlam durumu")
    warnings: List[str] = Field(default_factory=list, description="Uyarı kodları ve açıklamaları")
    disclaimer: str = Field(..., description="Teşhis olmadığına dair sabit yasal bilgilendirme")
    model_version: str = Field(..., description="Model sürümü")


class AnomalyDetectRequest(BaseModel):
    apartment_id: str = Field(..., description="Tahmin yapılacak daire (ör. APT_011)")
    target_timestamp: Optional[str] = Field(
        None,
        description="Değerlendirilecek saat (ISO formatı UTC veya yerel saat). Verilmezse son kayıt saati alınır."
    )
    history_days: int = Field(28, description="Geriye dönük incelenecek gün sayısı (önerilen 28)")
    save_log: bool = Field(True, description="Sonuç 'Anormal' veya 'Şüpheli' ise anomali log tablosuna kaydedilsin mi?")


class AnomalyLogItem(BaseModel):
    id: int
    apartment_id: str
    timestamp_utc: datetime
    timestamp_local: str
    consumption_liters: float
    status: str
    anomaly_score: float = Field(
        ...,
        description="Isolation Forest anomali skoru (0, 1]. Yüksek skor = daha olağandışı. Olasılık değildir."
    )
    message: str
    reasons: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    is_demo: bool


# ---------------------------------------------------------------------------
# Demo / Simülasyon Şemaları
# ---------------------------------------------------------------------------
class DemoSimulateRequest(BaseModel):
    apartment_id: str = Field("APT_011", description="Demo kaçak uygulanacak daire")
    start_time: Optional[str] = Field(
        None,
        description="Kaçağın başlayacağı yerel saat (ör. '2022-11-24 01:00'). Boş bırakılırsa uygun bir gece saati seçilir."
    )
    hours: float = Field(3.0, description="Kaçak süresi (saat)")
    rate_l_per_hour: float = Field(18.0, description="Kaçak debisi (Litre/saat, varsayılan 18 L/saat)")


class DemoSimulateResponse(BaseModel):
    apartment_id: str
    simulated_hours: float
    rate_l_per_hour: float
    start_time_local: str
    results: List[AnomalyPredictionResponse]
    summary: str

