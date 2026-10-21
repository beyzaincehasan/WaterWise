# WaterWise Backend API – Frontend Entegrasyon Rehberi 💧

**Hedef Kitle:** Frontend Geliştiricisi (React / TypeScript)  
**Base URL:** `http://localhost:8000`  
**Swagger Dokümantasyonu:** `http://localhost:8000/docs`  
**TypeScript Tipleri:** [`api_types.ts`](./api_types.ts)  
**OpenAPI Spesifikasyonu:** [`openapi.json`](./openapi.json)

---

## ⚠️ Kritik İş Mantığı ve Tasarım Kuralları

Frontend arayüzünü (özellikle uyarı ve grafik bileşenlerini) tasarlarken aşağıdaki üç kurala dikkat edilmelidir:

### 1. `anomaly_score` Bir Yüzde veya Olasılık DEĞİLDİR!
- Model skoru `(0, 1]` aralığında göreli bir aykırılık göstergesidir (Isolation Forest ağaçlarındaki ortalama yol uzunluğu formülüyle hesaplanır).
- Tipik normal tüketimlerde skor **0.38 – 0.55** aralığındadır. Değer 1'e yaklaştıkça kullanım daha olağandışı hale gelir.
- **Kesinlikle Yapılmaması Gereken:** Arayüzde `anomaly_score: 0.72` değerini *"%72 Kaçak İhtimali"* şeklinde **yansıtmamak** gerekir.
- **Doğru Gösterim:** Kullanıcıya `status` rozeti, `message` ve `reasons[].text` gerekçeleri sunulmalıdır. `anomaly_score` istenirse teknik detay panelinde veya eğilim çizgisinde gösterilebilir.

### 2. Durum Rozeti ve Alarm Politikası
Model üç durum üretir:
- 🟢 **`Normal` (Yeşil Rozet):** Tüketim dairenin geçmiş alışkanlıklarına ve normal profil aralığına uygundur.
- 🟡 **`Şüpheli` (Sarı Rozet):** Normalden belirli bir sapma vardır (ör. alışılmadık saatte kısa bir kullanım).
  - *Politika:* Daire-günlerin yaklaşık **%26.5'inde** en az bir şüpheli saat görülür. Bu sıklık kullanıcıya anlık bildirim göndermek için çok fazladır. Bu nedenle `Şüpheli` durum yalnızca **dashboard üzerinde sarı rozet veya bilgilendirme kartı** olarak tutulmalı, anlık push bildirim / alarm üretmemelidir.
- 🔴 **`Anormal` (Kırmızı Rozet / Alarm):** Belirgin ve yüksek öncelikli olağandışı durum (ör. gece boyunca kesintisiz akan su, aşırı yüksek pik debi).
  - *Politika:* Daire-günlerin yalnızca **%6.95'inde** görülür. Kullanıcıya gösterilecek **kritik uyarı banner'ı, pop-up, SMS veya push bildirimleri yalnızca `status == "Anormal"` olduğunda tetiklenmelidir.**

### 3. Zaman Damgası Standartları (UTC vs Yerel Saat)
- **API ve Veritabanı:** Tüm arka plan işlemleri, veritabanı sorguları ve model hesaplamaları **UTC** zaman damgalarıyla (`timestamp`, sonu `Z` ile biter) yürütülür.
- **Arayüz Gösterimi:** React bileşenlerinde tarih ve saatleri biçimlendirirken yanıttaki hazır `timestamp_local` alanı (İsveç Europe/Stockholm duvar saati) doğrudan kullanılabilir.

---

## 📡 Endpoint Referansı

### 1. Sistem ve Model Sağlık Kontrolü
Uygulama açılışında backend servisinin ve makine öğrenmesi modelinin hazır olup olmadığını kontrol eder.

- **Metot / Yol:** `GET /health`
- **Frontend Kullanımı:** Global uygulama yüklenirken veya durum çubuğunda.
- **Örnek Yanıt (200 OK):**
```json
{
  "status": "healthy",
  "app_name": "WaterWise Su Tüketim Analizi ve Anomali Tespit API",
  "version": "1.0.0",
  "model_version": "1.0.0",
  "known_apartments_count": 28,
  "database_status": "connected"
}
```

---

### 2. Daire Listesi
Sistemde kayıtlı 28 dairenin (`APT_001` .. `APT_028`) listesini ve eğitim profilinden öğrenilmiş günlük normal tüketim istatistiklerini getirir.

- **Metot / Yol:** `GET /api/v1/apartments`
- **Frontend Kullanımı:** Dashboard üzerindeki daire seçici (Dropdown/Select) bileşeni.
- **Örnek Yanıt (200 OK):**
```json
[
  {
    "id": "APT_011",
    "cluster_name": "CL_D",
    "has_profile": true,
    "normal_daily_mean_liters": 20.0,
    "normal_range_liters": [0.0, 58.0]
  }
]
```
> `normal_range_liters`: [p05, p95] normal tüketim bandını temsil eder (grafiklerde güven aralığı gölgesi çizmek için uygundur).

---

### 3. Tek Daire Detayı
Seçilen tek bir dairenin profil özetini döner.

- **Metot / Yol:** `GET /api/v1/apartments/{apartment_id}`
- **Parametreler:** `apartment_id` (Path, string, ör. `APT_011`)
- **Örnek Yanıt (200 OK):**
```json
{
  "id": "APT_011",
  "cluster_name": "CL_D",
  "has_profile": true,
  "normal_daily_mean_liters": 20.0,
  "normal_range_liters": [0.0, 58.0]
}
```

---

### 4. Günlük Tüketim Zaman Serisi (Çizgi Grafik)
Seçilen tarih aralığında gün gün toplam tüketimi, sıcak ve soğuk su ayrımıyla döner.

- **Metot / Yol:** `GET /api/v1/apartments/{apartment_id}/daily-consumption`
- **Query Parametreleri:**
  - `start_date` *(opsiyonel, YYYY-MM-DD)*
  - `end_date` *(opsiyonel, YYYY-MM-DD)*
- **Frontend Kullanımı:** "Tüketim Analizi" sayfasındaki yığılmış alan (stacked area) veya çift çizgi grafiği.
- **Örnek Yanıt (200 OK):**
```json
[
  {
    "date": "2022-11-01",
    "total_liters": 168.0,
    "cold_water_liters": 79.9,
    "hot_water_liters": 88.1,
    "record_count": 24
  },
  {
    "date": "2022-11-02",
    "total_liters": 154.5,
    "cold_water_liters": 72.0,
    "hot_water_liters": 82.5,
    "record_count": 21
  }
]
```

---

### 5. Armatür Dağılımı (Pasta / Donut Grafiği)
Dairenin su tüketimini kullanım türlerine göre (Duş, Musluk, Tuvalet, Makine) gruplar ve yüzdelerini hesaplar.

- **Metot / Yol:** `GET /api/v1/apartments/{apartment_id}/fixture-breakdown`
- **Query Parametreleri:**
  - `start_date` *(opsiyonel, YYYY-MM-DD)*
  - `end_date` *(opsiyonel, YYYY-MM-DD)*
- **Frontend Kullanımı:** "Kullanım Dağılımı" donut grafiği.
- **Örnek Yanıt (200 OK):**
```json
[
  {
    "fixture": "Duş",
    "total_liters": 2118.0,
    "percentage": 42.9,
    "record_count": 72
  },
  {
    "fixture": "Tuvalet",
    "total_liters": 1164.0,
    "percentage": 23.6,
    "record_count": 258
  },
  {
    "fixture": "Musluk",
    "total_liters": 992.4,
    "percentage": 20.1,
    "record_count": 248
  },
  {
    "fixture": "Makine",
    "total_liters": 656.8,
    "percentage": 13.3,
    "record_count": 69
  }
]
```

---

### 6. Daire Özet İstatistikleri (KPI Kartları)
Dairenin toplam hacmi, günlük ortalama tüketimi, pik saati, gece kullanım oranı ve profil kıyaslamasını sunar.

- **Metot / Yol:** `GET /api/v1/apartments/{apartment_id}/stats`
- **Frontend Kullanımı:** Dashboard üst kısmındaki KPI metrik kartları.
- **Örnek Yanıt (200 OK):**
```json
{
  "apartment_id": "APT_011",
  "total_consumption_liters": 4937.2,
  "daily_mean_liters": 170.2,
  "max_hourly_liters": 46.5,
  "night_consumption_ratio": 4.4,
  "normal_daily_mean_liters": 20.0,
  "normal_range_liters": [0.0, 58.0],
  "first_recorded_date": "2022-10-26",
  "last_recorded_date": "2022-11-24"
}
```

---

### 7. Zaman Aralığı Saatlik Anomali Değerlendirmesi
Dashboard'da son 24 saatin saat saat incelenmesi ve her saat için durum ile anomali skorunun listelenmesini sağlar.

- **Metot / Yol:** `GET /api/v1/apartments/{apartment_id}/evaluate-range`
- **Query Parametreleri:**
  - `start_time` *(zorunlu, ISO-8601 UTC/Local, ör. `2022-11-23T00:00:00Z`)*
  - `end_time` *(zorunlu, ISO-8601 UTC/Local, ör. `2022-11-23T23:00:00Z`)*
  - `history_days` *(opsiyonel, varsayılan `28`)*
- **Frontend Kullanımı:** 24 saatlik anomali ısı haritası veya zaman çizelgesi (timeline).

---

### 8. Anomali Tespiti Çalıştırma (Isolation Forest API)
Veritabanından önceki 28 günlük geçmişi otomatik olarak çekip eğitilmiş yapay zekâ modeliyle anomali analizi yapar.

- **Metot / Yol:** `POST /api/v1/anomalies/detect`
- **İstek Gövdesi (JSON):**
```json
{
  "apartment_id": "APT_011",
  "target_timestamp": "2022-11-24T02:00:00Z",
  "history_days": 28,
  "save_log": true
}
```

#### Örnek A: Normal Saat Yanıtı
```json
{
  "apartment_id": "APT_011",
  "timestamp": "2022-11-23T10:00:00Z",
  "timestamp_local": "2022-11-23T11:00:00+01:00",
  "period_minutes": 60,
  "consumption_liters": 9.0,
  "status": "Normal",
  "anomaly_score": 0.4838,
  "thresholds": {
    "suspicious": 0.6061,
    "anomalous": 0.6575,
    "scope": "apartment"
  },
  "normal_consumption_liters": 1.3,
  "normal_upper_liters": 4.0,
  "active_10min_intervals": 2,
  "continuous_activity_minutes": 10,
  "is_night": false,
  "reasons": [],
  "message": "Su tüketimi dairenin normal tüketim aralığında.",
  "history": {
    "sufficient": true,
    "profile_fallback_used": false,
    "apartment_profile_available": true
  },
  "warnings": [],
  "disclaimer": "Bu sonuç tüketim davranışına dayalı bir olası kaçak / olağandışı kullanım uyarısıdır; kesin tesisat kaçağı teşhisi değildir.",
  "model_version": "1.0.0"
}
```

#### Örnek B: Anormal Saat Yanıtı (Gece Sürekli Akış)
```json
{
  "apartment_id": "APT_011",
  "timestamp": "2022-11-24T02:00:00Z",
  "timestamp_local": "2022-11-24T03:00:00+01:00",
  "period_minutes": 60,
  "consumption_liters": 18.0,
  "status": "Anormal",
  "anomaly_score": 0.7242,
  "thresholds": {
    "suspicious": 0.6061,
    "anomalous": 0.6575,
    "scope": "apartment"
  },
  "normal_consumption_liters": 0.3,
  "normal_upper_liters": 2.0,
  "active_10min_intervals": 6,
  "continuous_activity_minutes": 180,
  "is_night": true,
  "reasons": [
    {
      "code": "NIGHT_CONTINUOUS_FLOW",
      "text": "Gece saatlerinde 180 dakika boyunca kesintisiz tüketim kaydı (6/6 aktif 10 dk dilim). Olası sürekli akış."
    },
    {
      "code": "HIGH_CONSUMPTION",
      "text": "Bu saat için olağandışı yüksek tüketim: 18 L (normal ortalama 0.3 L, normal üst sınır 2 L)."
    },
    {
      "code": "UNUSUAL_HOUR",
      "text": "Dairenin bu saatte tüketim yapma olasılığı düşük (%6), ancak 18 L tüketim kaydedildi."
    }
  ],
  "message": "Gece saatlerinde olağandışı su tüketimi tespit edildi. Olası sürekli akış (açık musluk, rezervuar arızası veya kaçak) kontrol edilmelidir.",
  "history": {
    "sufficient": true,
    "profile_fallback_used": false,
    "apartment_profile_available": true
  },
  "warnings": [],
  "disclaimer": "Bu sonuç tüketim davranışına dayalı bir olası kaçak / olağandışı kullanım uyarısıdır; kesin tesisat kaçağı teşhisi değildir.",
  "model_version": "1.0.0"
}
```

---

### 9. Kayıtlı Anomalileri Listeleme
Veritabanında kayıtlı tüm geçmiş uyarı ve anomali olaylarını listeler.

- **Metot / Yol:** `GET /api/v1/anomalies`
- **Query Parametreleri:**
  - `apartment_id` *(opsiyonel)*
  - `status` *(opsiyonel, "Anormal" veya "Şüpheli")*
  - `start_date` *(opsiyonel, YYYY-MM-DD)*
  - `end_date` *(opsiyonel, YYYY-MM-DD)*
  - `limit` *(varsayılan 50)*
  - `offset` *(varsayılan 0)*
- **Frontend Kullanımı:** "Anomaliler ve Uyarılar" geçmiş tablosu.
- **Örnek Yanıt (200 OK):**
```json
[
  {
    "id": 1,
    "apartment_id": "APT_011",
    "timestamp_utc": "2022-11-24T02:00:00Z",
    "timestamp_local": "2022-11-24T03:00:00+01:00",
    "consumption_liters": 18.0,
    "status": "Anormal",
    "anomaly_score": 0.7242,
    "message": "Gece saatlerinde olağandışı su tüketimi tespit edildi. Olası sürekli akış (açık musluk, rezervuar arızası veya kaçak) kontrol edilmelidir.",
    "reasons": [
      {
        "code": "NIGHT_CONTINUOUS_FLOW",
        "text": "Gece saatlerinde 180 dakika boyunca kesintisiz tüketim kaydı (6/6 aktif 10 dk dilim). Olası sürekli akış."
      }
    ],
    "created_at": "2026-10-20T17:01:05.123456",
    "is_demo": false
  }
]
```

---

### 10. Canlı Demo Kaçak Simülasyonu (Sunum Butonu)
Arayüzde bir "Kaçak Simüle Et" butonuna basıldığında sentetik gece sürekli akışı (18 L/saat) enjekte ederek sistemin Normal → Anormal geçişini canlı gösterir.

- **Metot / Yol:** `POST /api/v1/anomalies/simulate-demo`
- **İstek Gövdesi (JSON):**
```json
{
  "apartment_id": "APT_011",
  "start_time": "2022-11-24 01:00",
  "hours": 3.0,
  "rate_l_per_hour": 18.0
}
```
- **Örnek Yanıt (200 OK):**
```json
{
  "apartment_id": "APT_011",
  "simulated_hours": 3.0,
  "rate_l_per_hour": 18.0,
  "start_time_local": "2022-11-24T01:00:00+01:00",
  "results": [
    {
      "timestamp_local": "2022-11-24T01:00:00+01:00",
      "consumption_liters": 18.0,
      "status": "Anormal",
      "anomaly_score": 0.7118
    },
    {
      "timestamp_local": "2022-11-24T02:00:00+01:00",
      "consumption_liters": 18.0,
      "status": "Anormal",
      "anomaly_score": 0.7262
    },
    {
      "timestamp_local": "2022-11-24T03:00:00+01:00",
      "consumption_liters": 18.0,
      "status": "Anormal",
      "anomaly_score": 0.7258
    }
  ],
  "summary": "APT_011 dairesi için 2022-11-24 01:00 yerel saatinden itibaren 3 saatlik 18 L/saat debili sürekli akış başarıyla simüle edildi. 3 saatin değerlendirme sonuçları üretildi."
}
```

