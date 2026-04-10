<div align="center">

# 🌍 TR Earthquake AI

### Türkiye Deprem Analiz & Görselleştirme Platformu

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Pandas](https://img.shields.io/badge/Pandas-2.0+-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org)
[![License](https://img.shields.io/badge/Lisans-MIT-22c55e?style=for-the-badge)](LICENSE)

*AFAD ve USGS verilerine dayanan, interaktif harita ve istatistiksel analizlerle Türkiye'deki sismik aktiviteyi görselleştiren açık kaynaklı bir platform.*

---

![Dashboard Preview](https://img.shields.io/badge/Demo-Streamlit%20App-FF4B4B?style=flat-square&logo=streamlit)

</div>

---

## 📌 İçindekiler

- [Özellikler](#-özellikler)
- [Ekran Görüntüleri](#-ekran-görüntüleri)
- [Kurulum](#️-kurulum)
- [Kullanım](#-kullanım)
- [Veri Kaynakları](#-veri-kaynakları)
- [Proje Yapısı](#-proje-yapısı)
- [Teknik Detaylar](#-teknik-detaylar)
- [Katkıda Bulunma](#-katkıda-bulunma)

---

## ✨ Özellikler

### 🗺️ Deprem Haritası
- **3 görünüm modu:** Kümeleme (hızlı), Isı Haritası ve Bireysel İşaretçi
- Büyüklüğe göre renk kodlu noktalar (mavi → sarı → turuncu → kırmızı)
- **Diri fay hatları** katmanı (açılıp kapatılabilir)
- Popup'larda konum, tarih, büyüklük ve derinlik bilgisi
- Karanlık harita teması (CartoDB DarkMatter)

### 📈 Zaman & İstatistik Analizi
- Yıllara göre deprem sayısı ve ortalama büyüklük
- Aylık frekans grafiği (alan doldurmalı)
- **Yıl × Ay aktivite ısı haritası** — hangi dönemlerin daha aktif olduğunu görün
- Büyüklük ve derinlik dağılım histogramları

### 📊 Veri Kümesi
- Konum bazlı metin arama
- Anlık istatistikler (kayıt sayısı, en büyük, ortalama derinlik)
- Tüm filtrelenmiş veriyi **CSV olarak indir**

### 🔍 Akıllı Filtreler
- Tarih aralığı (1900'den bugüne kadar, her zaman güncel)
- Büyüklük aralığı slider
- Derinlik aralığı slider

---

## 🖥️ Ekran Görüntüleri

| Harita — Kümeleme Modu | Analiz Sayfası |
|------------------------|----------------|
| Binlerce deprem noktası kümelenerek hızlı yüklenir | Yıllık bar + yıl×ay ısı haritası |

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
streamlit run app/dashboard.py
```

Tarayıcı otomatik açılır → `http://localhost:8501`

### Sidebar Filtreleri
1. Sol menüden sayfa seç (Harita / Analiz / Veri)
2. Tarih aralığı, büyüklük ve derinlik filtrelerini ayarla
3. Harita sayfasında görünüm modu ve fay katmanını seç

---

## 📊 Veri Kaynakları

| Kaynak | Kapsam | Format |
|--------|--------|--------|
| **AFAD** — Afet ve Acil Durum Yönetimi Başkanlığı | 1990'dan günümüze, Türkiye | REST API |
| **USGS** — ABD Jeoloji Araştırmaları Kurumu | 1900–1990, küresel (M≥5) | GeoJSON API |
| **Diri Fay Veritabanı** | Türkiye aktif fay hatları | GeoJSON |

> Veriler `src/fetch_afad.py` ve `src/fetch_usgs.py` modülleri ile yeniden çekilebilir.

---

## 📁 Proje Yapısı

```
TR-Earthquake-AI/
│
├── app/
│   └── dashboard.py          ← Ana Streamlit uygulaması
│
├── src/
│   ├── config.py             ← Merkezi konfigürasyon (yollar, sabitler)
│   ├── fetch_afad.py         ← AFAD API veri çekici (retry + logging)
│   ├── fetch_usgs.py         ← USGS veri çekici
│   ├── merge_datasets.py     ← AFAD + USGS birleştirici
│   ├── preprocess.py         ← Veri temizleme ve standardizasyon
│   ├── ml_model.py           ← K-Means kümeleme + Random Forest pipeline
│   ├── fay_risk_analiz.py    ← Fay hattı bazlı risk skorlama
│   └── visualization.py      ← Matplotlib yardımcıları
│
├── data/
│   ├── merged_quakes.xlsx    ← Birleştirilmiş deprem verisi
│   ├── diri_faylar.geojson   ← Türkiye aktif fay hatları (~12 MB)
│   └── fay_risk_skorlari.csv ← Hesaplanmış fay risk skorları
│
├── tests/
│   └── test_preprocess.py    ← Birim testler (pytest)
│
├── .streamlit/
│   └── config.toml           ← Dark tema & renk ayarları
│
├── requirements.txt
└── README.md
```

---

## 🔧 Teknik Detaylar

### Hız Optimizasyonları
- `@st.cache_data` — veri dosyaları ve grafikler önbelleklenir
- `@st.cache_resource` — 12 MB GeoJSON yalnızca bir kez yüklenir
- `FastMarkerCluster` — binlerce nokta tarayıcı tarafında kümelenir
- Büyük veri setlerinde otomatik örnekleme (scatter için max 5.000 nokta)

### Veri Pipeline
```
AFAD API ──┐
           ├──► merge_datasets.py ──► preprocess.py ──► merged_quakes.xlsx
USGS API ──┘                                                    │
                                                                ▼
diri_faylar.geojson ──────────────────────────────► dashboard.py (Streamlit)
```

### Risk Skorlama Formülü
```
Risk Skoru = (Deprem Sayısı × Ortalama Mw) / (Yıl Geçti + 1)
```
Normalize edilmiş skor: 0–100 arası görsel karşılaştırma için.

---

## 🧪 Testler

```bash
pip install pytest
pytest tests/ -v
```

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
Risk skorları istatistiksel hesaplamaya dayanır; resmi bir deprem tahmini değildir.

---

<div align="center">

**ErenAksu17** tarafından geliştirildi &nbsp;•&nbsp; Veriler: AFAD & USGS

</div>
