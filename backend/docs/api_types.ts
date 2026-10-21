/**
 * WaterWise API TypeScript Tanımları (api_types.ts)
 * 
 * Frontend (React/TypeScript) geliştiricisi için hazırlanmış veri modelleri.
 * Bu dosya backend/app/schemas.py dosyasındaki Pydantic modelleriyle birebir uyumludur.
 */

// ---------------------------------------------------------------------------
// Durum ve Sabit Tipleri
// ---------------------------------------------------------------------------

/**
 * Anomali tespit durumu.
 * - "Normal": Tüketim normal aralıkta (Yeşil rozet).
 * - "Şüpheli": Belirli düzeyde sapma var (Sarı rozet, dashboard gösterimi).
 * - "Anormal": Belirgin ve yüksek olasılıklı aykırılık/kaçak (Kırmızı rozet, alarm/bildirim tetikler).
 */
export type AnomalyStatus = "Normal" | "Şüpheli" | "Anormal";

/**
 * Anomali gerekçe kodları.
 */
export type AnomalyReasonCode =
  | "NIGHT_CONTINUOUS_FLOW" // Gece saatlerinde kesintisiz akış (olası açık musluk/kaçak)
  | "HIGH_CONSUMPTION"      // Saatin normal p95 üst sınırının belirgin üzerinde tüketim
  | "UNUSUAL_HOUR"          // Dairenin nadiren su kullandığı saatte yüksek tüketim
  | "SHORT_SPIKE"           // 10-20 dakikada ani ve yüksek hacimli tüketim
  | "LONG_CONTINUOUS_USE"   // Gündüz saatlerinde daire ortalamasını aşan uzun sürekli kullanım
  | "DEVIATION_FROM_NORMAL" // 28 günlük geçmiş ortalamasından belirgin sapma
  | "PATTERN_COMBINATION"   // Zaman, miktar ve süreklilik bileşimi sıra dışı
  | "GENERIC_PROFILE";      // Daireye özel profil bulunamadı, bina ortalaması uygulandı

/**
 * Eşik kapsamı:
 * - "apartment": Dairenin kendi doğrulama skorlarına göre kalibre edilmiş eşik.
 * - "global": Tüm bina için geçerli ortak model eşiği.
 */
export type ThresholdScope = "apartment" | "global";

/**
 * Armatür / kullanım kategorileri.
 */
export type FixtureCategory = "Duş" | "Musluk" | "Tuvalet" | "Makine" | "Diğer" | string;

/**
 * Su türü.
 */
export type WaterType = "cold" | "hot" | "unknown";


// ---------------------------------------------------------------------------
// Sistem & Sağlık Modelleri
// ---------------------------------------------------------------------------

export interface HealthResponse {
  /** API çalışma durumu (ör. "healthy") */
  status: string;
  /** Uygulama adı */
  app_name: string;
  /** Backend sürümü */
  version: string;
  /** Eğitilmiş Isolation Forest model sürümü */
  model_version: string;
  /** Sistemde profili bulunan kayıtlı daire sayısı (28) */
  known_apartments_count: number;
  /** Veritabanı bağlantı durumu (ör. "connected") */
  database_status: string;
}


// ---------------------------------------------------------------------------
// Daire Modelleri
// ---------------------------------------------------------------------------

export interface ApartmentListItem {
  /** Daire kimliği (ör. "APT_001" .. "APT_028") */
  id: string;
  /** Bağlı olduğu bina kümesi (ör. "CL_A" .. "CL_I") */
  cluster_name: string | null;
  /** Eğitilmiş normal profili var mı? */
  has_profile: boolean;
  /** Normal profil günlük ortalama tüketimi (Litre) */
  normal_daily_mean_liters: number | null;
  /** Normal günlük tüketim aralığı [p05, p95] (Litre) */
  normal_range_liters: [number, number] | null;
}


// ---------------------------------------------------------------------------
// Tüketim Analizi Modelleri
// ---------------------------------------------------------------------------

export interface DailyConsumptionItem {
  /** Tarih (YYYY-MM-DD) */
  date: string;
  /** Günlük toplam tüketim (Litre) */
  total_liters: number;
  /** Soğuk su tüketimi (Litre) */
  cold_water_liters: number;
  /** Sıcak su tüketimi (Litre) */
  hot_water_liters: number;
  /** O güne ait sensör darbe/okuma sayısı */
  record_count: number;
}

export interface FixtureBreakdownItem {
  /** Armatür/kullanım kategorisi (Duş, Musluk, Tuvalet, Makine, Diğer) */
  fixture: FixtureCategory;
  /** İlgili armatürün toplam tüketimi (Litre) */
  total_liters: number;
  /** Toplam tüketim içindeki payı (%0 - %100) */
  percentage: number;
  /** Okuma/olay sayısı */
  record_count: number;
}

export interface ApartmentStatsResponse {
  /** Daire kimliği */
  apartment_id: string;
  /** İncelenen dönemdeki toplam tüketim (Litre) */
  total_consumption_liters: number;
  /** Günlük ortalama tüketim (Litre) */
  daily_mean_liters: number;
  /** Gözlemlenen en yüksek saatlik tüketim (Litre) */
  max_hourly_liters: number;
  /** Gece (00:00 - 06:00) tüketiminin toplam tüketime oranı (%) */
  night_consumption_ratio: number;
  /** Profil günlük ortalama tüketimi (Litre) */
  normal_daily_mean_liters: number | null;
  /** Profil normal aralığı [p05, p95] (Litre) */
  normal_range_liters: [number, number] | null;
  /** İlk kayıt tarihi (YYYY-MM-DD) */
  first_recorded_date: string | null;
  /** Son kayıt tarihi (YYYY-MM-DD) */
  last_recorded_date: string | null;
}


// ---------------------------------------------------------------------------
// Anomali Tespiti ve Uyarı Modelleri
// ---------------------------------------------------------------------------

export interface AnomalyReason {
  /** Gerekçe kodu */
  code: AnomalyReasonCode | string;
  /** Kullanıcıya gösterilecek Türkçe açıklama */
  text: string;
}

export interface ThresholdsInfo {
  /** Şüpheli durum eşiği */
  suspicious: number;
  /** Anormal durum eşiği */
  anomalous: number;
  /** Eşik kapsamı ("apartment" veya "global") */
  scope: ThresholdScope;
}

export interface AnomalyHistoryInfo {
  /** Geçmiş veri miktarı (en az 7 gün) yeterli mi? */
  sufficient: boolean;
  /** Yetersiz geçmiş nedeniyle eğitim profili yedek olarak kullanıldı mı? */
  profile_fallback_used: boolean;
  /** Daireye özel profil mevcut mu? */
  apartment_profile_available: boolean;
}

export interface AnomalyPredictionResponse {
  /** Değerlendirilen daire kimliği */
  apartment_id: string;
  /** Değerlendirilen saatin başlangıcı (UTC, ISO-8601 'Z' ile biter) */
  timestamp: string;
  /** Değerlendirilen anın yerel saat gösterimi (Europe/Stockholm, arayüz için) */
  timestamp_local: string;
  /** Analiz penceresi süresi (dakika, her zaman 60) */
  period_minutes: number;
  /** O saatteki toplam tüketim (Litre) */
  consumption_liters: number;
  /** Anomali durumu */
  status: AnomalyStatus;
  /**
   * Isolation Forest anomali skoru (0, 1].
   * Yüksek skor = daha olağandışı kullanım.
   * DİKKAT: Kesinlikle bir yüzde (% kaçak olasılığı) olarak gösterilmemelidir.
   */
  anomaly_score: number;
  /** Uygulanan dinamik eşikler */
  thresholds: ThresholdsInfo;
  /** Normal profildeki bu saatin ortalama tüketimi (Litre) */
  normal_consumption_liters: number | null;
  /** Normal profildeki bu saatin p95 üst sınırı (Litre) */
  normal_upper_liters: number | null;
  /** Son 28 gündeki aynı saat ortalaması (Litre) */
  historical_same_hour_mean_liters: number | null;
  /** Son 24 saatlik ortalama tüketim (Litre) */
  rolling_24h_mean_liters: number | null;
  /** Son 7 günlük ortalama tüketim (Litre) */
  rolling_7d_mean_liters: number | null;
  /** Saatte tüketim olan 10 dakikalık dilim adedi (0 - 6) */
  active_10min_intervals: number;
  /** Art arda tüketimli dilim süresi (dakika, süreklilik göstergesi) */
  continuous_activity_minutes: number;
  /** Gece saati mi? (Yerel 00:00 - 06:00) */
  is_night: boolean;
  /** Anomali gerekçeleri (Normal ise boş dizidir) */
  reasons: AnomalyReason[];
  /** Kullanıcıya gösterilecek Türkçe durum/uyarı mesajı */
  message: string;
  /** Geçmiş bağlam denetimi */
  history: AnomalyHistoryInfo;
  /** Varsa sistem uyarı kodları (ör. "SHORT_HISTORY") */
  warnings: string[];
  /** Yasal sorumluluk reddi beyanı */
  disclaimer: string;
  /** Model sürümü */
  model_version: string;
}

export interface AnomalyDetectRequest {
  /** Tahmin yapılacak daire (ör. "APT_011") */
  apartment_id: string;
  /** Değerlendirilecek saat (ISO UTC veya yerel saat). Boş bırakılırsa en son kayıt saati alınır. */
  target_timestamp?: string | null;
  /** İncelenecek geçmiş gün sayısı (önerilen: 28) */
  history_days?: number;
  /** Sonuç 'Şüpheli' veya 'Anormal' ise veritabanına kaydedilsin mi? (varsayılan: true) */
  save_log?: boolean;
}

export interface AnomalyLogItem {
  id: number;
  apartment_id: string;
  timestamp_utc: string;
  timestamp_local: string;
  consumption_liters: number;
  status: AnomalyStatus;
  anomaly_score: number;
  message: string;
  reasons: AnomalyReason[];
  created_at: string;
  is_demo: boolean;
}


// ---------------------------------------------------------------------------
// Demo / Simülasyon Modelleri
// ---------------------------------------------------------------------------

export interface DemoSimulateRequest {
  /** Kaçak uygulanacak daire (varsayılan "APT_011") */
  apartment_id?: string;
  /** Kaçağın başlayacağı yerel saat (ör. "2022-11-24 01:00") */
  start_time?: string | null;
  /** Kaçak süresi (saat, varsayılan 3.0) */
  hours?: number;
  /** Kaçak debisi (Litre/saat, varsayılan 18.0 L/saat) */
  rate_l_per_hour?: number;
}

export interface DemoSimulateResponse {
  apartment_id: string;
  simulated_hours: number;
  rate_l_per_hour: number;
  start_time_local: string;
  results: AnomalyPredictionResponse[];
  summary: string;
}


// ---------------------------------------------------------------------------
// Hata Yanıt Modeli
// ---------------------------------------------------------------------------

export interface ApiErrorResponse {
  error: string;
  detail: string;
}


// ---------------------------------------------------------------------------
// Frontend Yardımcı Fonksiyonları (Utility Helpers)
// ---------------------------------------------------------------------------

/**
 * Anomali durumuna göre UI rozet rengini döndürür.
 */
export function getStatusBadgeVariant(status: AnomalyStatus): "success" | "warning" | "destructive" {
  switch (status) {
    case "Normal":
      return "success";      // Yeşil
    case "Şüpheli":
      return "warning";      // Sarı
    case "Anormal":
      return "destructive";  // Kırmızı
    default:
      return "success";
  }
}

/**
 * Durumun kritik alarm / push bildirim gerektirip gerektirmediğini kontrol eder.
 * Politika gereği yalnızca "Anormal" durumu bildirim üretmelidir.
 */
export function shouldTriggerNotification(status: AnomalyStatus): boolean {
  return status === "Anormal";
}

