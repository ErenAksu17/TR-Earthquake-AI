"""
Kandilli Rasathanesi + AFAD Gerçek Zamanlı API
Kaynak: https://github.com/orhanayd/kandilli-rasathanesi-api
Base URL: https://api.orhanaydogdu.com.tr/deprem
Rate limit: 40 istek/dakika
"""

import requests
import pandas as pd
import logging

log = logging.getLogger(__name__)

BASE = "https://api.orhanaydogdu.com.tr/deprem"


def _parse_records(records: list) -> pd.DataFrame:
    """Ham API kayıtlarını standart DataFrame'e dönüştür."""
    rows = []
    for r in records:
        coords = r.get("geojson", {}).get("coordinates", [None, None])
        loc_props = r.get("location_properties", {})
        epic = loc_props.get("epiCenter", {}) or {}
        city = loc_props.get("closestCity", {}) or {}

        rows.append({
            "eventDate":  pd.to_datetime(r.get("date_time"), errors="coerce"),
            "latitude":   coords[1] if len(coords) > 1 else None,
            "longitude":  coords[0] if len(coords) > 0 else None,
            "depth":      r.get("depth"),
            "magnitude":  r.get("mag"),
            "location":   r.get("title", ""),
            "epicenter":  epic.get("name", ""),
            "city":       city.get("name", ""),
            "provider":   r.get("provider", ""),
            "quake_id":   r.get("earthquake_id", ""),
        })

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["latitude", "longitude", "magnitude", "eventDate"])
    return df.sort_values("eventDate", ascending=False).reset_index(drop=True)


def get_live(source: str = "kandilli") -> pd.DataFrame:
    """
    Son 24 saatin depremlerini çek.
    source: 'kandilli' | 'afad' | 'all'
    """
    endpoints = {
        "kandilli": f"{BASE}/kandilli/live",
        "afad":     f"{BASE}/afad/live",
        "all":      f"{BASE}",
    }
    url = endpoints.get(source, endpoints["kandilli"])

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        log.error("Kandilli API zaman aşımı.")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        log.error("Kandilli API hatası: %s", e)
        return pd.DataFrame()

    records = data.get("result", [])
    if not records:
        return pd.DataFrame()

    return _parse_records(records)


def get_archive(source: str = "kandilli", start: str = None, end: str = None) -> pd.DataFrame:
    """
    Arşiv verisini çek.
    start / end: 'YYYY-MM-DD' formatında
    """
    url = f"{BASE}/{source}/archive"
    params = {}
    if start: params["startdate"] = start
    if end:   params["enddate"]   = end

    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        log.error("Arşiv çekme hatası: %s", e)
        return pd.DataFrame()

    return _parse_records(data.get("result", []))


def api_status() -> bool:
    """API'nin çalışıp çalışmadığını kontrol et."""
    try:
        resp = requests.get(f"{BASE}/status", timeout=8)
        return resp.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    df = get_live("kandilli")
    print(f"✅ {len(df)} canlı deprem çekildi.")
    print(df[["eventDate", "magnitude", "depth", "location", "city"]].head(10))
