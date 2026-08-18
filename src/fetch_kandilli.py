"""
Canlı deprem verisi.

Birincil kaynak: orhanaydogdu Kandilli+AFAD API'si (gayriresmî, rate limit 40/dk)
Yedek kaynak:   AFAD resmî apiv2 (birincil kaynak erişilemezse otomatik devreye girer)

Tüm zaman damgaları UTC (tz-naive) olarak döner — Kandilli API'sinin yerel
(Europe/Istanbul) saati burada UTC'ye çevrilir.
"""

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from src.config import AFAD, KANDILLI, TZ
from src.pipeline import deduplicate, to_utc_naive

log = logging.getLogger(__name__)

BASE = KANDILLI["base_url"]
TIMEOUT = KANDILLI["timeout"]


def _parse_records(records: list) -> pd.DataFrame:
    """orhanaydogdu API kayıtlarını standart DataFrame'e dönüştür."""
    rows = []
    for r in records:
        coords = r.get("geojson", {}).get("coordinates", [None, None])
        loc_props = r.get("location_properties", {})
        epic = loc_props.get("epiCenter", {}) or {}
        city = loc_props.get("closestCity", {}) or {}

        rows.append({
            "eventDate":  r.get("date_time"),
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
    if df.empty:
        return df
    # API yerel saat (Europe/Istanbul) döner → UTC'ye normalize et
    df["eventDate"] = to_utc_naive(df["eventDate"], source_tz=TZ["kandilli_local"])
    df = df.dropna(subset=["latitude", "longitude", "magnitude", "eventDate"])
    return df.sort_values("eventDate", ascending=False).reset_index(drop=True)


def _parse_afad_official(records: list) -> pd.DataFrame:
    """AFAD resmî apiv2 kayıtlarını standart DataFrame'e dönüştür (UTC döner)."""
    rows = []
    for r in records:
        rows.append({
            "eventDate":  r.get("date"),
            "latitude":   r.get("latitude"),
            "longitude":  r.get("longitude"),
            "depth":      r.get("depth"),
            "magnitude":  r.get("magnitude"),
            "location":   r.get("location", ""),
            "epicenter":  r.get("district", "") or "",
            "city":       r.get("province", "") or "",
            "provider":   "afad",
            "quake_id":   str(r.get("eventID", "")),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["eventDate"] = to_utc_naive(df["eventDate"])
    for col in ("latitude", "longitude", "depth", "magnitude"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude", "magnitude", "eventDate"])
    return df.sort_values("eventDate", ascending=False).reset_index(drop=True)


def _get_json(url: str, params: dict = None, timeout: int = TIMEOUT):
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get_live_afad_official(hours: int = 24) -> pd.DataFrame:
    """AFAD resmî apiv2'den son N saatin depremlerini çek (yedek kaynak)."""
    now = datetime.now(timezone.utc)
    params = {
        "start": (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S"),
        "end":   now.strftime("%Y-%m-%dT%H:%M:%S"),
        "orderby": "timedesc",
    }
    try:
        data = _get_json(f"{AFAD['base_url']}/filter", params=params, timeout=20)
    except requests.exceptions.RequestException as e:
        log.error("AFAD resmî API hatası: %s", e)
        return pd.DataFrame()

    records = data if isinstance(data, list) else data.get("result", [])
    return _parse_afad_official(records or [])


def get_live(source: str = "kandilli") -> pd.DataFrame:
    """
    Son 24 saatin depremlerini çek.
    source: 'kandilli' | 'afad' | 'all'

    'all' seçiminde Kandilli+AFAD kayıtları tekilleştirilir (aynı deprem iki
    kaynaktan gelirse bir kez sayılır). Birincil API erişilemezse AFAD resmî
    API'sine otomatik düşülür.
    """
    endpoints = {
        "kandilli": f"{BASE}/kandilli/live",
        "afad":     f"{BASE}/afad/live",
        "all":      BASE,
    }
    url = endpoints.get(source, endpoints["kandilli"])

    try:
        data = _get_json(url)
        records = data.get("result", [])
        df = _parse_records(records) if records else pd.DataFrame()
    except requests.exceptions.RequestException as e:
        log.warning("Birincil canlı API hatası (%s), AFAD resmî API'sine geçiliyor.", e)
        df = pd.DataFrame()

    if df.empty:
        df = get_live_afad_official()

    if not df.empty and source == "all":
        df = deduplicate(df).sort_values("eventDate", ascending=False).reset_index(drop=True)

    return df


def get_archive(source: str = "kandilli", start: str = None, end: str = None) -> pd.DataFrame:
    """Arşiv verisini çek. start / end: 'YYYY-MM-DD' formatında."""
    url = f"{BASE}/{source}/archive"
    params = {}
    if start:
        params["startdate"] = start
    if end:
        params["enddate"] = end

    try:
        data = _get_json(url, params=params, timeout=20)
    except requests.exceptions.RequestException as e:
        log.error("Arşiv çekme hatası: %s", e)
        return pd.DataFrame()

    return _parse_records(data.get("result", []))


def api_status() -> dict:
    """Kaynakların erişilebilirlik durumu."""
    status = {"kandilli": False, "afad_official": False}
    try:
        status["kandilli"] = requests.get(f"{BASE}/status", timeout=8).status_code == 200
    except requests.exceptions.RequestException:
        pass
    try:
        r = requests.get(f"{AFAD['base_url']}/filter",
                         params={"start": "2024-01-01T00:00:00", "end": "2024-01-01T01:00:00"},
                         timeout=8)
        status["afad_official"] = r.status_code == 200
    except requests.exceptions.RequestException:
        pass
    return status


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = get_live("all")
    print(f"{len(df)} canlı deprem çekildi (UTC).")
    if not df.empty:
        print(df[["eventDate", "magnitude", "depth", "location", "city", "provider"]].head(10))
