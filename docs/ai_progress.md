# WaterWise – AI Modülü İlerleme Kaydı

Oturum kesilirse kaldığı yerden devam edebilmek için tutulur.

| # | Adım | Durum |
|---|------|-------|
| 1 | Mevcut dosyaların incelenmesi (README, DATA_DICTIONARY, öneri formu, notebook) | ✅ |
| 2 | Veri setinin doğrulanması (birim, zaman dilimi, tekrarlar, boşluk semantiği) | ✅ |
| 3 | Veri temizleme modülü (`src/data_preprocessing.py`) | ✅ |
| 4 | EDA (`src/eda.py`, `outputs/figures/`) | ✅ |
| 5 | Normal tüketim profili (`src/normal_profile.py`) | ✅ |
| 6 | Özellik mühendisliği (`src/feature_engineering.py`) | ✅ |
| 7 | Isolation Forest eğitimi (`src/train_model.py`) | ✅ |
| 8 | Model değerlendirme (`src/evaluate_model.py`) | ✅ |
| 9 | Sentetik anomali testleri (`src/synthetic_anomalies.py`) | ✅ |
| 10 | Tahmin fonksiyonu (`src/predict.py`) | ✅ |
| 11 | Model kaydetme / yükleme testi | ✅ |
| 12 | Otomatik testler (`tests/`) | ✅ |
| 13 | Backend entegrasyon dokümanı | ✅ |
| 14 | Teknik raporlar | ✅ |

## Doğrulanmış veri bulguları (adım 2)

- `value` birimi **m³** (README toplamı 3271 m³ = Σvalue 3270.789; 1 L sayaç çözünürlüğü = 0.001 adımı; `aggregated_value` kümülatif sayaç endeksi ve ardışık farkı %99.9 oranında `value`).
- `timestamp` **yerel saat (Europe/Stockholm)**: ilkbahar DST günlerinde 02:xx kaydı yok, sonbahar DST'de sayaç endeksi 02:xx'te geri gidiyor.
- Sensörler yalnızca tüketim olduğunda kayıt üretiyor; ≤30 günlük sensör boşluklarının %99.9'unda sayaç ilerlememiş → boşluk = 0 tüketim. Uzun sistem kesintilerinde ~541 m³ kaydedilmemiş tüketim var → bu aralıklar "gözlenmedi".
- 140 tam tekrar satır (sayaç ilerlemedi) → atılır.

## Model kararları (adım 7-9)

- Analiz birimi: daire-saat; 13 nedensel özellik (src/feature_engineering.py).
- Global Isolation Forest (n_estimators=300, max_samples=512, random_state=42).
- Eşikler doğrulama döneminden: Şüpheli q=0.97, Anormal q=0.995 + daireye uyarlanmış (yalnızca yukarı) eşik.
  Gerekçe: doğrulamada 3 yüksek hacimli daire >%10 alarm alıyordu.
- Değerlendirme: `python -m src.evaluate_model` → outputs/reports/evaluation_tables.md

## Tamamlanma (2026-10-10)

- Tüm hat: `venv\Scripts\python.exe -m src.run_pipeline` (~150 sn, deterministik)
- Testler: `venv\Scripts\python.exe -m pytest tests -q` → 46 geçti, 0 başarısız
- Belgeler: docs/ai_methodology.md, docs/model_evaluation.md, docs/backend_integration.md, outputs/reports/eda_report.md
