"""Merkezi konfigürasyon — tüm hardcoded değerler burada."""

import os

# Proje kök dizini
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Veri dosyası yolları
PATHS = {
    "merged":         os.path.join(DATA_DIR, "merged_quakes.parquet"),
    "merged_legacy":  os.path.join(DATA_DIR, "merged_quakes.xlsx"),
    "faults":         os.path.join(DATA_DIR, "diri_faylar.geojson"),
    "faults_simple":  os.path.join(DATA_DIR, "diri_faylar_simplified.geojson"),
    "fault_risk":     os.path.join(DATA_DIR, "fay_risk_skorlari.csv"),
    "afad_csv":       os.path.join(DATA_DIR, "m5_depremler.csv"),
    "usgs_csv":       os.path.join(DATA_DIR, "usgs_1900_1990.csv"),
    "settlements":    os.path.join(DATA_DIR, "yerlesimler.parquet"),
    "shelters":       os.path.join(DATA_DIR, "toplanma_alanlari.geojson"),
}

# Harita varsayılanları
MAP = {
    "center_lat": 39.0,
    "center_lon": 35.0,
    "zoom":        6,
    "turkey_bbox": (25.0, 35.0, 45.0, 43.0),  # (lon_min, lat_min, lon_max, lat_max)
}

# AFAD API (resmî)
AFAD = {
    "base_url": "https://deprem.afad.gov.tr/apiv2/event",
    "min_mag":  4.0,
    "limit":    500,
    "max_pages": 200,          # sayfalama güvenlik sınırı
}

# Kandilli (gayriresmî orhanaydogdu API'si — canlı veri birincil kaynağı)
KANDILLI = {
    "base_url": "https://api.orhanaydogdu.com.tr/deprem",
    "timeout":  15,
}

# USGS API
USGS = {
    "base_url":  "https://earthquake.usgs.gov/fdsnws/event/1/query",
    "start":     "1900-01-01",
    "end":       "1989-12-31",
    "min_mag":   5.0,
    "limit":     20000,
}

# Veri temizleme / dedup — iki kayıt üç koşulu birden sağlıyorsa aynı deprem sayılır
DEDUP = {
    "time_tolerance_s": 20,     # zaman farkı (kurumlar arası orijin zamanı farkı birkaç sn)
    "dist_tolerance_km": 25,    # konum farkı (kurumlar arası episantr farkı)
    "mag_tolerance": 0.6,       # büyüklük farkı (ML/Mw ölçek farkları ~0.5'e kadar çıkabilir)
}

# Fay analizi
FAULT = {
    "buffer_km":   10.0,        # metrik tampon (km) — metrik CRS'te uygulanır
    "metric_crs":  "EPSG:32636",  # UTM 36N — Türkiye için metre bazlı projeksiyon
    "simplify_deg": 0.005,      # GeoJSON sadeleştirme toleransı (~500 m)
}

# Zaman dilimi
TZ = {
    "kandilli_local": "Europe/Istanbul",  # Kandilli API yerel saat döner → UTC'ye çevrilir
}

# Çoklu katalog karşılaştırması
COMPARE = {
    "time_tolerance_s":  45,    # kurumlar arası orijin zamanı farkı payı
    "dist_tolerance_km": 120,   # kurumlar arası episantr farkı payı (deniz olayları geniş)
    "timeout":           60,
    "cache_ttl_s":       1800,  # karşılaştırma sonucu önbelleği (30 dk)
}

# Etki analizi — Allen, Wald & Worden (2012) makrosismik şiddet denklemi (IPE)
# Hipomerkez uzaklığı (Rhyp) varyantı: katalogda fay geometrisi olmadığı için
# nokta-kaynak varsayımı kullanılır. Kaynak: J. Seismology 16:409-433,
# katsayılar OpenQuake hazardlib/gsim/allen_2012_ipe.py ile birebir.
IPE = {
    "c0": 2.085, "c1": 1.428, "c2": -1.402, "c4": 0.078,
    "m1": -0.209, "m2": 2.042,
    "s1": 0.82, "s2": 0.37, "s3": 22.9,   # sigma = s1 + s2/(1+(R/s3)^2)
    "anelastic_from_km": 50.0,
    "max_distance_km": 300.0,             # denklemin geçerli olduğu üst sınır
}

# Nüfus maruziyeti verisinin ölçülmüş belirsizliği (TÜİK il nüfuslarına karşı)
EXPOSURE = {
    "province_error_low": -0.31,
    "province_error_high": 0.32,
    "coverage_note": "Yalnızca il/ilçe merkezleri; kırsal yerleşimler dahil değil.",
}
