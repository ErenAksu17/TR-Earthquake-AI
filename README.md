<div align="center">

# 🌍 TR Earthquake AI

### Türkiye Deprem Analiz & Görselleştirme Platformu

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Leaflet](https://img.shields.io/badge/Leaflet-1.9-199900?style=for-the-badge&logo=leaflet&logoColor=white)](https://leafletjs.com)
[![License](https://img.shields.io/badge/Lisans-MIT-22c55e?style=for-the-badge)](LICENSE)

*Kandilli Rasathanesi, AFAD ve USGS verilerini birleştiren; gerçek zamanlı deprem takibi, interaktif harita ve istatistiksel analizler sunan açık kaynaklı bir platform.*

</div>

---

## 📌 İçindekiler

- [Özellikler](#-özellikler)
- [Kurulum](#️-kurulum)
- [Kullanım](#-kullanım)
- [API Uçları](#-api-uçları)
- [Veri Kaynakları](#-veri-kaynakları)
- [Proje Yapısı](#-proje-yapısı)
- [Teknik Detaylar](#-teknik-detaylar)
- [Katkıda Bulunma](#-katkıda-bulunma)

---

## ✨ Özellikler

### 🔴 Canlı Veriler
- **Kandilli Rasathanesi & AFAD** son 24 saat verisi — 60 saniyede bir otomatik yenilenir
- Birincil API erişilemezse **AFAD resmî API'sine otomatik geçiş** (fallback)
- Kaynak seçimi (Kandilli / AFAD / Tümü) — "Tümü" modunda çift kayıtlar otomatik tekilleştirilir
- Harita + son depremler listesi yan yana; listeden tıklayınca harita odaklanır

### 🗺️ Arşiv & Analiz
- 1900'den bugüne **6.600+ tekilleştirilmiş kayıt** (M ≥ 4)
- İşaretçi ve ısı haritası görünümleri, **diri fay hatları** katmanı
- Tarih / büyüklük / derinlik / konum filtreleri
- Yıllık deprem sayısı + en büyük deprem grafiği, büyüklük ve derinlik dağılımları
- Filtrelenmiş veriyi **CSV olarak indir**

### 🔬 Sismoloji *(Yeni)*
- **Gutenberg-Richter analizi:** Mc (tamlık eşiği) tahmini + Aki-Utsu maksimum
  olabilirlik b-değeri (Shi & Bolt belirsizliğiyle), log ölçekli frekans grafiği
- **Bölgesel b-değeri haritası** — ızgara bazlı; düşük b, büyük deprem payının
  yüksek olduğu bölgeleri gösterir
- **Gardner-Knopoff katalog ayıklama** — artçı şokları ayırıp bağımsız
  (ana şok) katalogla analiz yapma seçeneği
- **Artçı şok tahmini:** Omori-Utsu bozunum yasası MLE + Reasenberg-Jones tipi
  olasılık — "önümüzdeki 7/30 günde M≥4/5/6 artçı olasılığı"

> Bunların hepsi **olasılıksal** yöntemlerdir. Deterministik kısa vadeli deprem
> tahmini (şu tarihte, şurada, şu büyüklükte) bilimsel olarak mümkün değildir ve
> bu proje böyle bir iddiada bulunmaz.

### ⚖️ Kaynak Karşılaştırma *(Yeni)*
- Aynı depremi **AFAD ve USGS nasıl farklı raporluyor?** — büyüklük, episantr,
  derinlik ve orijin zamanı farkları ölçülür
- **Büyüklük ölçeği kırılımı:** AFAD `ML`/`MW`, USGS `mb`/`mwr`/`mww` kullanır;
  hangi ölçek çiftinde ne kadar sistematik fark olduğu tabloya dökülür
- **Kapsama farkı:** yalnızca bir katalogda bulunan olaylar sayılır — USGS'in
  Türkiye eşiği ~M4.0 olduğu için küçük depremler onda hiç yoktur
- Eşleştirme yalnızca zaman + konum yakınlığına bakar; büyüklük farkı ölçüt
  **değildir** (ölçmek istenen şeyin ta kendisidir). Tolerans penceresinde birden
  fazla aday varsa satır "belirsiz" olarak işaretlenir

> Örnek (Şubat 2023): AFAD 179, USGS 171 olay listeler; 121'i eşleşir, **58 olay
> yalnızca AFAD'da, 50 olay yalnızca USGS'tedir**. Medyan episantr farkı 7,7 km,
> en büyüğü 91 km. Pazarcık ana şoku AFAD'da M7.7 (MW), USGS'te M7.8 (mww).

### 🧭 Veri Kalitesi
- **16.150+ kayıt** (M ≥ 4, 1900–2025), EventID bazlı tekilleştirme
- Ham veri iki sistematik bozulma içerir, ikisi de pipeline'da düzeltilir:
  tarihler `DD/MM/YYYY` metin biçimindedir (varsayılan ayrıştırma 6 Şubat'ı
  2 Haziran yapar) ve aynı deprem farklı dosyalarda UTC/TSİ olarak çiftlenir
- Tüm zaman damgaları veri katmanında **UTC** tutulur, arayüzde TR saatine çevrilir
- Katalog **Parquet** formatında (XLSX'e göre ~10x hızlı yükleme)

---

## ⚙️ Kurulum

### Gereksinimler
- Python 3.10 veya üzeri
- Git

### Adım Adım

```bash
# 1. Repoyu klonla
git clone https://github.com/ErenAksu17/TR-Earthquake-AI.git
cd TR-Earthquake-AI

# 2. Sanal ortam oluştur
python -m venv .venv

# 3. Sanal ortamı aktifleştir
# Windows:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# 4. Bağımlılıkları yükle
pip install -r requirements.txt
```

---

## ▶️ Kullanım

```bash
uvicorn app.main:app --port 8021
```

Tarayıcıda aç → `http://localhost:8021`

---

## 🔌 API Uçları

| Uç | Açıklama |
|----|----------|
| `GET /api/live?source=all&min_mag=0` | Son 24 saatin depremleri (60 sn sunucu önbelleği) |
| `GET /api/quakes?start=&end=&min_mag=&format=json\|csv` | Filtreli arşiv kataloğu |
| `GET /api/stats?...` | Filtreli istatistikler (yıllık seri, histogramlar) |
| `GET /api/faults` | Sadeleştirilmiş diri fay GeoJSON'u (~0,2 MB) |
| `GET /api/status` | Kaynak API erişilebilirlik durumu |
| `GET /api/analysis/gr?declustered=` | Gutenberg-Richter: Mc, b-değeri, kümülatif eğri |
| `GET /api/analysis/bmap?cell_deg=` | Izgara bazlı b-değeri haritası |
| `GET /api/analysis/decluster` | Gardner-Knopoff ayıklama özeti |
| `GET /api/analysis/mainshocks` | Tahmin için aday ana şoklar |
| `GET /api/analysis/aftershock?time=&lat=&lon=&mag=` | Omori-Utsu artçı şok tahmini |
| `GET /api/compare?start=&end=&min_mag=` | AFAD ↔ USGS katalog karşılaştırması (30 dk önbellek) |

Tüm zamanlar **UTC (ISO 8601, `Z` sonekli)** döner; yerel saate çeviri istemcinin işidir.

---

## 📊 Veri Kaynakları

| Kaynak | Kapsam | Güncelleme |
|--------|--------|------------|
| **Kandilli Rasathanesi** — Boğaziçi Üniversitesi | Gerçek zamanlı, Türkiye | Her dakika |
| **AFAD** — Afet ve Acil Durum Yönetimi Başkanlığı | Gerçek zamanlı + arşiv | Her dakika |
| **USGS** — ABD Jeoloji Araştırmaları Kurumu | 1900–1990 arşiv + canlı karşılaştırma (Türkiye eşiği ~M4.0) | FDSNWS |
| **Diri Fay Veritabanı** | Türkiye aktif fay hatları | Statik |

> Canlı veri birincil olarak [orhanayd/kandilli-rasathanesi-api](https://github.com/orhanayd/kandilli-rasathanesi-api)
> üzerinden çekilir; erişilemezse AFAD resmî `apiv2` API'sine otomatik düşülür.

---

## 📁 Proje Yapısı

```
TR-Earthquake-AI/
│
├── app/
│   ├── main.py               ← FastAPI backend (API + statik sunum)
│   └── static/
│       ├── index.html        ← Leaflet tabanlı arayüz
│       ├── app.js
│       └── style.css
│
├── src/
│   ├── config.py             ← Merkezi konfigürasyon (yollar, sabitler, toleranslar)
│   ├── pipeline.py           ← Temizleme + UTC normalizasyonu + tekilleştirme + Parquet
│   ├── fetch_kandilli.py     ← Canlı veri (Kandilli/AFAD + resmî AFAD fallback)
│   ├── fetch_afad.py         ← AFAD arşiv veri çekici (retry + logging)
│   ├── fetch_usgs.py         ← USGS arşiv veri çekici
│   ├── merge_datasets.py     ← AFAD + USGS birleştirici (pipeline üzerinden)
│   ├── combine_excels.py     ← Ham Excel dışa aktarımlarını birleştirir
│   ├── preprocess.py         ← Sütun standardizasyonu
│   ├── seismology.py         ← b-değeri, Mc, Gardner-Knopoff, Omori-Utsu
│   ├── catalog_compare.py    ← AFAD ↔ USGS katalog eşleştirme ve fark analizi (YENİ)
│   └── fay_risk_analiz.py    ← Fay bazlı aktivite skoru (metrik CRS, en-yakın-fay ataması)
│
├── data/
│   ├── merged_quakes.parquet ← Tekilleştirilmiş birleşik katalog
│   ├── diri_faylar_simplified.geojson ← Web için sadeleştirilmiş faylar (~0,2 MB)
│   └── diri_faylar.geojson   ← Orijinal fay veritabanı (~12 MB)
│
├── tests/                    ← pytest (pipeline + API + sismoloji + karşılaştırma, 75 test)
├── .github/workflows/ci.yml  ← GitHub Actions (her push'ta testler)
├── requirements.txt
└── README.md
```

---

## 🔧 Teknik Detaylar

### Veri Pipeline
```
AFAD API ──┐
           ├─► pipeline.py ─► temizle ─► UTC'ye çevir ─► tekilleştir ─► merged_quakes.parquet
USGS API ──┘                                                                  │
                                                                              ▼
diri_faylar_simplified.geojson ─────────────────────────────► FastAPI ─► Leaflet arayüzü
```

### Tekilleştirme Kuralı
İki kayıt şu üç koşulu birden sağlıyorsa aynı deprem sayılır ve öncelikli kaynak
(afad > kandilli > usgs) tutulur:
- Zaman farkı ≤ 20 sn (kurumlar arası orijin zamanı farkı)
- Mesafe ≤ 25 km (kurumlar arası episantr farkı)
- Büyüklük farkı ≤ 0.6 (farklı büyüklük ölçekleri ML/Mw)

Büyüklük koşulu olmadan 2023 Kahramanmaraş gibi yoğun artçı dizilerindeki
gerçek ayrı depremler yanlışlıkla tek kayda iner.

### Hız Optimizasyonları
- Parquet katalog (XLSX'e göre ~10x hızlı), süreç başına tek yükleme
- Fay GeoJSON'u 12 MB → 0,22 MB sadeleştirildi, tarayıcıya tek sefer + 24 saat cache ile gider
- Canlı veri 60 sn sunucu önbelleği (kaynak API rate limitine saygı)
- Leaflet canvas renderer — binlerce nokta akıcı çizilir

---

## 🧪 Testler

```bash
pytest tests/ -v
```

Her push'ta GitHub Actions üzerinde otomatik çalışır.

---

## 🤝 Katkıda Bulunma

1. Fork'la
2. Yeni branch oluştur (`git checkout -b feature/yeni-ozellik`)
3. Değişikliklerini commit et
4. Push et ve Pull Request aç

---

## ⚠️ Sorumluluk Reddi

Bu proje **akademik veya bilimsel doğruluk iddiası taşımaz.**
Tamamen geliştirme, görselleştirme ve deney amaçlıdır.
Gösterilen skorlar istatistiksel hesaplamaya dayanır; **resmî bir deprem tahmini değildir**
ve deterministik kısa vadeli deprem tahmini bilimsel olarak mümkün değildir.

---

<div align="center">

**ErenAksu17** tarafından geliştirildi &nbsp;•&nbsp; Veriler: Kandilli Rasathanesi · AFAD · USGS

</div>
