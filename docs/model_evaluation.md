# WaterWise – Model Değerlendirme Raporu

Kod: `src/evaluate_model.py` · Ham sonuçlar: `outputs/reports/evaluation_results.json` · Tablolar:
`outputs/reports/evaluation_tables.md` · Olay bazlı sonuçlar: `outputs/anomalies/` · Grafikler: `outputs/figures/13–17`

Bu belgedeki bütün sayılar gerçek deney çıktılarıdır (`python -m src.evaluate_model`, deterministik, ~2 dk).

## 1. Protokol

| Bileşen | Ayrıntı |
|---|---|
| Zamansal ayrım | Eğitim 2020-01-01 – 2021-11-22 · Doğrulama 2022-02-17 – 2022-06-30 · Test 2022-07-01 – 2023-01-31 |
| Eğitim verisi | 403 083 daire-saat (yeterli geçmişi olan, gözlenen saatler) |
| Eşik kalibrasyonu | Doğrulama dönemi gerçek skorlarının q=0.97 (Şüpheli) ve q=0.995 (Anormal) yüzdelikleri + daireye uyarlanmış yalnızca yukarı yönlü eşik |
| Tasarım kararları | Yalnızca doğrulama verisi ve doğrulama sentetik olaylarıyla (tohum 101) verildi |
| Test | Sabitlenmiş model ve eşiklerle, ayrı tohumlu (202) sentetik olaylarla raporlandı |
| Yakalama tanımı | Olayın kapsadığı saatlerden en az biri ≥ Şüpheli ise olay "yakalandı" sayılır. Anormal düzeyi ve saat bazlı oran ayrıca verilir |
| Alarm oranı | Gerçek, etiketsiz, gözlenen saatlerde ≥ Şüpheli oranı |

> **Önemli:** Veri setinde doğrulanmış "normal kullanım" etiketi yoktur. Gerçek saatlerdeki alarm oranı bu
> nedenle kesin bir **yanlış pozitif oranı değildir.** Gerçek anomaliler (ör. arızalı rezervuar) de içerebilir;
> gerçek yanlış alarm oranı bu değere eşit veya ondan düşüktür.

## 2. Proje hedefleri ve gerçekleşen sonuçlar (test dönemi)

| Hedef (öneri formu) | Gerçekleşen | Durum |
|---|---|---|
| Sentetik sürekli akış anomalilerinin en az %90'ı tespit edilmeli | **%100.0** (300/300 olay, hepsi Anormal düzeyinde) | ✅ |
| Seçilen normal kullanım test verilerinde alarm oranı < %10 | **%1.57** saat bazında (Anormal: %0.34) | ✅ |

## 3. Gerçek veride alarm oranları

| Küme | Saat | ≥ Şüpheli | Anormal | Gece saatleri ≥ Şüpheli | Daire-gün ≥ Şüpheli | Daire-gün Anormal |
|---|---|---|---|---|---|---|
| Eğitim | 403 083 | %1.85 | %0.42 | %4.97 | %29.85 | %8.14 |
| Doğrulama | 84 140 | %1.74 | %0.29 | %5.02 | %30.07 | %6.16 |
| **Test** | **115 202** | **%1.57** | **%0.34** | %4.51 | %26.51 | %6.95 |
| Test – seçilmiş normal¹ | 115 195 | %1.57 | %0.34 | %4.51 | %26.43 | %6.95 |

¹ Tek kayıtta ≥100 L/10 dk değeri (olası gerçek anomali veya toplu gönderim) içeren 7 saat çıkarılmıştır.

**Yorum:** Eğitim, doğrulama ve test oranları birbirine yakındır. Bu, modelin zaman içinde kararlı olduğunu
gösterir. Gece saatlerindeki alarm oranı daha yüksektir; bunun nedeni geceleri tüketimin nadir olması ve her
gece kullanımının daha olağandışı görünmesidir. **Daire-gün düzeyinde** her dört günden birinde en az bir
Şüpheli saat görülür. Bu oran kullanıcıya doğrudan bildirim göndermek için fazladır. Önerilen politika:
**bildirim yalnızca Anormal durumda gönderilsin** (daire-gün %6.95), Şüpheli durum dashboard'da gösterilsin.

## 4. Sentetik anomali sonuçları

### Test (nihai, senaryo başına 300 olay)

| Senaryo | Yakalama (≥ Şüpheli) | Yakalama (Anormal) | Saat bazlı | Medyan max skor |
|---|---|---|---|---|
| S1 Gece sürekli akış (6–30 L/saat, 02–05) | **%100.0** | %100.0 | %100.0 | 0.745 |
| S2 Olağandışı yüksek tüketim | **%100.0** | %91.3 | %99.8 | 0.679 |
| S3 Alışılmadık saatte yoğun kullanım | **%97.7** | %82.0 | %97.7 | 0.712 |
| S4 Kısa süreli artış (tek 10 dk) | **%93.3** | %30.0 | %93.3 | 0.640 |

### Doğrulama (tasarım kararları için kullanıldı)

| Senaryo | ≥ Şüpheli | Anormal |
|---|---|---|
| S1 | %100.0 | %100.0 |
| S2 | %100.0 | %85.3 |
| S3 | %97.3 | %79.3 |
| S4 | %91.7 | %29.3 |

**S1 debiye göre (test):** 6–10, 10–15, 15–20, 20–25 ve 25–30 L/saat aralıklarının hepsinde %100.

**Stres testi – sayaç çözünürlüğünün altındaki sızıntılar (1–6 L/saat, 300 olay, ana hedefe dahil değil):**

| Debi (L/saat) | 1–2 | 2–3 | 3–4 | 4–5 | 5–6 | Toplam |
|---|---|---|---|---|---|---|
| Yakalama (≥ Şüpheli) | %80.0 | %98.3 | %100 | %100 | %100 | %96.0 (Anormal %64.0) |

1–2 L/saatlik bir sızıntı 30–60 dakikada bir darbe üretir. Bu durumda dilimler aralıklı görünür ve süreklilik
göstergesi zayıflar. Modelin pratik alt sınırı yaklaşık 2 L/saattir.

**Enjeksiyondan önce aynı pencere zaten alarm veriyor muydu? (test)** S1 %9.3, S2 %0.7, S3 %2.0, S4 %2.0.
S1 olaylarının %9.3'ü, gerçek veride zaten olağandışı tüketim olan gecelere denk gelmiştir. Geri kalan
%90.7'sinde yakalama tamamen enjekte edilen akıştan kaynaklanır.

## 5. Anomali skoru dağılımı (`13_anomaly_score_distribution.png`)

Gerçek test saatlerinin skorları 0.37–0.60 aralığında yoğunlaşır (medyan ≈0.43). Senaryoların olay başına en
yüksek skorları belirgin biçimde ayrışır: S1 ≈0.70–0.77, S3 ≈0.66–0.74, S2 ≈0.64–0.73. S4 ise ≈0.59–0.70
aralığındadır ve Şüpheli eşiğinin hemen üstüne düşer. Bu yüzden S4'ün çoğu "Şüpheli" olarak işaretlenir. Bu
beklenen bir sonuçtur: tek ve kısa bir yüksek kullanım (ör. küvet doldurma) normal davranışa en çok benzeyen
senaryodur.

## 6. Yanlış negatifler (test)

Kaçırılan 27 olayın 20'si S4, 7'si S3'tür (`outputs/anomalies/synthetic_test_false_negatives.csv`). En
belirgin örnekler:

| Olay | Senaryo | Daire | Eklenen hacim | Max skor | Neden |
|---|---|---|---|---|---|
| TEST_S4_0189 | S4 | APT_017 | 92 L, 06:00 | 0.594 | Yüksek hacimli dairede sabah tepe saatine denk geldi |
| TEST_S4_0048 | S4 | APT_016 | 40 L, 12:00 | 0.595 | Taban hacim (en az 40 L) gündüz için olağan bir kullanım |
| TEST_S4_0271 | S4 | APT_025 | 40 L, 11:00 | 0.597 | Aynı |
| TEST_S3_0205 | S3 | APT_014 | 38 L, 23:00 | 0.600 | 23:00 dairenin akşam rutinine yakın; aktiflik olasılığı %11 |
| TEST_S4_0016 | S4 | APT_017 | 125 L, 16:00 | 0.602 | Eşiği yükseltilmiş daire (uyarlanmış eşik 0.639) |

Ortak nokta: kaçırılan olaylar **gündüz veya akşam saatlerinde** gerçekleşen, kısa süreli ve dairenin olağan
kullanım hacmine yakın olaylardır. Gece sürekli akış senaryosunda hiçbir olay kaçırılmamıştır.

## 7. Farklı eşiklerin etkisi (`15_threshold_tradeoff.png`)

Eşikler doğrulama skorlarının farklı yüzdeliklerinden alınmıştır (bu tabloda yalnızca global eşik kullanılır).
Sonuçlar test verisine aittir:

| Doğrulama q | Eşik | Test alarm | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|---|
| 0.90 | 0.5475 | %8.74 | %100 | %100 | %100 | %100 |
| 0.95 | 0.5852 | %4.35 | %100 | %100 | %100 | %100 |
| **0.97** | **0.6061** | **%2.70** | %100 | %100 | %99.3 | %96.0 |
| 0.99 | 0.6414 | %0.93 | %100 | %97.7 | %89.7 | %48.7 |
| **0.995** | **0.6575** | **%0.53** | %100 | %92.0 | %83.3 | %32.7 |
| 0.999 | 0.6939 | %0.12 | %100 | %26.0 | %78.0 | %18.0 |

S1 bütün eşiklerde %100 kalır, yani sürekli akış tespiti eşik seçimine duyarlı değildir. Eşik seçimi asıl olarak
S4 (kısa artış) ile alarm yükü arasındaki dengeyi belirler. q=0.97 seçimi, alarm oranını %10 hedefinin çok
altında tutarken S2–S4'te %93'ün üzerinde yakalama sağlar.

## 8. Daire bazlı model davranışı (`16_per_apartment_behavior.png`)

* **Yalnızca global eşik (ilk sürüm):** Test döneminde 3 dairede alarm oranı %10'u aşmıştır (APT_002 %13.1,
  APT_017 %12.3, APT_003 %11.4). Bu daireler 8 sensörlü ve günde 300–420 L tüketen yüksek hacimli dairelerdir.
  Aynı durum doğrulama döneminde de görülmüştür (%18.5 / %10.9 / %11.1) ve eşik politikası bu bulguya göre
  değiştirilmiştir.
* **Nihai (daireye uyarlanmış eşik):** Hiçbir daire %3.8'i aşmaz. Daireler arası standart sapma 3.54 → 0.87
  yüzde puana düşer. Bütün dairelerde S1 yakalama %100'dür.
* Ayrıntı: `outputs/reports/per_apartment_test_behavior.csv`.

## 9. Global ve daire bazlı model karşılaştırması

| Model | Küme | S1 | S2 | S3 | S4 | Gerçek alarm | Daireler arası std | En yüksek daire | >%10 daire |
|---|---|---|---|---|---|---|---|---|---|
| Global, global eşik | doğrulama | 100 | 100 | 98.7 | 95.0 | %3.00 | 4.05 pp | %18.5 | 3 |
| Global, global eşik | test | 100 | 100 | 99.3 | 96.0 | %2.70 | 3.54 pp | %13.1 | 3 |
| **Global, uyarlanmış eşik (nihai)** | doğrulama | 100 | 100 | 97.3 | 91.7 | %1.74 | 0.90 pp | %3.0 | 0 |
| **Global, uyarlanmış eşik (nihai)** | **test** | **100** | **100** | **97.7** | **93.3** | **%1.57** | **0.87 pp** | **%3.8** | **0** |
| 28 daire bazlı model | doğrulama | 100 | 100 | 98.7 | 98.3 | %3.03 | 0.00 pp² | %3.0 | 0 |
| 28 daire bazlı model | test | 100 | 100 | 100 | 99.7 | %3.05 | 2.11 pp | %10.9 | 1 |

² Daire bazlı eşikler aynı doğrulama verisinden hesaplandığı için doğrulamadaki sıfır sapma bir yapı gereğidir.

Daire bazlı modeller kısa artışları (S4) biraz daha iyi yakalamaktadır. Buna karşılık gerçek veride yaklaşık iki
kat alarm üretirler, testte bir dairede %10'u aşarlar, 28 ayrı dosyanın bakımını gerektirirler ve yeni daireler
için kullanılamazlar. Nihai yapılandırma ana hedefte (S1) aynı sonucu verir ve alarm yükü en düşük seçenektir.
Kısa artış senaryosunda küçük bir kayıp (S4 %96.0 → %93.3) bilinçli bir ödünleşimdir.

## 10. Hiperparametre duyarlılığı (yalnızca doğrulama)

| n_estimators | max_samples | S1 | S2 | S3 | S4 | Ortalama |
|---|---|---|---|---|---|---|
| 100 | 256 | 100 | 100 | 91.3 | 81.3 | 93.2 |
| 100 | 512 | 100 | 100 | 99.0 | 96.7 | 98.9 |
| 100 | 2048 | 100 | 100 | 99.3 | 98.3 | 99.4 |
| 300 | 256 | 100 | 100 | 88.3 | 65.3 | 88.4 |
| **300** | **512** | 100 | 100 | 98.7 | 95.0 | 98.4 |
| 300 | 2048 | 100 | 100 | 99.3 | 99.3 | 99.7 |

(Global eşikle hesaplanmıştır.) Varsayılan `max_samples=256` kısa artışlarda belirgin biçimde zayıftır.
512 ve üstü benzer sonuç verir. Sürüm 1.0.0 önceden belirlenen 512 değerini korur (bkz. `ai_methodology.md` §9).

## 11. Gerçek veride bulunan alarmlar

Test döneminde 1 810 saat ≥ Şüpheli olmuştur; bunların 387'si Anormal'dir (`outputs/anomalies/real_test_alarms.csv`,
gerekçe kodları ve mesajlarla birlikte). En yüksek skorlu örnekler gece saatlerinde 5–6 dilim boyunca süren
yüksek hacimli tüketimlerdir. Örneğin APT_003'te 2022-07-23 02:00'de 192 L, art arda 6 dilim boyunca kayıt
vardır. Bunlar sahada doğrulanmamış adaylardır ve gerçek kaçak oldukları iddia edilmez.

## 12. Model sınırlılıkları

Ayrıntılı liste: `docs/ai_methodology.md` §14. Özetle: etiket yoktur (alarm oranı kesin FPR değildir);
sentetik senaryolar varsayıma dayanır; 2 L/saatin altındaki sızıntılar zayıf yakalanır; süreklilik bir
göstergedir, gerçek akış süresi değildir; uyarlanabilir taban değerler ve uyarlanmış eşikler kalıcı kaçakları
zamanla normalleştirebilir; daire-gün düzeyinde Şüpheli oranı yüksektir, bu yüzden bildirimler Anormal
durumuna bağlanmalıdır; sonuçlar tek bir binaya aittir.
