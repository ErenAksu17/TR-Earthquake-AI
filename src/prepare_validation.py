"""
Doğrulama veri setini hazırlar — USGS DYFI ("Did You Feel It?") gözlemleri.

DYFI, depremi hisseden insanların anketlerinden üretilen GÖZLENEN makrosismik
şiddettir. Bu veri, projedeki şiddet denkleminin (src/impact.py) tahminlerini
gerçekle kıyaslamak için kullanılır.

Veri yapısı: her olay için 10 km'lik kutulara toplanmış gözlemler
    cdi    → gözlenen şiddet (CDI ≈ MMI)
    dist   → episantr uzaklığı (km, yüzey)
    nresp  → o kutudaki anket sayısı

Güvenilirlik notu: tek yanıta dayanan kutular çok gürültülüdür (bir kişi 228 km
uzaktan MMI 9 bildirebiliyor). Bu yüzden varsayılan olarak nresp ≥ 3 filtresi
uygulanır; filtre parametreyle değiştirilebilir.

Kapsam sınırı: DYFI gönüllü katılıma dayanır — kırsal ve internet erişimi düşük
bölgeler eksik temsil edilir, bu yüzden gözlemler kentsel alanlara yanlıdır.
"""

import logging
import os
import time

import pandas as pd
import requests

from src.config import MAP, PATHS

log = logging.getLogger(__name__)

USGS_QUERY = "https://earthquake.usgs.gov/fdsnws/event/1/query"
UA = {"User-Agent": "TR-Earthquake-AI/1.0 (github.com/ErenAksu17/TR-Earthquake-AI)"}
PREFERRED_PRODUCTS = ("dyfi_geo_10km.geojson", "dyfi_geo_1km.geojson", "dyfi_zip.geojson")


def _events(min_mag: float, start: str, end: str) -> list[dict]:
    """Türkiye bbox'ında DYFI verisi olabilecek olayları listeler."""
    lon_min, lat_min, lon_max, lat_max = MAP["turkey_bbox"]
    resp = requests.get(USGS_QUERY, headers=UA, timeout=90, params={
        "format": "geojson", "starttime": start, "endtime": end,
        "minlatitude": lat_min, "maxlatitude": lat_max,
        "minlongitude": lon_min, "maxlongitude": lon_max,
        "minmagnitude": min_mag, "orderby": "magnitude",
    })
    resp.raise_for_status()
    return resp.json().get("features", [])


def _dyfi_url(event_id: str) -> str | None:
    """Olayın DYFI ürünlerinden en uygun geojson'un adresini bulur."""
    try:
        detail = requests.get(USGS_QUERY, headers=UA, timeout=60,
                              params={"format": "geojson", "eventid": event_id}).json()
    except requests.exceptions.RequestException as e:
        log.warning("%s detay alınamadı: %s", event_id, e)
        return None

    products = detail.get("properties", {}).get("products", {})
    if "dyfi" not in products:
        return None
    contents = products["dyfi"][0].get("contents", {})
    for name in PREFERRED_PRODUCTS:
        if name in contents:
            return contents[name]["url"]
    return None


def build_dyfi(output: str = None, min_mag: float = 5.0,
               start: str = "2000-01-01", end: str = "2026-12-31",
               pause_s: float = 0.3) -> pd.DataFrame:
    """Türkiye olayları için DYFI gözlemlerini indirip Parquet'e yazar."""
    output = output or PATHS["dyfi"]
    events = _events(min_mag, start, end)
    log.info("%d aday olay bulundu (M≥%.1f).", len(events), min_mag)

    rows = []
    for i, feat in enumerate(events, 1):
        props, coords = feat["properties"], feat["geometry"]["coordinates"]
        if props.get("cdi") is None:
            continue
        url = _dyfi_url(feat["id"])
        if not url:
            continue
        try:
            data = requests.get(url, headers=UA, timeout=90).json()
        except requests.exceptions.RequestException as e:
            log.warning("%s DYFI indirilemedi: %s", feat["id"], e)
            continue

        n_before = len(rows)
        for box in data.get("features", []):
            p = box.get("properties", {})
            if p.get("cdi") is None or p.get("dist") is None:
                continue
            rows.append({
                "event_id": feat["id"],
                "event_mag": float(props["mag"]),
                "event_depth_km": float(coords[2]) if coords[2] is not None else 10.0,
                "event_place": props.get("place", ""),
                "event_time": pd.to_datetime(props["time"], unit="ms"),
                "box_name": p.get("name", ""),
                "epicentral_km": float(p["dist"]),
                "observed_mmi": float(p["cdi"]),
                "n_responses": int(p.get("nresp", 0) or 0),
            })
        log.info("[%d/%d] M%.1f %s → %d kutu", i, len(events), props["mag"],
                 (props.get("place") or "")[:32], len(rows) - n_before)
        time.sleep(pause_s)

    df = pd.DataFrame(rows)
    if df.empty:
        log.warning("Hiç DYFI gözlemi toplanamadı.")
        return df

    os.makedirs(os.path.dirname(output), exist_ok=True)
    df.to_parquet(output, index=False)
    log.info("DYFI gözlemleri yazıldı: %s (%d gözlem, %d olay)",
             output, len(df), df["event_id"].nunique())
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    build_dyfi()
