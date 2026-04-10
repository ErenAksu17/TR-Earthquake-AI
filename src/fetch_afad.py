"""AFAD deprem verisi çekme modülü — hata yönetimi ve retry desteğiyle."""

import requests
import pandas as pd
from datetime import datetime
import os
import time
import logging

from src.config import AFAD, PATHS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BASE_URL = AFAD["base_url"]


def _get_with_retry(url: str, params: dict, max_retries: int = 3, backoff: float = 2.0) -> dict | list:
    """HTTP GET with exponential backoff retry."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            log.warning("Timeout (deneme %d/%d): %s", attempt, max_retries, url)
        except requests.exceptions.HTTPError as e:
            log.error("HTTP hatası: %s", e)
            raise
        except requests.exceptions.RequestException as e:
            log.warning("Bağlantı hatası (deneme %d/%d): %s", attempt, max_retries, e)
        if attempt < max_retries:
            time.sleep(backoff ** attempt)
    raise ConnectionError(f"AFAD API'ye {max_retries} denemede ulaşılamadı.")


def fetch_all_m5_plus(min_mag: float = None, start: str = "1990-01-01") -> pd.DataFrame:
    """AFAD'dan M≥min_mag tüm depremleri sayfalayarak çeker."""
    min_mag = min_mag or AFAD["min_mag"]
    all_data = []
    offset = 0
    limit = AFAD["limit"]
    end = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    while True:
        params = {
            "start":    start + "T00:00:00",
            "end":      end,
            "minmag":   min_mag,
            "orderby":  "timedesc",
            "limit":    limit,
            "offset":   offset,
        }
        try:
            json_data = _get_with_retry(f"{BASE_URL}/filter", params)
        except ConnectionError as e:
            log.error("Veri çekme durdu: %s", e)
            break

        data = json_data.get("result", []) if isinstance(json_data, dict) else (json_data if isinstance(json_data, list) else [])

        if not data:
            break

        all_data.extend(data)
        offset += limit
        log.info("✔️  %d kayıt çekildi...", offset)

    if not all_data:
        log.warning("Hiç veri alınamadı.")
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    # Sütun adlarını standartlaştır
    rename_map = {
        "date":      "eventDate",
        "lat":       "latitude",
        "lon":       "longitude",
        "dep":       "depth",
        "mag":       "magnitude",
        "location":  "location",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    return df


def save_m5_to_csv(filepath: str = None) -> None:
    filepath = filepath or PATHS["afad_csv"]
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df = fetch_all_m5_plus()
    if df.empty:
        log.error("Kaydedilecek veri yok.")
        return
    df.to_csv(filepath, index=False)
    log.info("✅ %d kayıt kaydedildi: %s", len(df), filepath)
    if "eventDate" in df.columns:
        log.info("⏳ En eski: %s  |  🔥 En büyük: %s", df["eventDate"].min(), df["magnitude"].max())


if __name__ == "__main__":
    save_m5_to_csv()
