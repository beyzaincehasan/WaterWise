# WaterWise – Veri Analizi ve Yapay Zekâ Modülü: Teknik Metodoloji

**Proje:** WaterWise – Yapay Zekâ Destekli Evsel Su Tüketimi ve Anomali Tespit Sistemi
**Modül sorumlusu:** Beyza İNCEHASAN (Veri Analizi ve Yapay Zekâ)
**Model sürümü:** 1.0.0 · **Ortam:** Python 3.13.14, scikit-learn 1.9.1, pandas 3.0.6, numpy 2.5.3

Bu belge veri setini, ön işleme kararlarını, normal tüketim profilini, özellik mühendisliğini ve Isolation
Forest modelini anlatır. Deney sonuçları `docs/model_evaluation.md`, backend kullanımı
`docs/backend_integration.md` belgesindedir. Bu belgedeki bütün sayılar `python -m src.run_pipeline`
çalıştırılarak üretilmiştir.

---

## 1. Veri seti nereden alındı?

**HSB Living Lab Household Water Consumption Dataset** (Knutsson, J., Chalmers University of Technology, 2026;
lisans CC BY 4.0). Veri, Göteborg'daki HSB Living Lab araştırma binasındaki 28 dairede, 1 L çözünürlüklü ve
10 dakikalık raporlama yapan 214 darbe sayaçlı su sayacından toplanmıştır. Anonimleştirilmiş CSV
(`data/HSB_Living_Lab_Water_Consumption_Anonymized.csv`, `;` ayırıcı) 652 315 kayıt içerir ve
2019-12-31 – 2023-01-31 dönemini kapsar. Kaynak belgeler: `docs/README.txt`, `docs/DATA_DICTIONARY.txt`.

## 2. Veri setinde hangi sütunlar var?

| Sütun | Açıklama | Doğrulama sonucu |
|---|---|---|
| `timestamp` | 10 dakikaya yuvarlanmış zaman damgası | Sözlükte "UTC" yazıyor; ancak **yerel saat** olduğu doğrulandı (bölüm 4) |
| `date, hour, day_of_week, day_name, month, year` | `timestamp`'ten türetilmiş | %100 tutarlı |
| `sensor_id` | S0001–S0214 | Her sensör tek bir daire/oda/armatür/su tipine bağlı (1-1) |
| `apartment` | APT_001–APT_028 | 154 269 eksik → 62 ortak alan sensörü |
| `cluster_name` | CL_A–CL_I | 41 798 eksik (çamaşırhane, temizlik, ortak banyo) |
| `room_number, room_type` | Oda kimliği / türü | Eksik yok |
| `type` | soğuk / sıcak su | Eksik yok |
| `attached_to` | Tuvalet, mutfak musluğu, lavabo, duş, çamaşır makinesi | Eksik yok |
| `value` | Kayıt başına tüketim | **m³** (bölüm 4) |
| `aggregated_value` | Sözlükte belirsiz tanımlı | **Sensörün kümülatif sayaç endeksi (m³)** |

## 3. Eksik veriler nasıl yönetildi?

* **Daire bilgisi eksik (154 269 kayıt):** Bu kayıtların hepsi ortak kullanım alanlarına aittir (ortak alan
  mutfağı, ortak banyo, çamaşırhane, temizlik odası). Daire bazlı analizden **ayrılmış**, silinmemiş ve
  doldurulmamıştır (`data/processed/shared_area_records.parquet`, 1 284 m³). Daire modeline girmez.
* **Küme bilgisi eksik (41 798 kayıt):** Bu kayıtların hepsinde daire bilgisi de yoktur (çamaşırhane/temizlik/banyo).
  Bu yüzden ayrıca bir işlem yapılmamıştır.
* **Kayıt olmayan zaman aralıkları:** Kayıt yok diye doğrudan sıfır tüketim kabul **edilmemiştir.** İki durum
  sayaç endeksiyle birbirinden ayrılmıştır:
  1. **Gözlenen, tüketim yok:** Bir sensörün iki kaydı arasında kümülatif endeks tam olarak sonraki kaydın
     değeri kadar arttıysa aradaki sürede tüketim yoktur. Bu kural, 30 güne kadar olan sensör boşluklarının
     %99.9'undan fazlasında sağlanır. Sensörler yalnızca darbe olduğunda kayıt üretir.
  2. **Gözlenmedi (veri kaybı):** Endeks, kaydedilenden fazla ilerlediyse (> 0.5 L) aradaki aralık
     "gözlenmedi" olarak işaretlenir. 358 aralıkta toplam ~551 m³ kaydedilmemiş tüketim bulunmuştur.
     Bu tüketimin çoğu uzun sistem kesintilerine aittir.
  3. Ek güvenlik önlemi olarak bina genelinde **6 saatten uzun hiç kaydın olmadığı** aralıklar da gözlenmedi
     sayılır (15 kesinti, toplam 4 717 saat).
* Gözlenmeyen dilimler `NaN` olarak tutulur. Bir saat ancak 6 dilimin tamamı gözlendiyse kullanılır. Profil,
  eğitim ve değerlendirmede gözlenmeyen saatler dışarıda bırakılır.

## 4. Ölçüm birimi nasıl belirlendi?

Veri sözlüğü `value` için "litre" diyor, ancak üç bağımsız kanıt **m³** olduğunu gösteriyor:

1. README'de toplam tüketim 3 271 m³ olarak verilmiştir. CSV'de Σ`value` = **3 270.789**'dur. Değer litre olsaydı
   bina 3 yılda yalnızca 3.3 m³ tüketmiş olurdu, bu da 28 daire için kişi başı günde birkaç mililitre eder.
2. README sayaçların **1 L çözünürlüklü** olduğunu söyler. `value`'nun en küçük değeri ve adımı 0.001'dir ve
   tüm değerler 0.001'in tam katıdır (0 istisna). Yani 0.001 m³ = 1 L = bir darbedir.
3. `aggregated_value`, her sensör için zamanla monoton artan bir **kümülatif sayaç endeksidir**. Ardışık farkı
   kayıtların %99.9'unda `value`'ya eşittir. Endeks değerleri (ör. bir tuvalet için 84 m³) ancak m³ cinsinden
   anlamlıdır.

Ayrıca README'de belirtilen aykırı değer eşiği de "0.3 m³"tür ve `value` üst sınırı tam olarak 0.3'tür.
**Karar:** `value_liters = value × 1000`. Ham `value` sütunu korunmuştur. `aggregated_value` toplam tüketim
hesaplarında kullanılmamış, yalnızca veri kaybı tespitinde kullanılmıştır.

**Zaman dilimi:** Sözlük zaman damgalarının UTC olduğunu söyler. Ancak ilkbahar yaz saati günlerinde
(2021-03-28, 2022-03-27) **saat 02:xx'te hiç kayıt yoktur.** Sonbahar geri alımında ise (2020-10-25, 2021-10-31,
2022-10-30) kümülatif sayaç yalnızca 02:xx'te geri gider. Bu iki davranış ancak yerel duvar saatinde ortaya çıkar.
Ayrıca tüketimin hafta içi 07:00'de tepe yapması da yerel saatle uyumludur. Zaman damgaları **Europe/Stockholm**
olarak yerelleştirilmiş ve UTC'ye çevrilmiştir. Sonbahardaki belirsiz 65 kayıt, sensörün sayaç sırasına göre ilk
ya da ikinci geçişe atanmıştır. Bunun sonucunda UTC sıralamasında sayaçta **hiç geri adım kalmamıştır.** Model
özellikleri yerel saati kullanır. Backend çıktısı hem UTC hem yerel saati içerir.

## 5. Veri ön işleme aşamaları (`src/data_preprocessing.py`)

| # | Adım | Sonuç |
|---|---|---|
| 1 | CSV yükleme (`;`), şema kontrolü, tip dönüşümü | 652 315 × 16 |
| 2 | Kalite raporu (eksik, aralık, türetilmiş sütun tutarlılığı, sensör eşleşmesi) | `cleaning_report.json` |
| 3 | Tam tekrar satırların atılması (sayaç ilerlememiş tekrar iletim) | 140 satır |
| 4 | Aynı sensör + aynı zaman damgalı, farklı endeksli 565 satır **korunur** | 10 dk yuvarlaması; aynı dilimde toplanır |
| 5 | Negatif/sıfır/geçersiz değer kontrolü | 0 negatif, 0 sıfır (kaynakta sıfırlar filtrelenmiş) |
| 6 | DST-doğru yerel saat → UTC dönüşümü | 65 belirsiz satır çözüldü |
| 7 | `value_liters = value × 1000` | Toplam 3 270 229 L |
| 8 | Kullanım kategorisi standardizasyonu | Duş / Musluk (mutfak+lavabo) / Tuvalet / Makine; sıcak/soğuk |
| 9 | Ortak alan ayrımı | 497 932 daire, 154 243 ortak alan kaydı |
| 10 | Sayaç tutarlılığı, veri kaybı ve bina kesintisi tespiti | 358 kayıp aralığı, 15 kesinti |
| 11 | Yüksek debi işareti (≥100 L/10 dk) | 989 kayıt işaretlendi, **silinmedi** |
| 12 | Daire bazlı 10 dk dilim ve saatlik seriler | 755 142 daire-saat, %81.4 gözlenen |

Çıktılar: `data/processed/` (`records_clean.parquet`, `apartment_records.parquet`, `shared_area_records.parquet`,
`apartment_slots_10min.parquet`, `apartment_hourly.parquet/.csv`, `building_outages.csv`,
`sensor_data_loss_intervals.csv`, `apartment_hourly_features.parquet`, `cleaning_report.json`).

## 6. Hangi özellikler çıkarıldı? (`src/feature_engineering.py`)

**Analiz birimi:** daire-saat. Dairenin bütün armatürleri ile sıcak ve soğuk suyu toplanır. Özellik zinciri
`kayıtlar → 10 dk dilimler → saatlik seri → özellikler` şeklindedir ve eğitimde de tahminde de **aynı fonksiyonlar**
kullanılır. Toplu hesaplanan özelliklerden elde edilen skorlarla backend tahmin yolundan elde edilen skorların
birebir aynı olduğu test edilmiştir (`test_batch_and_online_scores_match`).

| Model özelliği | Tanım | Öneri formundaki karşılığı |
|---|---|---|
| `hour_sin`, `hour_cos` | Yerel saatin döngüsel kodlaması | hour |
| `is_weekend` | Cumartesi/Pazar | day_of_week |
| `log_consumption` | log(1 + saatlik litre) | consumption_liters / hourly_consumption |
| `log_prev_hour` | log(1 + önceki saat) | previous_hour_consumption |
| `log_rolling_3h_sum` | Hedef saat + önceki 2 saat toplamı | Kısa süreli süreklilik |
| `deviation_from_normal` | log(1+x) − log(1+aynı yerel saatin son 28 gün ort.) | historical_same_hour_mean, deviation_from_normal |
| `deviation_from_24h` | log(1+x) − log(1+önceki 24 saat ort.) | rolling_24h_mean |
| `deviation_from_7d` | log(1+x) − log(1+önceki 168 saat ort.) | rolling_7d_mean |
| `active_slots` | Saatteki tüketimli 10 dk dilim sayısı (0–6) | Tüketim sürekliliği |
| `log_continuous_activity_min` | Art arda tüketimli dilimlerin süresi (dk, en çok 12 saat) | continuous_flow_duration (**gösterge**) |
| `night_log_consumption` | Gece (00–06) ise log tüketim, değilse 0 | nighttime_consumption |
| `night_active_slots` | Gece ise aktif dilim sayısı, değilse 0 | Gece sürekliliği |

**Neden bu seçim?**
* Taban değerlerin kendisi yerine (ör. `rolling_7d_mean`) **dairenin kendi geçmişine göre log-oran sapmaları**
  kullanılmıştır. Daireler arasında 20 kat hacim farkı olduğu için ham taban değerler modelin büyük daireleri
  sürekli "olağandışı" görmesine yol açar. Ham taban değerler yine de hesaplanır ve backend çıktısında açıklama
  amacıyla döndürülür.
* **Süreklilik bir göstergedir, gerçek akış süresi değildir.** Veri 10 dakikalık darbe sayımlarından oluşur,
  akışın başlama ve bitiş anı ölçülmez. `continuous_activity_min`, art arda tüketim kaydı olan 10 dakikalık
  dilimlerin toplam süresidir. 6 L/saatin altındaki sızıntılar her dilimde darbe üretmeyebilir (bkz. stres testi).
* **Sızıntının önlenmesi:** Bütün geçmiş-tabanlı özellikler yalnızca hedef saatten önceki saatleri kullanır
  (`shift(1)`, `closed="left"`). Bu kural test edilmiştir: gelecekteki veriler 50 katına çıkarıldığında geçmiş
  saatlerin özellikleri değişmez (`test_no_future_leakage`). Tahmin fonksiyonu hedef saatten sonraki kayıtları
  yok sayar.
* **Eksik geçmiş:** Aynı-saat ortalaması için en az 7, 24 saatlik ortalama için en az 12, 7 günlük ortalama için en
  az 72 gözlenen saat gerekir. Bu koşul sağlanmazsa eğitimde satır dışarıda bırakılır. Tahminde ise eğitim dönemi
  profili yedek olarak kullanılır ve `fallback_used` / `warnings` alanlarında bildirilir.

## 7. Neden Isolation Forest seçildi?

* Veri setinde **doğrulanmış kaçak etiketi yoktur.** Bu yüzden gözetimsiz bir yöntem gerekir. Isolation Forest
  etiket istemez ve proje önerisinde de belirtilmiştir.
* Az sayıdaki ve normalden belirgin biçimde farklı gözlemleri, rastgele bölmelerle kısa yollarda izole ederek
  bulur. Su tüketiminde anomaliler seyrek ve belirgindir (gece sürekli akışı, ani hacim artışı).
* Ölçeklemeye ihtiyaç duymaz, karışık ölçekli özelliklerle çalışır ve hızlıdır (403 bin satır yaklaşık 8 saniyede
  eğitilir; 28 günlük geçmişle tek saatlik tahmin ölçülen ~60 ms sürer). Tek bir küçük dosya olarak kaydedilip yeniden eğitilmeden yüklenebilir.
* Sınırlılığı: skorlar olasılık değildir ve eksene paralel bölmeler etkileşimleri dolaylı yakalar. Bu yüzden
  gece etkileşimleri (`night_*`) açık özellik olarak eklenmiştir.

## 8. Model nasıl eğitildi? Tek model mi, daire bazlı mı?

**Zamansal ayrım** (veri setindeki uzun kesintiler doğal sınır olarak kullanılmıştır):

| Dönem | Yerel tarih aralığı | Kullanım | Gözlenen daire-saat |
|---|---|---|---|
| Eğitim | 2020-01-01 – 2021-11-22 | Model + normal profil | 403 083 (yeterli geçmişi olan) |
| Doğrulama | 2022-02-17 – 2022-06-30 | Eşik kalibrasyonu, tasarım kararları | 84 140 |
| Test | 2022-07-01 – 2023-01-31 | Yalnızca nihai raporlama | 115 202 |

**Global model + daireye uyarlanmış eşik seçildi.** Değerlendirmede üç seçenek karşılaştırılmıştır:

| Ölçüt | Daire bazlı 28 model | Tek global model (global eşik) | **Global model + uyarlanmış eşik** |
|---|---|---|---|
| Veri miktarı | Daire başına ≥10 976 satır; seyrek olaylar az | 403 bin satır | 403 bin satır |
| Sentetik yakalama (doğrulama, S1–S4) | 100 / 100 / 98.7 / 98.3 | 100 / 100 / 98.7 / 95.0 | 100 / 100 / 97.3 / 91.7 |
| Gerçek alarm oranı (doğrulama) | %3.03 | %3.00 | **%1.74** |
| %10'u aşan daire (doğrulama) | 0 (eşik kalibrasyonu gereği) | **3** (en yüksek %18.5) | **0** (en yüksek %3.0) |
| Yeni / bilinmeyen daire | Model yok | Çalışır | Çalışır (global eşik) |
| Bakım | 28 model + 28 eşik seti | 1 dosya | 1 dosya + eşik tablosu |

Daire bazlı modeller sentetik olayları biraz daha iyi yakalamaktadır. Buna karşın 28 ayrı modelin bakımı
gerekir, yeni bir daire için model bulunmaz ve her dairenin seyrek olay örneği azdır. Tek global model bilinmeyen
dairelerde de çalışır ve bakımı kolaydır. Ancak doğrulama döneminde 3 yüksek hacimli dairede (8 sensörlü
APT_002, APT_003, APT_017) %10–18 alarm üretmiştir. Bu sorun bir eşik politikasıyla giderilmiştir:

> **eşik_daire = max(global eşik, dairenin doğrulama skorlarının aynı yüzdeliği)**

Eşik yalnızca yukarı yönde değişebilir. Gürültülü dairelerde (6 daire: APT_002, 003, 005, 010, 017, 028)
yükselir, sessiz dairelerde global eşik korunur ve hassasiyet düşmez. Bu karar test sonuçlarına göre değil,
doğrulama dönemindeki daire bazlı alarm oranlarına göre verilmiştir. İlk sürümün (yalnızca global eşik) test
sonuçları da `model_evaluation.md` belgesinde gizlenmeden raporlanmıştır.

## 9. Hangi hiperparametreler kullanıldı?

| Parametre | Değer | Gerekçe |
|---|---|---|
| `n_estimators` | 300 | Doğrulamada 100 ile benzer sonuç; daha çok ağaç, skorun rastgele ağaç seçimine bağlı dalgalanmasını azaltır |
| `max_samples` | 512 | Varsayılan 256 doğrulamada S4'ü zayıf yakaladı (%65); 512 dengeli |
| `max_features` | 1.0 | Tüm özellikler |
| `contamination` | "auto" | Kullanılmaz; eşikler doğrulama yüzdeliklerinden belirlenir |
| `bootstrap` | False | Varsayılan |
| `random_state` | 42 | Tekrar üretilebilirlik |

Hiperparametre duyarlılığı yalnızca doğrulama verisinde incelenmiştir. `max_samples=2048`, S4 yakalamasında
doğrulamada küçük bir artış gösterdi (%95.0 → %99.3). Önceden belirlenen yapılandırma (512) bütün hedefleri
karşıladığı ve test verisi tekrar tekrar kullanılmak istenmediği için sürüm 1.0.0'da değiştirilmemiştir.
Sonraki sürüm için aday olarak not edilmiştir.

**Skor tanımı:** `anomaly_score = −IsolationForest.score_samples(X)`. Bu değer Liu vd. (2008) anomali skoru
s(x) = 2^(−E[h(x)]/c(n))'dir ve (0, 1] aralığındadır. **Yüksek skor daha olağandışı demektir.** Tipik gözlemler
0.38–0.55 arasındadır; 1'e yaklaştıkça gözlem daha kolay izole edilir. **Skor bir olasılık değildir** ve
"%87 kaçak olasılığı" gibi yorumlanmamalıdır.

**Durum eşikleri** (doğrulama dönemi gerçek saatlerinin skor yüzdeliklerinden):

| Durum | Kural (global) |
|---|---|
| Normal | skor < 0.6061 |
| Şüpheli | 0.6061 ≤ skor < 0.6575 (doğrulama q = 0.97) |
| Anormal | skor ≥ 0.6575 (doğrulama q = 0.995) |

Daireye özel eşikler `models/model_metadata.json` → `apartment_thresholds` içindedir.

## 10. Normal tüketim profili nasıl oluşturuldu? (`src/normal_profile.py`)

* **Veri aralığı:** Yalnızca eğitim dönemi (2020-01-01 – 2021-11-22, yerel saat). Doğrulama ve test dönemlerinden
  profile hiçbir bilgi girmez.
* **Eksik gözlem yöntemi:** Yalnızca 6 dilimi de gözlenen saatler ve bütün saatleri gözlenen yerel günler
  kullanılır. DST nedeniyle 23 veya 25 saatlik günler de tam gün sayılır. Kesinti dönemleri sıfırla doldurulmaz.
* **İçerik (daire başına):** günlük ortalama, medyan, std, p05, p95 ve normal aralık [p05, p95]; değişim katsayısı;
  sıfır tüketimli gün oranı; 24 yerel saat için ortalama, medyan, std, p95 ve aktiflik olasılığı; haftanın
  günlerine göre günlük ortalama; hafta içi/sonu karşılaştırması; gece profili (saatlik ortalama ve p95, gecelik
  toplam ortalama ve p95, aktif dilim sayısı); süreklilik göstergesi (p95/p99 dakika); 10 dakikalık dilim
  istatistikleri. Bilinmeyen daireler için bina geneli medyan profil de vardır.
* **Kullanım:** (1) Uyarı mesajlarında "normal ortalama X L, üst sınır Y L – tespit edilen Z L" karşılaştırması;
  (2) geçmiş bağlam yetersizse özellik hesabında yedek taban değeri. Modelin kayan özellikleri (son 24 saat,
  7 gün, 28 gün) ise her zaman hedef saatten önceki gerçek geçmişten hesaplanır. Böylece uzun dönemli
  davranış değişimine uyum sağlanır.
* **Dosya:** `models/normal_profiles.json`.

## 11. Sentetik anomaliler nasıl üretildi? (`src/synthetic_anomalies.py`)

Doğrulanmış kaçak etiketi olmadığından model, gerçek seriye eklenen kontrollü olaylarla değerlendirilmiştir.

* **Ayrı tutma:** Olaylar yalnızca bellekteki kopyaya eklenir. İşlenmiş gerçek veri değişmez. Olay katalogları
  `data/synthetic/*_events.csv`, parametreler `data/synthetic/scenario_parameters.json` dosyasındadır.
* **Gerçekçilik:** Enjeksiyon 10 dakikalık dilim düzeyinde ve 1 L sayaç çözünürlüğüne uygun **tam litre darbeler**
  olarak yapılır. Ardından eğitimdeki özellik hattının aynısı çalıştırılır. Miktarlar dairenin kendi eğitim
  profiline göre ölçeklenir.
* **Yerleşim:** Olaylar rastgele daire-günlerine yerleştirilir. Günün bütün saatleri gözlenmiş olmalı ve önceki
  28 günün en az %70'i gözlenmiş olmalıdır. Her olay diğerlerinden bağımsız değerlendirilir. Doğrulama (tohum 101)
  ve test (tohum 202) olayları ayrı dönemlerde, ayrı tohumlarla üretilir. Senaryo başına 300 olay vardır.

| Senaryo | Parametreler |
|---|---|
| S1 Gece sürekli akış | 02:00–05:00 yerel, 3 saat, sabit 6–30 L/saat (her 10 dk'da ≥1 darbe) |
| S2 Olağandışı yüksek tüketim | Gündüz 07–21 arası başlayan 2 saat; her saat için o saatin profil p95 değerinin (en az 10 L) 2–4 katı ek tüketim; dilim başına en çok 150 L |
| S3 Alışılmadık saat | Dairenin aktiflik olasılığı en düşük 6 saatinden biri; 20–30 dk içinde 30–80 L |
| S4 Kısa süreli artış | Rastgele saat, tek 10 dk dilim; dairenin aktif dilim p99 değerinin 2–4 katı (40–300 L) |
| Stres testi S1L | 02:00–05:00, 1–6 L/saat (darbeler aralıklı); ana hedefe dahil değil |

## 12–13. Değerlendirme ve gerçek sonuçlar

Ayrıntılar: **`docs/model_evaluation.md`**. Test dönemi özeti (nihai yapılandırma):

| Ölçüt | Hedef (öneri formu) | Gerçekleşen (test) |
|---|---|---|
| Sentetik sürekli akış (S1) yakalama | ≥ %90 | **%100** (300/300; Anormal düzeyinde de %100) |
| Normal kabul edilen test saatlerinde alarm oranı | < %10 | **%1.57** (≥Şüpheli), %0.34 (Anormal) |
| S2 / S3 / S4 yakalama | – | %100 / %97.7 / %93.3 |

## 14. Modelin sınırlılıkları

1. **Etiket yok:** Gerçek verideki alarm oranı kesin yanlış pozitif oranı değildir. Gerçek anomaliler de içerebilir.
   Sentetik başarı da gerçek kaçak başarısının kanıtı değildir.
2. **Sentetik senaryolar tasarımcının varsayımlarını yansıtır.** S1'in %100 olması, bu veri setinde gecelerin çok
   sessiz olmasından ve 6 L/saatin her dilimde darbe üretmesinden kaynaklanır. 1–2 L/saatlik sızıntılarda
   yakalama %80'e düşer.
3. **Süreklilik bir göstergedir:** Gerçek akış süresi ölçülmez. 10 dakikalık yuvarlama ve 1 L çözünürlük nedeniyle
   küçük damlatmalar görülemeyebilir.
4. **Uyarlanabilir taban değerler** (son 7/28 gün) dairenin davranış değişimine uyum sağlar. Bunun bir sonucu
   olarak haftalarca süren kalıcı bir kaçak zamanla "normal" kabul edilebilir. Daireye uyarlanmış eşikler de
   sürekli gürültülü bir dairenin (ör. kalıcı gece akışı olduğundan şüphelenilen APT_005) alarmlarını azaltır.
   Bu tür kalıcı durumlar için profil karşılaştırması (`normal_consumption_liters`) ve uzun dönem trend
   izlenmelidir.
5. **Daire-gün düzeyinde gürültü:** Saatlik alarm oranı düşük olsa da daire-günlerin %26.5'inde en az bir Şüpheli
   saat vardır. Kullanıcıya bildirim için yalnızca **Anormal** durumu kullanılmalıdır (daire-gün %6.95).
   Şüpheli durum dashboard'da gösterilebilir.
6. **Gece tanımı sabittir** (00–06 yerel). Vardiyalı çalışan haneler için kişiselleştirme gerekebilir.
7. **Veri seti tek bir binaya aittir** (İsveç, araştırma binası, 2020–2023; pandemi dönemi dahil). Başka bina
   veya ülkelere genellenmesi doğrulanmamıştır.
8. Saatlik çözünürlük nedeniyle bir alarm en erken ilgili saat tamamlandığında üretilebilir.
9. Sistem kesin tesisat kaçağı teşhisi koymaz. Yalnızca "olası kaçak / olağandışı kullanım" uyarısı verir.

## 15. Backend ekibi modeli nasıl kullanacak?

`from src.predict import load_detector, predict_anomaly` ile modeli yeniden eğitmeden kullanır. Gerekli
dosyalar `models/` klasöründedir. Girdi/çıktı sözleşmesi, hata kodları ve örnekler için:
**`docs/backend_integration.md`** · çalışan örnek: `examples/backend_usage_example.py`.

---

## Yeniden üretme

```powershell
cd C:\Users\Beyza\Desktop\WaterWise
venv\Scripts\python.exe -m src.run_pipeline        # ön işleme → EDA → eğitim → değerlendirme (~2.5 dk)
venv\Scripts\python.exe -m pytest tests -q          # 46 otomatik test
```

## Kaynakça

* Knutsson, J. (2026). Household water consumption patterns revealed through high-resolution fixture-level
  monitoring in a Swedish living lab. *Journal of Cleaner Production*. Veri seti: CC BY 4.0.
* Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation Forest. *IEEE ICDM*, 413–422.
* Pedregosa, F. vd. (2011). Scikit-learn: Machine Learning in Python. *JMLR*, 12, 2825–2830.
