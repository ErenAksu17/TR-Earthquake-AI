"""Merkezi konfigürasyon — tüm hardcoded değerler burada."""

import os

# Proje kök dizini
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Veri dosyası yolları
PATHS = {
    "merged":      os.path.join(DATA_DIR, "merged_quakes.xlsx"),
    "faults":      os.path.join(DATA_DIR, "diri_faylar.geojson"),
    "fault_risk":  os.path.join(DATA_DIR, "fay_risk_skorlari.csv"),
    "risk_model":  os.path.join(DATA_DIR, "risk_model.pkl"),
    "cluster_model": os.path.join(DATA_DIR, "cluster_model.pkl"),
    "afad_csv":    os.path.join(DATA_DIR, "m5_depremler.csv"),
    "usgs_csv":    os.path.join(DATA_DIR, "usgs_1900_1990.csv"),
}

# Harita varsayılanları
MAP = {
    "center_lat": 39.0,
    "center_lon": 35.0,
    "zoom":        6,
    "turkey_bbox": (25.0, 35.0, 45.0, 43.0),  # (lon_min, lat_min, lon_max, lat_max)
}

# Filtre varsayılanları
DEFAULTS = {
    "mag_min":   4.0,
    "mag_max":   7.5,
    "depth_max": 100,
    "lat_range": (35.0, 43.0),
    "lon_range": (25.0, 45.0),
}

# AFAD API
AFAD = {
    "base_url": "https://deprem.afad.gov.tr/apiv2/event",
    "min_mag":  5.0,
    "limit":    500,
}

# USGS API
USGS = {
    "base_url":  "https://earthquake.usgs.gov/fdsnws/event/1/query",
    "start":     "1900-01-01",
    "end":       "1989-12-31",
    "min_mag":   5.0,
    "limit":     20000,
}

# Fay analizi
FAULT = {
    "buffer_deg": 0.1,   # ~10 km
}

# ML
ML = {
    "n_clusters":    5,
    "rf_estimators": 200,
    "test_size":     0.2,
    "random_state":  42,
    "max_map_points": 3000,
}
