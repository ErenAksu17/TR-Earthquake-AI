"""
Veri boru hattı — normalizasyon, tekilleştirme (dedup) ve birleştirme.

Kurallar:
- Tüm zaman damgaları veri katmanında UTC (tz-naive) tutulur;
  yerel saate çeviri yalnızca sunum katmanında yapılır.
- İki kayıt, zaman farkı DEDUP["time_tolerance_s"] saniyeden ve mesafesi
  DEDUP["dist_tolerance_km"] km'den küçükse aynı deprem sayılır.
- Birleşik katalog Parquet olarak yazılır (XLSX'e göre ~10x hızlı).
"""

import logging
import os

import numpy as np
import pandas as pd

from src.config import DEDUP, PATHS, TZ

log = logging.getLogger(__name__)

REQUIRED_COLS = ["eventDate", "latitude", "longitude", "depth", "magnitude", "location"]

# Aynı depremi birden çok kaynak raporladığında tercih sırası
PROVIDER_PRIORITY = {"afad": 0, "kandilli": 1, "usgs": 2}


def to_utc_naive(series: pd.Series, source_tz: str | None = None) -> pd.Series:
    """Zaman damgalarını tz-naive UTC'ye normalize et.

    source_tz verilirse tz-naive girdiler o dilimde kabul edilip UTC'ye çevrilir
    (Kandilli API'si Europe/Istanbul yerel saati döner). Verilmezse girdi zaten
    UTC kabul edilir (AFAD resmî API ve USGS UTC döner).
    """
    s = pd.to_datetime(series, errors="coerce")
    if isinstance(s.dtype, pd.DatetimeTZDtype):
        return s.dt.tz_convert("UTC").dt.tz_localize(None)
    if source_tz:
        return (
            s.dt.tz_localize(source_tz, ambiguous="NaT", nonexistent="NaT")
            .dt.tz_convert("UTC")
            .dt.tz_localize(None)
        )
    return s


def _haversine_km(lat1, lon1, lat2, lon2):
    """İki nokta dizisi arasındaki büyük daire mesafesi (km)."""
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def deduplicate(df: pd.DataFrame,
                time_tol_s: int = None,
                dist_tol_km: float = None,
                mag_tol: float = None) -> pd.DataFrame:
    """Zaman + konum + büyüklük toleransıyla mükerrer kayıtları at.

    Üç koşul birden sağlanmalı; büyüklük koşulu olmadan yoğun artçı şok
    dizilerindeki (ör. 2023 Kahramanmaraş) gerçek ayrı depremler yanlışlıkla
    tek kayda iner. Çakışan kayıtlardan kaynak önceliği yüksek olan
    (afad > kandilli > usgs), eşitlikte ilki tutulur.
    """
    time_tol_s = time_tol_s or DEDUP["time_tolerance_s"]
    dist_tol_km = dist_tol_km or DEDUP["dist_tolerance_km"]
    mag_tol = mag_tol or DEDUP["mag_tolerance"]

    if df.empty:
        return df

    df = df.sort_values("eventDate", kind="stable").reset_index(drop=True)
    # Birim-güvenli epoch saniyesi: datetime64 çözünürlüğü (ns/us/s) ne olursa olsun doğru
    times = ((df["eventDate"] - pd.Timestamp(0)) // pd.Timedelta(seconds=1)).to_numpy()
    lats = df["latitude"].to_numpy(dtype=float)
    lons = df["longitude"].to_numpy(dtype=float)
    mags = df["magnitude"].to_numpy(dtype=float)
    if "provider" in df.columns:
        prio = df["provider"].map(lambda p: PROVIDER_PRIORITY.get(str(p).lower(), 9)).to_numpy()
    else:
        prio = np.full(len(df), 9)

    keep = np.ones(len(df), dtype=bool)
    for i in range(len(df)):
        if not keep[i]:
            continue
        j = i + 1
        while j < len(df) and times[j] - times[i] <= time_tol_s:
            if (keep[j]
                    and abs(mags[i] - mags[j]) <= mag_tol
                    and _haversine_km(lats[i], lons[i], lats[j], lons[j]) <= dist_tol_km):
                # Öncelikli kaynağı tut
                if prio[j] < prio[i]:
                    keep[i] = False
                    break
                keep[j] = False
            j += 1

    dropped = int((~keep).sum())
    if dropped:
        log.info("Dedup: %d mükerrer kayıt atıldı (%d kaldı).", dropped, int(keep.sum()))
    return df[keep].reset_index(drop=True)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Tip dönüşümü + geçersiz satırların atılması."""
    df = df.copy()
    df["eventDate"] = pd.to_datetime(df["eventDate"], errors="coerce")
    for col in ("latitude", "longitude", "depth", "magnitude"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["eventDate", "latitude", "longitude", "magnitude"])
    df = df[df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)]
    df = df[df["magnitude"].between(0, 10)]
    if "depth" in df.columns:
        df["depth"] = df["depth"].fillna(0).clip(lower=0)
    return df


def build_merged(frames: list[pd.DataFrame], output: str = None) -> pd.DataFrame:
    """Kaynak DataFrame'lerini temizle, birleştir, tekilleştir ve Parquet'e yaz."""
    output = output or PATHS["merged"]
    merged = pd.concat([clean(f) for f in frames], ignore_index=True)
    merged = deduplicate(merged)
    merged = merged.sort_values("eventDate").reset_index(drop=True)

    cols = [c for c in REQUIRED_COLS + ["provider"] if c in merged.columns]
    merged = merged[cols]

    os.makedirs(os.path.dirname(output), exist_ok=True)
    merged.to_parquet(output, index=False)
    log.info("Birleşik katalog yazıldı: %s (%d kayıt)", output, len(merged))
    return merged


def load_merged(path: str = None) -> pd.DataFrame:
    """Birleşik kataloğu Parquet'ten oku (yoksa eski XLSX'ten dönüştür)."""
    path = path or PATHS["merged"]
    if os.path.exists(path):
        return pd.read_parquet(path)

    legacy = PATHS["merged_legacy"]
    if os.path.exists(legacy):
        log.warning("Parquet yok, eski XLSX'ten dönüştürülüyor: %s", legacy)
        df = clean(pd.read_excel(legacy))
        return build_merged([df], output=path)

    raise FileNotFoundError(f"Katalog bulunamadı: {path}")


def migrate_legacy(kandilli_tz_fix: bool = False) -> pd.DataFrame:
    """Tek seferlik geçiş: merged_quakes.xlsx → tekilleştirilmiş Parquet.

    Eski birleşik veri AFAD resmî API + USGS kaynaklıdır; ikisi de UTC döner,
    bu yüzden varsayılan olarak saat dilimi dönüşümü uygulanmaz. (Kandilli'den
    gelmiş yerel saatli tarihsel satırlar varsa kandilli_tz_fix=True kullanın.)
    """
    df = pd.read_excel(PATHS["merged_legacy"])
    if kandilli_tz_fix:
        df["eventDate"] = to_utc_naive(df["eventDate"], source_tz=TZ["kandilli_local"])
    return build_merged([df])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = migrate_legacy()
    print(f"Gecis tamam: {len(result)} kayit -> {PATHS['merged']}")
