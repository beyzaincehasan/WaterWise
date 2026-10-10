# WaterWise AI Modülü – Backend Entegrasyon Rehberi

**Hedef okuyucu:** Backend ve veritabanı geliştiricisi (FastAPI / PostgreSQL)
**Model sürümü:** 1.0.0 · **Python:** 3.13 · Modeli kullanmak için **yeniden eğitim gerekmez.**

Bu rehber, eğitilmiş Isolation Forest modelini backend'e bağlamak için gereken dosyaları, fonksiyonları,
girdi/çıktı sözleşmesini ve hata kodlarını tanımlar. Endpoint, veritabanı şeması ve arayüz tasarımı backend
ekibine aittir; burada yalnızca AI modülünün nasıl çağrılacağı anlatılır.

---

## 1. Teslim edilen dosyalar

| Dosya | Görev | Zorunlu |
|---|---|---|
| `models/isolation_forest.joblib` | Eğitilmiş model + özellik listesi + global ve daire eşikleri | ✅ |
| `models/normal_profiles.json` | 28 dairenin normal tüketim profili + bina geneli yedek profil | ✅ |
| `models/model_metadata.json` | Sürüm, hiperparametreler, eşikler, eğitim dönemi, skor tanımı | ✅ (bilgi) |
| `src/__init__.py`, `src/config.py` | Paket ve sabitler | ✅ |
| `src/feature_engineering.py` | Özellik hesabı (eğitimle birebir aynı) | ✅ |
| `src/normal_profile.py` | Profil yükleme | ✅ |
| `src/predict.py` | **Tahmin API'si** | ✅ |
| `src/synthetic_anomalies.py` | Demo için kaçak kaydı üretici (`make_demo_leak_records`) | Demo için |
| `requirements-ai.txt` | Sabitlenmiş bağımlılıklar | ✅ |
| `examples/backend_usage_example.py` | Çalışan örnek | Önerilir |
| `data/processed/apartment_records.parquet` | Temizlenmiş daire kayıtları (UTC, litre), veritabanına aktarım için | Önerilir |
| `data/processed/building_outages.csv`, `sensor_data_loss_intervals.csv` | Bilinen izleme kesintileri | Önerilir |

`src/` klasörü proje kökünden içe aktarılır (`from src.predict import ...`). Backend projesi farklı bir dizindeyse
`src/` ve `models/` klasörlerini birlikte kopyalayın. Model klasörü `load_detector(model_dir=...)` ile
değiştirilebilir. Tahmin için `train_model.py`, `evaluate_model.py`, `eda.py` ve matplotlib **gerekmez.**

### Bağımlılıklar

```powershell
pip install -r requirements-ai.txt
```
Çalışma zamanında gerekenler: `numpy==2.5.3, pandas==3.0.6, scikit-learn==1.9.1, scipy==1.18.1, joblib==1.6.0,
tzdata==2026.5` (parquet okumak için `pyarrow==26.0.0`). **scikit-learn sürümü değişirse** joblib dosyası
yüklenemeyebilir veya uyarı verebilir. Bu durumda aynı sürümü kullanın ya da modeli yeniden eğitin
(`python -m src.run_pipeline --skip-eda`).

## 2. Hızlı başlangıç

```python
from src.predict import load_detector, predict_anomaly, WaterWiseInputError

detector = load_detector()            # uygulama açılışında BİR KEZ (≈0.9 sn); önbelleğe alınır

result = predict_anomaly(
    apartment_id="APT_011",
    records=[  # dairenin ham 10 dk kayıtları: hedef saat + önceki 28 gün
        {"timestamp": "2022-11-24T01:10:00Z", "consumption_liters": 3.0},
        {"timestamp": "2022-11-24T01:20:00Z", "consumption_liters": 3.0},
        # ...
    ],
    target_timestamp="2022-11-24T03:00:00+01:00",   # değerlendirilecek saat
    history_start="2022-10-27T03:00:00+01:00",      # kayıtların kapsadığı izleme başlangıcı
    detector=detector,
)
print(result["status"], result["anomaly_score"], result["message"])
```

Çalışan tam örnek (gerçek veriyle test edilmiştir):
```powershell
venv\Scripts\python.exe examples\backend_usage_example.py
```

## 3. API

### `load_detector(model_dir=None) -> WaterWiseAnomalyDetector`
Model, profil ve metadata dosyalarını yükler ve önbelleğe alır. Dosya yoksa veya özellik listesi kodla uyumsuzsa
`WaterWiseModelError` fırlatır.

### `predict_anomaly(apartment_id, records, target_timestamp=None, history_start=None, unobserved_intervals=None, detector=None) -> dict`
**Tek bir saat** için sonuç döndürür.

### `detector.evaluate(apartment_id, records, start=None, end=None, history_start=None, unobserved_intervals=None) -> list[dict]`
`[start, end]` aralığındaki **her saat** için sonuç listesi döndürür (dashboard'daki son 24 saat, toplu yeniden
hesaplama vb.). Her öğe `predict_anomaly` çıktısıyla aynı yapıdadır. Geçmiş bağlam bir kez hesaplanır; 24 saatlik
değerlendirme de tek saatlik değerlendirme kadar sürer (~60 ms).

### Diğer
* `detector.known_apartments()` → profili olan daireler (APT_001 … APT_028)
* `detector.thresholds_for(apartment_id)` → `(eşikler, "apartment" | "global")`
* `detector.metadata` → `model_metadata.json` içeriği

## 4. Girdi sözleşmesi

| Parametre | Tip | Açıklama |
|---|---|---|
| `apartment_id` | `str` | "APT_001" … "APT_028". Bilinmeyen bir daire de kabul edilir; bina geneli profil kullanılır ve uyarı döner |
| `records` | `list[dict]` veya `pandas.DataFrame` | Dairenin **ham 10 dakikalık sensör kayıtları** (bütün armatürler, sıcak ve soğuk su ayrı satırlar olabilir; aynı 10 dk dilimine düşenler toplanır) |
| `records[].timestamp` | ISO-8601 metni veya datetime | Saat dilimli (`Z`, `+01:00`) önerilir. **Saat dilimsiz değerler Europe/Stockholm yerel saati kabul edilir** (veri setindeki CSV ile aynı). Karışık ofsetler desteklenir |
| `records[].consumption_liters` | `float ≥ 0` | Litre. Alternatif olarak ham CSV biçiminde `value` (m³) gönderilebilir; ×1000 ile litreye çevrilir |
| `records[].apartment` | `str` (isteğe bağlı) | Verilirse `apartment_id` ile aynı olmalı |
| `target_timestamp` | ISO / datetime | Değerlendirilecek saatin içindeki herhangi bir an (saat başına yuvarlanır). Verilmezse en son kaydın saati kullanılır |
| `history_start` | ISO / datetime | Kayıtların kapsadığı izleme döneminin başlangıcı. Verilmezse en eski kaydın saati kabul edilir |
| `unobserved_intervals` | `[(başlangıç, bitiş), ...]` | Sensör veya veri toplama kesintileri. Bu aralıklar sıfır tüketim değil, "veri yok" sayılır |

### Geçmiş kayıtlar neden gerekli ve nasıl sağlanmalı?

Model tek bir kayda bakmaz. Hedef saati, dairenin **son 24 saat, son 7 gün ve son 28 gündeki aynı saat**
ortalamalarıyla karşılaştırır ve süreklilik için önceki dilimlere bakar. Bu yüzden tek bir tüketim kaydından
güvenilir tahmin yapılamaz.

**Önerilen sorgu** (hedef saat `T` için):
```sql
SELECT timestamp_utc, value_liters
FROM consumption_records
WHERE apartment = :apartment_id
  AND timestamp_utc >= :T - INTERVAL '28 days'
  AND timestamp_utc <  :T + INTERVAL '1 hour';
```
Ardından `history_start = T - 28 gün` geçirin.

* **Kritik semantik:** Sensörler **yalnızca tüketim olduğunda** kayıt üretir. Model, `[history_start, T'nin sonu]`
  aralığında kaydı olmayan 10 dakikalık dilimleri **0 L** kabul eder. Bu yüzden:
  * `history_start`'ı gerçekten izleme yapılan dönemin başlangıcı olarak verin. Daha geriye verirseniz izlenmeyen
    günler sıfır sayılır ve taban değerler düşer.
  * Bilinen kesintileri `unobserved_intervals` ile bildirin. Veri setindeki kesintiler
    `data/processed/building_outages.csv` (tüm daireler) ve `sensor_data_loss_intervals.csv` (daire bazlı)
    dosyalarındadır.
* **En az geçmiş:** 7 gün önerilir, ideal olan 28 gündür. Daha kısa geçmişte tahmin yine yapılır. Bu durumda eğitim
  profili yedek olarak kullanılır ve `warnings` içinde `SHORT_HISTORY` / `PROFILE_FALLBACK` döner.
* Hedef saatten **sonraki** kayıtlar yok sayılır; gelecek bilgisi kullanılmaz.
* Kayıtlar sıralı olmak zorunda değildir; tekrar eden zaman damgaları toplanır.

## 5. Çıktı sözleşmesi

Gerçek bir çıktı (`examples/backend_usage_example.py`, demo kaçak senaryosu):

```json
{
  "apartment_id": "APT_011",
  "timestamp": "2022-11-24T02:00:00Z",
  "timestamp_local": "2022-11-24T03:00:00+01:00",
  "period_minutes": 60,
  "consumption_liters": 18.0,
  "status": "Anormal",
  "anomaly_score": 0.7486,
  "thresholds": {
    "suspicious": 0.6061,
    "anomalous": 0.6575,
    "scope": "apartment"
  },
  "normal_consumption_liters": 0.3,
  "normal_upper_liters": 2.0,
  "historical_same_hour_mean_liters": 0.2,
  "rolling_24h_mean_liters": 1.83,
  "rolling_7d_mean_liters": 0.36,
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

| Alan | Tip | Açıklama |
|---|---|---|
| `timestamp` | str (UTC, `Z`) | Değerlendirilen saatin başlangıcı. Veritabanında anahtar olarak önerilir |
| `timestamp_local` | str | Aynı an, Europe/Stockholm yerel saati (arayüzde gösterim için) |
| `period_minutes` | int | Her zaman 60 (saatlik analiz birimi) |
| `consumption_liters` | float | O saatteki toplam tüketim (L) |
| `status` | `"Normal" \| "Şüpheli" \| "Anormal"` | Durum |
| `anomaly_score` | float, (0, 1] | **Yüksek = daha olağandışı.** Olasılık değildir; "%75 kaçak" diye gösterilmemelidir |
| `thresholds` | obj | Kullanılan eşikler; `scope`: `apartment` (daireye uyarlanmış) veya `global` |
| `normal_consumption_liters`, `normal_upper_liters` | float | Eğitim profilindeki bu saatin ortalaması ve p95 değeri ("normal – tespit edilen" karşılaştırması için) |
| `historical_same_hour_mean_liters`, `rolling_24h_mean_liters`, `rolling_7d_mean_liters` | float | Modelin kullandığı yakın geçmiş taban değerleri |
| `active_10min_intervals` | int 0–6 | Saatte tüketim kaydı olan 10 dk dilim sayısı |
| `continuous_activity_minutes` | int | Art arda tüketimli dilimlerin süresi. **Gerçek akış süresi değil, bir göstergedir** |
| `is_night` | bool | Yerel 00:00–06:00 |
| `reasons` | list[{code, text}] | Açıklamalar; status `Normal` ise boş liste |
| `message` | str | Kullanıcıya gösterilecek Türkçe uyarı metni |
| `history` | obj | Geçmiş bağlamın yeterliliği |
| `warnings` | list[str] | `UNKNOWN_APARTMENT`, `SHORT_HISTORY`, `PROFILE_FALLBACK` (önek: açıklama) |
| `disclaimer` | str | Teşhis olmadığına dair sabit not |
| `model_version` | str | Model sürümü |

**Gerekçe kodları:** `NIGHT_CONTINUOUS_FLOW`, `HIGH_CONSUMPTION`, `UNUSUAL_HOUR`, `SHORT_SPIKE`,
`LONG_CONTINUOUS_USE`, `DEVIATION_FROM_NORMAL`, `PATTERN_COMBINATION`, `GENERIC_PROFILE`.

## 6. Hata durumları

Geçersiz girdiler `WaterWiseInputError` (bir `ValueError` alt sınıfı) fırlatır. Hatanın `.code` alanı makine
tarafından okunabilir koddur, `.message` alanı Türkçe açıklamadır. Önerilen HTTP karşılıkları:

| `code` | Neden | Önerilen HTTP |
|---|---|---|
| `NO_RECORDS` | `records` boş veya `None` | 422 |
| `INVALID_RECORDS` | `records` liste/DataFrame değil | 422 |
| `MISSING_FIELD` | `timestamp` veya `consumption_liters`/`value` yok | 422 |
| `INVALID_VALUE` | Tüketim sayısal veya sonlu değil | 422 |
| `NEGATIVE_VALUE` | Negatif tüketim | 422 |
| `INVALID_TIMESTAMP` | Zaman damgası çözümlenemedi | 422 |
| `APARTMENT_MISMATCH` | Kayıtlarda başka bir daire var | 422 |
| `INVALID_APARTMENT` | `apartment_id` boş veya metin değil | 422 |
| `INVALID_RANGE` | `start > end` veya `history_start` hedef saatten sonra | 422 |
| `TARGET_NOT_OBSERVED` | Hedef saat `unobserved_intervals` içinde, değerlendirilemez | 409 veya "veri yok" durumu |
| `WaterWiseModelError` | Model dosyaları yok veya uyumsuz (sunucu yapılandırma hatası) | 500 |

```python
try:
    result = predict_anomaly(apt, records, target, history_start, detector=detector)
except WaterWiseInputError as e:
    return {"error": e.code, "detail": e.message}       # 422
```

## 7. Önerilen kullanım politikası

* **Bildirim:** Kullanıcıya bildirim (push/e-posta) yalnızca `status == "Anormal"` olduğunda gönderilsin.
  Testte daire-günlerin %6.95'inde en az bir Anormal saat görülmüştür. `Şüpheli` durum dashboard'da sarı
  rozet olarak gösterilsin; daire-günlerin %26.5'inde en az bir Şüpheli saat vardır ve bu bildirim için fazladır.
* **Alarm kaydı:** Ardışık Anormal saatler tek bir "olay" olarak birleştirilebilir (ör. 01:00–04:00 gece akışı).
* **Gösterim:** `anomaly_score` olasılık olarak sunulmamalıdır. Arayüzde `message`, `reasons[].text` ve
  `normal_consumption_liters` – `consumption_liters` karşılaştırması gösterilmelidir.
* **Zamanlama:** Saatlik analiz yapıldığı için bir saat, ancak o saat tamamlandıktan sonra (ör. 03:00–04:00
  saati için 04:00'ten sonra) değerlendirilmelidir. Tamamlanmamış bir saat eksik tüketimle değerlendirilir.

## 8. Demo senaryosu (öneri formundaki "Normal → Anormal" gösterimi)

```python
from src.synthetic_anomalies import make_demo_leak_records

leak = make_demo_leak_records("2022-11-24 01:00", hours=3, rate_l_per_hour=18)   # yerel saat
# Demo akışında bu kayıtlar gerçek kayıtların arkasına eklenip veritabanına yazılır;
# ardından ilgili saatler için predict_anomaly çağrılır.
```
Gerçek çalıştırma sonucu (APT_011): 00:00 Normal (skor 0.395) → 01:00, 02:00, 03:00 **Anormal**
(0.743 / 0.748 / 0.749).

## 9. Performans

Ölçüm ortamı: geliştirme bilgisayarı, Windows 11, Python 3.13.

| İşlem | Süre |
|---|---|
| `load_detector()` (ilk yükleme) | ~0.9 sn |
| 28 günlük geçmişle tek saatlik tahmin (APT_017, 2 196 kayıt) | ~63 ms |
| Aynı geçmişle 24 saatin toplu değerlendirmesi | ~63 ms |
| Model dosyası boyutu | 1.7 MB |

## 10. Modelin güncellenmesi

* Yeniden eğitim: `venv\Scripts\python.exe -m src.run_pipeline` (~2.5 dk). Bu komut `models/` altındaki üç dosyayı
  yeniler; değerlendirme raporları da güncellenir.
* Eşikler `models/isolation_forest.joblib` içindedir ve `model_metadata.json` dosyasında okunabilir biçimde
  tekrarlanır. Elle değiştirilmemelidir.
* `config.MODEL_VERSION` her yeniden eğitimde güncellenmeli, tahmin sonuçlarıyla birlikte `model_version`
  veritabanına kaydedilmelidir.

## 11. Sık sorulanlar

**Saatlik toplanmış veri gönderebilir miyim?** Hayır. Süreklilik özellikleri (`active_10min_intervals`, ardışık
dilimler) ham 10 dakikalık kayıtlar gerektirir. Saatlik özet tabloları arayüz için ayrıca tutulabilir.

**Ortak alan sensörleri ne olacak?** Daire bilgisi olmayan 62 sensör (ortak mutfak, banyo, çamaşırhane) modelin
kapsamı dışındadır. `apartment_id` olmadan tahmin yapılmaz. Bu kayıtlar raporlama için
`shared_area_records.parquet` dosyasındadır.

**Yeni bir daire eklenirse?** Tahmin bina geneli profil ve global eşikle çalışır (`UNKNOWN_APARTMENT` uyarısı
döner). Daireye özel profil için en az birkaç haftalık veriyle yeniden eğitim önerilir.

**Zaman damgalarını hangi saat diliminde saklamalıyım?** UTC (`timestamp_utc`) önerilir. Ham CSV'deki
`timestamp` yerel saattir; `data/processed/*.parquet` dosyalarında `timestamp_utc` ve `timestamp_local`
sütunları hazırdır.
