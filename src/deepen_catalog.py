"""
Kataloğu modern dönem için derinleştirir (AFAD resmî apiv2'den M≥3 çekimi).

NEDEN: Katalog M≥4 eşiğindeyken artçı dizilerinin çoğu istatistiksel analiz için
yeterli olay içermiyordu — Faz 5 doğrulamasında 40 ana şoktan yalnızca 5'i test
edilebildi. Eşiği modern dönem için düşürmek hem artçı tahminini, hem b-değeri
kestirimini, hem de doğrulama örneklemini büyütür.

ZAMANLA DEĞİŞEN TAMLIK — bu katalogda bilinçli bir asimetri vardır:
    1900–2004 : M ≥ 4.0   (tarihsel dışa aktarımlar)
    2005–bugün: M ≥ 3.0   (AFAD apiv2, yoğun ağ dönemi)
Bu, karşılaştırmalı analizlerde tuzaktır: tüm kataloğu tek parça sayıp yıllık
deprem sayısına bakmak "2005'ten sonra deprem arttı" yanılsaması üretir. Gerçekte
artan şey ALGILAMA kabiliyetidir. Bu yüzden:
  - `catalog_completeness()` dönem sınırlarını açıkça döndürür,
  - b-değeri analizi zaten veriden Mc kestirdiği için pencere bazında doğrudur,
  - arayüzde dönem uyarısı gösterilir.

AFAD apiv2 notu: `orderby=time` sayfalar arasında gerçek bir sıralama vermez
(sayfa 0 ile sayfa 1 tarih aralıkları örtüşür), ancak `offset` sayfalaması
çakışmasız çalışır — doğrulandı. Sıralama yerel olarak yapılır.
"""

import logging
import os
import time

import pandas as pd
import requests

from src.config import AFAD, DEEPEN, PATHS
from src.pipeline import clean, deduplicate, load_merged

log = logging.getLogger(__name__)

UA = {"User-Agent": "TR-Earthquake-AI/1.0 (github.com/ErenAksu17/TR-Earthquake-AI)"}

RENAME = {
    "date": "eventDate", "latitude": "latitude", "longitude": "longitude",
    "depth": "depth", "magnitude": "magnitude", "location": "location",
    "eventID": "event_id", "type": "mag_type",
}


def fetch_year(year: int, min_mag: float, limit: int = None,
               pause_s: float = 0.15, max_pages: int = 400) -> pd.DataFrame:
    """Bir yılın tüm kayıtlarını sayfalayarak çeker."""
    limit = limit or AFAD["limit"]
    rows, offset, pages = [], 0, 0

    while pages < max_pages:
        params = {
            "start": f"{year}-01-01T00:00:00",
            "end": f"{year}-12-31T23:59:59",
            "minmag": min_mag,
            "orderby": "time",
            "limit": limit,
            "offset": offset,
        }
        try:
            resp = requests.get(f"{AFAD['base_url']}/filter", params=params,
                                headers=UA, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            log.warning("%d yılı, offset %d çekilemedi: %s", year, offset, e)
            break

        page = data if isinstance(data, list) else data.get("result", [])
        if not page:
            break
        rows.extend(page)
        pages += 1
        if len(page) < limit:
            break
        offset += limit
        time.sleep(pause_s)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).rename(columns={k: v for k, v in RENAME.items() if k in rows[0]})
    keep = [c for c in ("eventDate", "latitude", "longitude", "depth",
                        "magnitude", "location", "event_id", "mag_type") if c in df.columns]
    df = df[keep]
    df["eventDate"] = pd.to_datetime(df["eventDate"], errors="coerce")  # apiv2 UTC döner
    if "event_id" in df.columns:
        df["event_id"] = pd.to_numeric(df["event_id"], errors="coerce")
    return clean(df)


def deepen(start_year: int = None, end_year: int = None, min_mag: float = None,
           output: str = None, pause_s: float = 0.15) -> pd.DataFrame:
    """Modern dönemi düşük eşikle çekip mevcut katalogla birleştirir."""
    start_year = start_year or DEEPEN["start_year"]
    end_year = end_year or DEEPEN["end_year"]
    min_mag = min_mag if min_mag is not None else DEEPEN["min_mag"]
    output = output or PATHS["merged"]

    base = load_merged()
    log.info("Mevcut katalog: %d kayıt", len(base))

    frames = []
    for year in range(start_year, end_year + 1):
        df = fetch_year(year, min_mag, pause_s=pause_s)
        log.info("  %d → %d kayıt (M≥%.1f)", year, len(df), min_mag)
        if not df.empty:
            frames.append(df)

    if not frames:
        log.warning("Hiç yeni kayıt çekilemedi; katalog değişmedi.")
        return base

    fresh = pd.concat(frames, ignore_index=True)
    merged = pd.concat([base, fresh], ignore_index=True)

    # EventID birincil anahtar — aynı olay iki kaynaktan gelirse bir kez kalır
    if "event_id" in merged.columns:
        before = len(merged)
        with_id = merged[merged["event_id"].notna()].drop_duplicates(subset=["event_id"], keep="first")
        without_id = merged[merged["event_id"].isna()]
        merged = pd.concat([with_id, without_id], ignore_index=True)
        log.info("EventID tekilleştirme: %d → %d", before, len(merged))

    merged = merged.sort_values("eventDate").reset_index(drop=True)
    merged = deduplicate(merged)   # EventID'siz tarihsel kayıtlar için tolerans temizliği

    os.makedirs(os.path.dirname(output), exist_ok=True)
    merged.to_parquet(output, index=False)
    log.info("Katalog derinleştirildi: %s (%d kayıt)", output, len(merged))
    return merged


def catalog_completeness(df: pd.DataFrame = None) -> dict:
    """Kataloğun zamanla değişen tamlık eşiğini açıkça raporlar."""
    df = load_merged() if df is None else df
    cutoff = pd.Timestamp(f"{DEEPEN['start_year']}-01-01")
    historic = df[df["eventDate"] < cutoff]
    modern = df[df["eventDate"] >= cutoff]
    return {
        "eras": [
            {
                "label": "Tarihsel",
                "start": int(df["eventDate"].dt.year.min()) if len(df) else None,
                "end": DEEPEN["start_year"] - 1,
                "nominal_min_mag": 4.0,
                "records": int(len(historic)),
            },
            {
                "label": "Modern (yoğun ağ)",
                "start": DEEPEN["start_year"],
                "end": int(df["eventDate"].dt.year.max()) if len(df) else None,
                "nominal_min_mag": DEEPEN["min_mag"],
                "records": int(len(modern)),
            },
        ],
        "total": int(len(df)),
        "warning": (
            "Katalog eşiği zamanla değişir: "
            f"{DEEPEN['start_year']} öncesi M≥4.0, sonrası M≥{DEEPEN['min_mag']:.1f}. "
            "Dönemler arası ham deprem SAYISI karşılaştırılamaz — artan şey algılama "
            "kabiliyetidir, sismik etkinlik değil. Büyüklük-frekans analizleri her "
            "pencerede tamlık eşiğini (Mc) veriden kestirdiği için bundan etkilenmez."
        ),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    deepen()
