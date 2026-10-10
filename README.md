# WaterWise 💧

### Yapay Zekâ Destekli Evsel Su Tüketimi Analizi ve Anomali Tespit Sistemi

WaterWise, evsel su tüketiminin analiz edilmesini, olağandışı tüketim davranışlarının tespit edilmesini ve kullanıcıların su tasarrufu konusunda bilinçlendirilmesini amaçlayan web tabanlı bir sosyal sorumluluk projesidir.

Sistem, geçmiş tüketim verilerinden normal kullanım alışkanlıklarını öğrenerek gece saatlerinde sürekli su akışı, beklenmedik yüksek tüketim ve alışılmışın dışındaki kullanım örüntülerini belirlemeyi hedeflemektedir.

## Projenin Amaçları

- Evsel su tüketimini günlük, haftalık ve aylık olarak analiz etmek.
- Kullanıcıların tüketim alışkanlıklarını görselleştirmek.
- Makine öğrenmesi ile olağandışı tüketim davranışlarını tespit etmek.
- Olası su israfı ve sürekli akış durumlarında kullanıcıları bilgilendirmek.
- Su tasarrufu farkındalığını artırmak.

## Kullanılan Teknolojiler

| Katman | Teknolojiler |
|---|---|
| Veri Analizi | Python, Pandas, NumPy |
| Yapay Zekâ | Scikit-learn, Isolation Forest |
| Backend | FastAPI, PostgreSQL |
| Frontend | React |
| Test | Pytest |
| Versiyon Kontrol | Git, GitHub |

## Yapay Zekâ Modülü

WaterWise'ın yapay zekâ modülü, HSB Living Lab Water Consumption Data (Anonymized) veri seti üzerinde geliştirilmiştir.

Veri seti 28 daireye ait su tüketim kayıtlarını içermektedir. Veri temizleme ve özellik mühendisliği işlemlerinin ardından normal tüketim profilleri oluşturulmuş ve Isolation Forest algoritmasıyla anomali tespit modeli eğitilmiştir.

Model; tüketim miktarı, saat bilgisi, geçmiş tüketim ortalamaları, gece kullanımı ve tüketim sürekliliği gibi özelliklerden yararlanır.

### Anomali Durumları

| Durum | Açıklama |
|---|---|
| Normal | Tüketim olağan kullanım örüntüsüne uygun |
| Şüpheli | Normal tüketimden belirli düzeyde sapma var |
| Anormal | Belirgin derecede olağandışı tüketim tespit edildi |

Anomali skorları kesin kaçak olasılığı değildir. Sistem, olası kaçak veya su israfı durumları için kullanıcıya uyarı sunar.

### Model Değerlendirmesi

Kontrollü sentetik anomali senaryolarında elde edilen tespit oranları:

| Senaryo | Tespit oranı |
|---|---|
| Gece sürekli akış | %100 |
| Olağandışı yüksek tüketim | %100 |
| Alışılmadık saatte tüketim | %97,7 |
| Kısa süreli tüketim artışı | %93,3 |

Bu sonuçlar sentetik test senaryolarına aittir; gerçek tesisat kaçaklarında aynı başarıyı garanti etmez.

Yapay zekâ modülünün 46 otomatik testi başarıyla tamamlanmıştır.

## Proje Yapısı

```text
WaterWise/
├── src/                    # Veri analizi ve AI modülü
├── models/                 # Eğitilmiş model ve tüketim profilleri
├── notebooks/              # Veri analizi ve deneyler
├── tests/                  # Otomatik testler
├── examples/               # Backend kullanım örneği
├── docs/                   # Teknik dokümantasyon
├── requirements-ai.txt     # AI bağımlılıkları
└── README.md
```

Backend ve frontend klasörleri ilgili geliştirme aşamalarında eklenecektir.

## Kurulum

Python 3.13 önerilir.

Depoyu bilgisayarınıza indirin:

```bash
git clone https://github.com/beyzaincehasan/WaterWise.git
cd WaterWise
```

Sanal ortam oluşturun:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Bağımlılıkları yükleyin:

```powershell
pip install -r requirements-ai.txt
```

Testleri çalıştırın:

```powershell
python -m pytest tests -v
```

Örnek tahmin uygulamasını çalıştırın:

```powershell
python examples/backend_usage_example.py
```

**Veri notu:** Ham ve işlenmiş tüketim verileri GitHub deposunda bulunmamaktadır. Örnek tahmin uygulamasını gerçek veriyle çalıştırmak için gerekli veri dosyaları ayrıca temin edilmelidir.

## Backend Entegrasyonu

Eğitilmiş modelin FastAPI backend'e bağlanması için `docs/backend_integration.md` belgesi hazırlanmıştır.

Temel kullanım:

```python
from src.predict import load_detector, predict_anomaly

detector = load_detector()

result = predict_anomaly(
    apartment_id="APT_011",
    records=records,
    target_timestamp=target_timestamp,
    history_start=history_start,
    detector=detector,
)

print(result["status"])
print(result["anomaly_score"])
print(result["message"])
```

Tahmin fonksiyonu, ideal olarak önceki 28 güne ait ham tüketim kayıtlarıyla kullanılmalıdır.

## Web Uygulaması

Planlanan temel sayfalar:

1. Dashboard
2. Tüketim Analizi
3. Kullanım Dağılımı
4. Anomali ve Uyarılar
5. Tasarruf Raporu

## Ekip ve Görev Dağılımı

| Sorumlu | Görev |
|---|---|
| Beyza | Veri analizi, özellik mühendisliği, makine öğrenmesi ve anomali tespiti |
| Gaye | FastAPI backend, PostgreSQL veritabanı ve AI entegrasyonu |
| Alperen | React frontend, dashboard ve veri görselleştirme |



---

**WaterWise — Her damla değerlidir. 💧**