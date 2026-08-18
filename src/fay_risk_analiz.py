"""
Diri fay hattı bazlı sismik risk skoru hesaplama.
İmportlanabilir fonksiyonlar + CLI desteği.
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import os
import logging

from src.config import FAULT, PATHS

log = logging.getLogger(__name__)


def calculate_fault_risk(
    quakes_path: str = None,
    faults_path: str = None,
    output_path: str = None,
    buffer_deg: float = None,
) -> pd.DataFrame:
    """
    Her diri fay hattı için deprem yoğunluğu ve risk skoru hesaplar.

    Risk Skoru = (Deprem Sayısı × Ortalama Mw) / (Yıl Geçti + 1)

    Returns:
        DataFrame: catalog_name, Deprem Sayısı, Ortalama Mw, En Büyük Mw,
                   Son Deprem, Yıl Geçti, Risk Skoru
    """
    quakes_path = quakes_path or PATHS["merged"]
    faults_path = faults_path or PATHS["faults"]
    output_path = output_path or PATHS["fault_risk"]
    buffer_km   = buffer_deg  or FAULT["buffer_km"]   # geriye uyumlu parametre adı

    # Deprem verisi
    try:
        if quakes_path.endswith(".parquet"):
            df = pd.read_parquet(quakes_path)
        elif quakes_path.endswith(".xlsx"):
            df = pd.read_excel(quakes_path)
        else:
            df = pd.read_csv(quakes_path)
    except FileNotFoundError:
        log.error("Deprem verisi bulunamadı: %s", quakes_path)
        return pd.DataFrame()

    df = df.dropna(subset=["latitude", "longitude", "magnitude", "eventDate"])
    df["eventDate"] = pd.to_datetime(df["eventDate"], errors="coerce")
    df["geometry"]  = df.apply(lambda r: Point(r["longitude"], r["latitude"]), axis=1)
    quakes_gdf      = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    # Fay hatları
    try:
        faylar = gpd.read_file(faults_path).to_crs("EPSG:4326")
    except FileNotFoundError:
        log.error("Fay verisi bulunamadı: %s", faults_path)
        return pd.DataFrame()

    # Mesafe hesabı metrik CRS'te yapılır (derece bazlı buffer coğrafi olarak
    # yanlıştır: 0.1° doğu-batı ~8,6 km, kuzey-güney ~11,1 km eder).
    metric = FAULT["metric_crs"]
    quakes_m = quakes_gdf.to_crs(metric)
    faylar_m = faylar[["catalog_name", "geometry"]].to_crs(metric)

    # Her deprem yalnızca EN YAKIN faya atanır (çift sayım önlenir)
    matched = gpd.sjoin_nearest(
        quakes_m, faylar_m, how="inner", max_distance=buffer_km * 1000.0,
    )

    if matched.empty:
        log.warning("Hiçbir deprem fay hattı yakınında bulunamadı.")
        return pd.DataFrame()

    grouped = matched.groupby("catalog_name").agg(
        Deprem_Sayisi=("magnitude", "count"),
        Ortalama_Mw=("magnitude", "mean"),
        En_Buyuk_Mw=("magnitude", "max"),
        Son_Deprem=("eventDate", "max"),
    )

    grouped["Yil_Gecti"] = (
        pd.Timestamp.now().year - pd.to_datetime(grouped["Son_Deprem"]).dt.year
    ).clip(lower=0)

    grouped["Risk_Skoru"] = (
        (grouped["Deprem_Sayisi"] * grouped["Ortalama_Mw"]) / (grouped["Yil_Gecti"] + 1)
    ).round(2)

    # Normalize (0–100 arası görsel skor)
    max_risk = grouped["Risk_Skoru"].max()
    grouped["Risk_Normalize"] = ((grouped["Risk_Skoru"] / max_risk) * 100).round(1) if max_risk > 0 else 0

    result = grouped.reset_index().rename(columns={
        "catalog_name":  "Fay Adı",
        "Deprem_Sayisi": "Deprem Sayısı",
        "Ortalama_Mw":   "Ortalama Mw",
        "En_Buyuk_Mw":   "En Büyük Mw",
        "Son_Deprem":    "Son Deprem",
        "Yil_Gecti":     "Yıl Geçti",
        "Risk_Skoru":    "Risk Skoru",
        "Risk_Normalize":"Risk (0-100)",
    }).sort_values("Risk Skoru", ascending=False)

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True) if os.path.dirname(output_path) else None
        result.to_csv(output_path, index=False)
        log.info("✅ Risk skoru kaydedildi: %s", output_path)

    return result


def load_fault_risk(path: str = None) -> pd.DataFrame | None:
    path = path or PATHS["fault_risk"]
    if os.path.exists(path):
        return pd.read_csv(path)
    return None


def risk_color(score_normalized: float) -> str:
    """Normalize skora (0–100) göre renk döndür."""
    if score_normalized >= 75: return "#FF0000"
    elif score_normalized >= 50: return "#FF6600"
    elif score_normalized >= 25: return "#FFAA00"
    else: return "#4CAF50"


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    result = calculate_fault_risk()
    if not result.empty:
        print("✅ Risk skoru hesaplandı:")
        print(result[["Fay Adı", "Deprem Sayısı", "Risk Skoru", "Risk (0-100)"]].to_string())
