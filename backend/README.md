# WaterWise Backend API 💧

WaterWise projesinin evsel su tüketimi analizi, istatistiksel görselleştirme ve yapay zekâ destekli anomali tespiti işlemlerini yürüten FastAPI tabanlı arka uç (backend) servisidir.

Bu servis, **Isolation Forest** algoritması ile eğitilmiş makine öğrenmesi modelini (`models/isolation_forest.joblib`) ve 28 dairenin normal tüketim profillerini (`models/normal_profiles.json`) kullanarak anormal tüketimleri (gece sürekli akışı, açık kalan musluk, olası su kaçağı) tespit eder.

---

## 🚀 Teknolojiler

- **Python:** 3.13
- **Web Çerçevesi:** FastAPI (Asenkron, yüksek performans, otomatik OpenAPI / Swagger dokümantasyonu)
- **Veritabanı ORM:** SQLAlchemy 2.x
- **Veritabanı:** Varsayılan olarak yerel **SQLite** (`waterwise.db`), `.env` üzerinden tek satırla **PostgreSQL** desteği
- **Makine Öğrenmesi & Veri:** Scikit-learn, Pandas, NumPy, Joblib, PyArrow

---

## 📁 Dizin Yapısı

```text
WaterWise/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI ana uygulaması, CORS, lifespan ve router kayıtları
│   │   ├── config.py            # Ortam değişkenleri (.env) ve dinamik dizin yolları
│   │   ├── database.py          # SQLAlchemy motoru, oturum yönetimi ve get_db dependency
│   │   ├── models.py            # ConsumptionRecord, AnomalyLog ve Apartment tabloları
│   │   ├── schemas.py           # Pydantic v2 girdi/çıktı sözleşmeleri ve Swagger modelleri
│   │   ├── services/
│   │   │   ├── ai_service.py    # Isolation Forest dedektörü, 28 günlük geçmiş çekme ve tahmin
│   │   │   ├── consumption_service.py # Günlük tüketim serisi, armatür kırılımı ve istatistikler
│   │   │   └── demo_service.py  # make_demo_leak_records ile canlı kaçak simülasyonu
│   │   └── routers/
│   │       ├── health.py        # GET /health
│   │       ├── apartments.py    # GET /api/v1/apartments
│   │       ├── consumption.py   # GET /daily-consumption, fixture-breakdown, stats, evaluate-range
│   │       └── anomalies.py     # POST /detect, GET /anomalies, POST /simulate-demo
│   ├── scripts/
│   │   ├── load_data.py         # Ham CSV / Parquet verisini veritabanına aktaran betik
│   │   ├── seed_demo_data.py    # Geliştirme/test için gerçekçi 28 günlük demo veri tohumlayıcı
│   │   └── test_endpoints.py    # Tüm endpoint'lerin otomatik doğrulama betiği
│   ├── .env.example             # Örnek ortam değişkenleri şablonu
│   ├── .gitignore               # Backend özelinde git yoksayma kuralları (.env, *.db vb.)
│   ├── requirements.txt         # Sabitlenmiş Python 3.13 bağımlılıkları
│   └── README.md                # Kurulum ve entegrasyon dokümantasyonu (bu dosya)
```

---

## 🛠️ Kurulum Adımları

Tüm komutlar projenin kök dizininde (`WaterWise\`) çalıştırılmalıdır.

### 1. Sanal Ortam Oluşturma (Python 3.13)

```powershell
py -3.13 -m venv backend\.venv
```

Sanal ortamı aktifleştirmek için (PowerShell):
```powershell
.\backend\.venv\Scripts\Activate.ps1
```

### 2. Bağımlılıkları Yükleme

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

### 3. Yapılandırma Dosyasını Hazırlama

`backend/.env.example` dosyasını `backend/.env` olarak kopyalayın:
```powershell
Copy-Item backend\.env.example backend\.env
```

*Varsayılan SQLite ayarı hazırdır. PostgreSQL kullanmak isterseniz `DATABASE_URL` satırını güncelleyin:*
```env
DATABASE_URL=sqlite:///./waterwise.db
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

## 💾 Veritabanına Veri Yükleme

### Seçenek A: Hızlı Demo Verisi Tohumlama (Önerilen)

Elinizde tam ham veri seti (650 bin satırlık CSV) henüz yoksa, normal tüketim profillerine uygun 28 günlük gerçekçi sensör okumalarını ve 28 daireyi oluşturmak için:

```powershell
backend\.venv\Scripts\python.exe backend/scripts/seed_demo_data.py
```

### Seçenek B: Ham CSV veya Parquet Dosyasını Aktarma

Gerçek veri dosyanız mevcut olduğunda toplu aktarım için:

```powershell
# Ham CSV'den aktarım (ayırıcı ; Europe/Stockholm -> UTC ve Litre dönüşümüyle):
backend\.venv\Scripts\python.exe backend/scripts/load_data.py --csv data/HSB_Living_Lab_Water_Consumption_Anonymized.csv

# Veya işlenmiş Parquet'ten hızlı aktarım:
backend\.venv\Scripts\python.exe backend/scripts/load_data.py --parquet data/processed/apartment_records.parquet
```

---

## ⚡ Sunucuyu Başlatma

Uvicorn geliştirme sunucusunu başlatmak için:

```powershell
backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

* Sunucu Adresi: `http://127.0.0.1:8000`
* **Etkileşimli Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **ReDoc Dokümantasyonu:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 📡 API Endpoint Referansı

| Metot | Endpoint | Açıklama |
|---|---|---|
| `GET` | `/health` | API, veritabanı ve model sağlık durumu |
| `GET` | `/api/v1/apartments` | Kayıtlı 28 dairenin listesi ve normal tüketim aralıkları |
| `GET` | `/api/v1/apartments/{id}` | Tek bir dairenin profil detayları |
| `GET` | `/api/v1/apartments/{id}/daily-consumption` | Günlük toplam, soğuk ve sıcak su tüketim serisi |
| `GET` | `/api/v1/apartments/{id}/fixture-breakdown` | Armatür bazında (Duş, Musluk, Tuvalet, Makine) tüketim yüzdeleri |
| `GET` | `/api/v1/apartments/{id}/stats` | Daire özet istatistikleri (ortalama, pik saat, gece oranı) |
| `GET` | `/api/v1/apartments/{id}/evaluate-range` | Dashboard için saatlik anomali değerlendirmesi (son 24 saat) |
| `POST` | `/api/v1/anomalies/detect` | Eğitilmiş Isolation Forest ile tek saatlik anomali tespiti |
| `GET` | `/api/v1/anomalies` | Veritabanına kaydedilmiş anomalileri listeleme ve filtreleme |
| `POST` | `/api/v1/anomalies/simulate-demo` | Sunum için gece sürekli akış (18 L/saat) kaçak simülasyonu |

---

## 💻 Frontend (React) Geliştiricisi İçin İstek ve Yanıt Örnekleri

### 1. Sistem ve Model Durumu
```bash
curl -X GET "http://127.0.0.1:8000/health"
```
**Yanıt (200 OK):**
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
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/apartments"
```
**Örnek Öğe:**
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

### 3. Günlük Tüketim Çizgi Grafiği Verisi
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/apartments/APT_011/daily-consumption?start_date=2022-11-01&end_date=2022-11-07"
```
**Yanıt (200 OK):**
```json
[
  {
    "date": "2022-11-01",
    "total_liters": 168.0,
    "cold_water_liters": 79.9,
    "hot_water_liters": 88.1,
    "record_count": 24
  }
]
```

---

### 4. Armatür / Kullanım Türü Dağılımı (Pasta Grafiği)
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/apartments/APT_011/fixture-breakdown"
```
**Yanıt (200 OK):**
```json
[
  { "fixture": "Duş", "total_liters": 2118.0, "percentage": 42.9, "record_count": 72 },
  { "fixture": "Tuvalet", "total_liters": 1164.0, "percentage": 23.6, "record_count": 258 },
  { "fixture": "Musluk", "total_liters": 992.4, "percentage": 20.1, "record_count": 248 },
  { "fixture": "Makine", "total_liters": 656.8, "percentage": 13.3, "record_count": 69 }
]
```

---

### 5. Anomali Tespiti Çalıştırma (Isolation Forest)

#### A) Normal Bir Saat İçin İstek:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/anomalies/detect" \
  -H "Content-Type: application/json" \
  -d '{
    "apartment_id": "APT_011",
    "target_timestamp": "2022-11-23T10:00:00Z",
    "history_days": 28,
    "save_log": true
  }'
```
**Yanıt (200 OK - Normal):**
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

#### B) Gece Sürekli Akış (Kaçak) Saati İçin İstek:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/anomalies/detect" \
  -H "Content-Type: application/json" \
  -d '{
    "apartment_id": "APT_011",
    "target_timestamp": "2022-11-24T02:00:00Z",
    "history_days": 28,
    "save_log": true
  }'
```
**Yanıt (200 OK - Anormal):**
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

### 6. Canlı Demo Kaçak Simülasyonu
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/anomalies/simulate-demo" \
  -H "Content-Type: application/json" \
  -d '{
    "apartment_id": "APT_011",
    "start_time": "2022-11-24 01:00",
    "hours": 3.0,
    "rate_l_per_hour": 18.0
  }'
```
**Yanıt (200 OK):**
01:00, 02:00 ve 03:00 saatlerinin üçü için de `Anormal` durum kodu, `NIGHT_CONTINUOUS_FLOW` gerekçesi ve detaylı sonuç listesi döner.

---

## 📌 Entegrasyon İlkeleri ve Frontend İpuçları

1. **`anomaly_score` Bir Yüzde/Olasılık Değildir:**
   - Model skoru `(0, 1]` aralığında göreceli bir ölçektir (Liu vd. 2008). Tipik normal gözlemler `0.38 - 0.55` aralığındadır.
   - Arayüzde kesinlikle *"%74 Kaçak Var"* gibi gösterilmemelidir.
   - Gösterimde `status` rozeti (`Normal` -> Yeşil, `Şüpheli` -> Sarı, `Anormal` -> Kırmızı), `message` ve `reasons[].text` kullanılmalıdır.
2. **Bildirim ve Alarm Politikası:**
   - Daire-günlerin yaklaşık %26.5'inde en az bir `Şüpheli` saat bulunur; bu bildirim için fazladır.
   - Kullanıcıya anlık uyarı / bildirim yalnızca `status == "Anormal"` durumunda gönderilmelidir (daire-günlerin yaklaşık %6.95'i).
   - `Şüpheli` durum arayüzde bilgilendirme rozeti olarak tutulmalıdır.
3. **Zaman Damgaları (UTC vs Local):**
   - Veritabanı ve model girdi çağrılarında ISO-8601 UTC (`timestamp_utc`, sonu `Z` ile biten) kullanılır.
   - Arayüzde kullanıcıya göstermek için `timestamp_local` alanı hazırdır (İsveç saati Europe/Stockholm).

