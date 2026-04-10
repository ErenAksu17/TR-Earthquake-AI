# 🌍 TR Earthquake AI

> **Türkiye Sismik Risk Analiz & Yapay Zeka Platformu**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-FF4B4B?logo=streamlit)](https://streamlit.io)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 🌐 Dil / Language / Lingua

- [🇹🇷 Türkçe](#-türkçe)
- [🇬🇧 English](#-english)
- [🇮🇹 Italiano](#-italiano)

---

## 🇹🇷 Türkçe

**TR Earthquake AI**, Türkiye'deki depremleri görselleştiren, zaman içindeki sismik aktiviteyi analiz eden ve makine öğrenmesiyle risk değerlendirmesi yapan interaktif bir veri platformudur.

### 🚀 Özellikler

| Özellik | Açıklama |
|---------|----------|
| 🗺️ **Deprem Haritası** | Kümeleme, ısı haritası veya bireysel işaretçi modlarıyla interaktif harita |
| 🔥 **Isı Haritası** | Büyüklük ve derinlik bazlı yoğunluk haritaları |
| 📈 **Zaman Analizi** | Yıllık/aylık frekans, mevsimsel ısı haritası, kümülatif grafik |
| ⚠️ **Fay Risk Analizi** | Diri fay hatları bazında normalize edilmiş risk skorları |
| 🤖 **ML Tahmin Modeli** | K-Means sismik zon kümeleme + Random Forest büyüklük sınıflandırması |
| 📊 **Veri Kümesi** | Arama, filtreleme ve CSV indirme |

### 📊 Veri Kaynakları

- **AFAD** — Afet ve Acil Durum Yönetimi Başkanlığı (resmi Türkiye deprem verileri)
- **USGS** — ABD Jeoloji Araştırmaları Kurumu (1900–1990 tarihi veriler)
- **Diri Fay Veritabanı** — GeoJSON formatında Türkiye aktif fay hatları

### ⚙️ Kurulum

```bash
# 1. Repo'yu klonla
git clone https://github.com/ErenAksu17/TR-Earthquake-AI.git
cd TR-Earthquake-AI

# 2. Sanal ortam oluştur
python -m venv .venv
.\.venv\Scripts\activate      # Windows
# source .venv/bin/activate   # Linux/Mac

# 3. Bağımlılıkları yükle
pip install -r requirements.txt
```

### ▶️ Uygulamayı Başlat

```bash
streamlit run app/dashboard.py
```

### 🧪 Testleri Çalıştır

```bash
pip install pytest
pytest tests/ -v
```

### 📁 Proje Yapısı

```
TR-Earthquake-AI/
├── app/
│   └── dashboard.py          # Ana Streamlit uygulaması
├── src/
│   ├── config.py             # Merkezi konfigürasyon
│   ├── fetch_afad.py         # AFAD API veri çekici
│   ├── fetch_usgs.py         # USGS veri çekici
│   ├── merge_datasets.py     # Veri birleştirici
│   ├── preprocess.py         # Veri temizleme
│   ├── ml_model.py           # K-Means + Random Forest ML pipeline
│   ├── fay_risk_analiz.py    # Fay hattı risk skorlama
│   └── visualization.py      # Çizim yardımcıları
├── data/                     # Veri dosyaları (xlsx, geojson, csv)
├── tests/                    # Birim testler
├── .streamlit/
│   └── config.toml           # Dark tema konfigürasyonu
└── requirements.txt
```

### ⚠️ Not

Bu proje akademik veya bilimsel doğruluk iddiası taşımaz. Geliştirme, görselleştirme ve deney amaçlıdır. Risk skorları deneysel hesaplamaya dayanır.

---

## 🇬🇧 English

**TR Earthquake AI** is an interactive data platform for visualizing Turkish earthquakes, analyzing seismic activity over time, and performing AI-powered risk assessment.

### 🚀 Features

| Feature | Description |
|---------|-------------|
| 🗺️ **Earthquake Map** | Interactive map with cluster, heatmap, or individual marker modes |
| 🔥 **Heatmap** | Magnitude and depth-based density maps |
| 📈 **Time Analysis** | Yearly/monthly frequency, seasonal heatmap, cumulative chart |
| ⚠️ **Fault Risk Analysis** | Normalized risk scores per active fault line |
| 🤖 **ML Model** | K-Means seismic zone clustering + Random Forest magnitude classification |
| 📊 **Dataset** | Search, filter, and CSV download |

### 📊 Data Sources

- **AFAD** — Turkish Disaster and Emergency Authority (official earthquake data)
- **USGS** — United States Geological Survey (1900–1990 historical data)
- **Active Fault Database** — Turkey active fault lines in GeoJSON format

### ⚙️ Setup

```bash
git clone https://github.com/ErenAksu17/TR-Earthquake-AI.git
cd TR-Earthquake-AI
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### ▶️ Run

```bash
streamlit run app/dashboard.py
```

### ⚠️ Note

This project does not claim scientific or academic accuracy. It is for development, visualization, and experimentation purposes only.

---

## 🇮🇹 Italiano

**TR Earthquake AI** è una piattaforma dati interattiva per visualizzare i terremoti in Turchia, analizzare l'attività sismica nel tempo ed eseguire valutazioni del rischio tramite AI.

### 🚀 Caratteristiche

- 🗺️ Mappa interattiva con modalità cluster, heatmap e marker individuali
- 🔥 Mappe di densità per magnitudo e profondità
- 📈 Analisi temporale: frequenza annuale/mensile, stagionale, cumulativa
- ⚠️ Punteggi di rischio per faglia attiva
- 🤖 Clustering K-Means + classificazione Random Forest
- 📊 Dataset ricercabile con download CSV

### ⚙️ Installazione

```bash
git clone https://github.com/ErenAksu17/TR-Earthquake-AI.git
cd TR-Earthquake-AI
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/dashboard.py
```

### ⚠️ Nota

Questo progetto non pretende accuratezza scientifica. È sviluppato a scopo sperimentale e di visualizzazione.
