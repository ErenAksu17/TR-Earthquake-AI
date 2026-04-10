"""USGS tarihi deprem verisi çekme modülü — hata yönetimiyle."""

import requests
import pandas as pd
import os
import logging

from src.config import USGS, PATHS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def fetch_usgs(
    start: str = None,
    end: str = None,
    min_mag: float = None,
    output: str = None,
) -> pd.DataFrame:
    """USGS FDSNWS'den deprem verisi çeker ve DataFrame döndürür."""
    start   = start   or USGS["start"]
    end     = end     or USGS["end"]
    min_mag = min_mag or USGS["min_mag"]
    output  = output  or PATHS["usgs_csv"]

    params = {
        "format":       "geojson",
        "starttime":    start,
        "endtime":      end,
        "minmagnitude": min_mag,
        "limit":        USGS["limit"],
        "orderby":      "time-asc",
    }

    log.info("🔄 USGS verisi çekiliyor (%s – %s, M≥%.1f)...", start, end, min_mag)
    try:
        resp = requests.get(USGS["base_url"], params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        log.error("USGS API zaman aşımı.")
        return pd.DataFrame()
    except requests.exceptions.HTTPError as e:
        log.error("USGS HTTP hatası: %s", e)
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        log.error("USGS bağlantı hatası: %s", e)
        return pd.DataFrame()

    features = data.get("features", [])
    if not features:
        log.warning("USGS'den hiç veri alınamadı.")
        return pd.DataFrame()

    records = []
    for feature in features:
        props  = feature["properties"]
        coords = feature["geometry"]["coordinates"]
        records.append({
            "eventDate": pd.to_datetime(props["time"], unit="ms"),
            "latitude":  coords[1],
            "longitude": coords[0],
            "depth":     coords[2],
            "magnitude": props["mag"],
            "location":  props.get("place", ""),
        })

    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    df.to_csv(output, index=False)
    log.info("✅ USGS verisi kaydedildi: %s (%d kayıt)", output, len(df))
    return df


if __name__ == "__main__":
    fetch_usgs()
