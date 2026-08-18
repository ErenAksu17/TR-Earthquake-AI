"""
Çoklu katalog karşılaştırması — aynı depremi farklı kurumlar nasıl raporluyor?

Kurumlar aynı depreme farklı büyüklük, konum ve derinlik atar; farklı büyüklük
ölçekleri (ML, MW, mb, mww) kullanırlar. Bu modül aynı olayı kataloglar arasında
eşleştirip bu farkları ölçülebilir hale getirir.

Kaynakların gerçek kabiliyetleri (2026-08 itibarıyla doğrulandı):
- AFAD resmî apiv2  : UTC döner, tarih aralığıyla sorgulanabilir, ölçek bilgisi
                      verir (ML / MW). Türkiye için birincil katalog.
- USGS FDSNWS       : UTC döner, tarih aralığıyla sorgulanabilir, magType verir
                      (mb / mww / ml). Türkiye'de fiilî kapsama eşiği ~M4.0 —
                      daha küçük depremler USGS kataloğunda YOKTUR.
- Kandilli (orhanaydogdu API'si): yalnızca son ~24-48 saat. "archive" ucu
                      startdate/enddate parametrelerini YOK SAYAR (30 günlük
                      istek son 2 günü döndürür), bu yüzden tarihsel
                      karşılaştırmada kullanılamaz.

Eşleştirme yalnızca ZAMAN ve KONUM yakınlığına bakar; büyüklük farkı ölçütü
bilinçli olarak KULLANILMAZ — ölçmek istediğimiz şeyin ta kendisi odur.
"""

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

from src.config import AFAD, COMPARE, KANDILLI, MAP, TZ, USGS
from src.pipeline import to_utc_naive

log = logging.getLogger(__name__)

SCHEMA = ["source", "event_id", "eventDate", "latitude", "longitude",
          "depth", "magnitude", "mag_type", "location"]

MATCH_COLS = ["time_a", "time_b", "dt_s", "dist_km", "mag_a", "mag_b", "dmag",
              "magtype_a", "magtype_b", "depth_a", "depth_b", "ddepth",
              "location_a", "location_b", "ambiguous"]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=SCHEMA)


def _finalize(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Ortak şemaya oturt, geçersiz satırları at, zamana göre sırala."""
    if df.empty:
        return _empty()
    df = df.copy()
    df["source"] = source
    for col in ("latitude", "longitude", "depth", "magnitude"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["depth"] = df["depth"].fillna(0.0)
    df = df.dropna(subset=["eventDate", "latitude", "longitude", "magnitude"])
    df["mag_type"] = df["mag_type"].fillna("").astype(str)
    return df[SCHEMA].sort_values("eventDate").reset_index(drop=True)


# ── Kaynak çekiciler ─────────────────────────────────────────────────────────

def fetch_afad(start: str, end: str, min_mag: float = 4.0) -> pd.DataFrame:
    """AFAD resmî apiv2'den bir zaman penceresi çeker (UTC)."""
    rows, offset = [], 0
    for _ in range(AFAD["max_pages"]):
        params = {
            "start": f"{start}T00:00:00" if len(start) == 10 else start,
            "end": f"{end}T23:59:59" if len(end) == 10 else end,
            "minmag": min_mag,
            "orderby": "time",
            "limit": AFAD["limit"],
            "offset": offset,
        }
        try:
            resp = requests.get(f"{AFAD['base_url']}/filter", params=params,
                                timeout=COMPARE["timeout"])
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            log.error("AFAD karşılaştırma çekimi hatası: %s", e)
            break

        page = data if isinstance(data, list) else data.get("result", [])
        if not page:
            break
        rows.extend(page)
        if len(page) < AFAD["limit"]:
            break
        offset += AFAD["limit"]

    if not rows:
        return _empty()

    df = pd.DataFrame([{
        "event_id": str(r.get("eventID", "")),
        "eventDate": r.get("date"),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "depth": r.get("depth"),
        "magnitude": r.get("magnitude"),
        "mag_type": r.get("type", ""),
        "location": r.get("location", ""),
    } for r in rows])
    df["eventDate"] = to_utc_naive(df["eventDate"])   # AFAD apiv2 UTC döner
    return _finalize(df, "AFAD")


def fetch_usgs(start: str, end: str, min_mag: float = 4.0) -> pd.DataFrame:
    """USGS FDSNWS'den Türkiye bbox'ı için bir zaman penceresi çeker (UTC)."""
    lon_min, lat_min, lon_max, lat_max = MAP["turkey_bbox"]
    params = {
        "format": "geojson",
        "starttime": start, "endtime": end,
        "minlatitude": lat_min, "maxlatitude": lat_max,
        "minlongitude": lon_min, "maxlongitude": lon_max,
        "minmagnitude": min_mag,
        "orderby": "time-asc",
        "limit": USGS["limit"],
    }
    try:
        resp = requests.get(USGS["base_url"], params=params, timeout=COMPARE["timeout"])
        resp.raise_for_status()
        feats = resp.json().get("features", [])
    except requests.exceptions.RequestException as e:
        log.error("USGS karşılaştırma çekimi hatası: %s", e)
        return _empty()

    if not feats:
        return _empty()

    df = pd.DataFrame([{
        "event_id": f.get("id", ""),
        "eventDate": pd.to_datetime(f["properties"]["time"], unit="ms"),
        "latitude": f["geometry"]["coordinates"][1],
        "longitude": f["geometry"]["coordinates"][0],
        "depth": f["geometry"]["coordinates"][2],
        "magnitude": f["properties"].get("mag"),
        "mag_type": f["properties"].get("magType", ""),
        "location": f["properties"].get("place", ""),
    } for f in feats])
    return _finalize(df, "USGS")


def fetch_kandilli_recent(min_mag: float = 0.0) -> pd.DataFrame:
    """Kandilli'nin son ~24 saatlik canlı verisi (tarihsel olarak sorgulanamaz)."""
    try:
        resp = requests.get(f"{KANDILLI['base_url']}/kandilli/live",
                            timeout=KANDILLI["timeout"])
        resp.raise_for_status()
        recs = resp.json().get("result", [])
    except requests.exceptions.RequestException as e:
        log.error("Kandilli karşılaştırma çekimi hatası: %s", e)
        return _empty()

    if not recs:
        return _empty()

    df = pd.DataFrame([{
        "event_id": r.get("earthquake_id", ""),
        "eventDate": r.get("date_time"),
        "latitude": (r.get("geojson", {}).get("coordinates") or [None, None])[1],
        "longitude": (r.get("geojson", {}).get("coordinates") or [None, None])[0],
        "depth": r.get("depth"),
        "magnitude": r.get("mag"),
        "mag_type": "",          # API ölçek bilgisi vermiyor
        "location": r.get("title", ""),
    } for r in recs])
    df["eventDate"] = to_utc_naive(df["eventDate"], source_tz=TZ["kandilli_local"])
    df = _finalize(df, "Kandilli")
    return df[df["magnitude"] >= min_mag].reset_index(drop=True) if min_mag else df


FETCHERS = {"AFAD": fetch_afad, "USGS": fetch_usgs}


# ── Eşleştirme ───────────────────────────────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def match_catalogs(a: pd.DataFrame, b: pd.DataFrame,
                   time_tol_s: float = None, dist_tol_km: float = None) -> pd.DataFrame:
    """İki kataloğu bire bir eşleştirir (zaman + konum yakınlığı).

    Büyüklük farkı ölçüt DEĞİLDİR — ölçmek istediğimiz şey odur. Aday çoksa
    zamanca en yakın olan seçilir ve 'ambiguous' sütunuyla işaretlenir; bu,
    yoğun artçı dizilerinde yanlış eşleşme riskini görünür kılar.
    """
    time_tol_s = time_tol_s if time_tol_s is not None else COMPARE["time_tolerance_s"]
    dist_tol_km = dist_tol_km if dist_tol_km is not None else COMPARE["dist_tolerance_km"]

    if a.empty or b.empty:
        return pd.DataFrame(columns=MATCH_COLS)

    a = a.sort_values("eventDate").reset_index(drop=True)
    b = b.sort_values("eventDate").reset_index(drop=True)

    ta = ((a["eventDate"] - pd.Timestamp(0)) // pd.Timedelta(seconds=1)).to_numpy()
    tb = ((b["eventDate"] - pd.Timestamp(0)) // pd.Timedelta(seconds=1)).to_numpy()
    lat_a, lon_a = a["latitude"].to_numpy(float), a["longitude"].to_numpy(float)
    lat_b, lon_b = b["latitude"].to_numpy(float), b["longitude"].to_numpy(float)

    # Aday çiftleri topla
    candidates = []
    for i in range(len(a)):
        lo = np.searchsorted(tb, ta[i] - time_tol_s, side="left")
        hi = np.searchsorted(tb, ta[i] + time_tol_s, side="right")
        if hi <= lo:
            continue
        idx = np.arange(lo, hi)
        d = _haversine_km(lat_a[i], lon_a[i], lat_b[idx], lon_b[idx])
        ok = d <= dist_tol_km
        n_ok = int(ok.sum())
        for j, dist in zip(idx[ok], d[ok]):
            candidates.append((abs(int(ta[i]) - int(tb[j])), float(dist), i, int(j), n_ok > 1))

    # Zamanca en yakından başlayarak bire bir ata
    candidates.sort(key=lambda c: (c[0], c[1]))
    used_a, used_b, pairs = set(), set(), []
    for dt, dist, i, j, ambiguous in candidates:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        ra, rb = a.iloc[i], b.iloc[j]
        pairs.append({
            "time_a": ra["eventDate"], "time_b": rb["eventDate"],
            "dt_s": float(dt), "dist_km": round(float(dist), 2),
            "mag_a": float(ra["magnitude"]), "mag_b": float(rb["magnitude"]),
            "dmag": round(float(ra["magnitude"]) - float(rb["magnitude"]), 2),
            "magtype_a": ra["mag_type"], "magtype_b": rb["mag_type"],
            "depth_a": float(ra["depth"]), "depth_b": float(rb["depth"]),
            "ddepth": round(float(ra["depth"]) - float(rb["depth"]), 1),
            "location_a": ra["location"], "location_b": rb["location"],
            "ambiguous": bool(ambiguous),
        })

    if not pairs:
        return pd.DataFrame(columns=MATCH_COLS)

    return pd.DataFrame(pairs).sort_values("time_a").reset_index(drop=True)


# ── Özet istatistikler ───────────────────────────────────────────────────────

def compare_pair(a: pd.DataFrame, b: pd.DataFrame, name_a: str, name_b: str,
                 time_tol_s: float = None, dist_tol_km: float = None) -> dict:
    """İki katalog arasındaki sistematik farkları özetler."""
    matched = match_catalogs(a, b, time_tol_s, dist_tol_km)
    out = {
        "source_a": name_a, "source_b": name_b,
        "n_a": int(len(a)), "n_b": int(len(b)),
        "matched": int(len(matched)),
        "only_a": int(len(a) - len(matched)),
        "only_b": int(len(b) - len(matched)),
        "ambiguous": int(matched["ambiguous"].sum()) if len(matched) else 0,
    }
    if matched.empty:
        out["stats"] = None
        out["scale_pairs"] = []
        return out

    dmag, dist, dt = matched["dmag"], matched["dist_km"], matched["dt_s"]
    out["stats"] = {
        "dmag_mean": round(float(dmag.mean()), 3),
        "dmag_median": round(float(dmag.median()), 3),
        "dmag_std": round(float(dmag.std(ddof=0)), 3),
        "dmag_max_abs": round(float(dmag.abs().max()), 2),
        "dist_mean": round(float(dist.mean()), 2),
        "dist_median": round(float(dist.median()), 2),
        "dist_max": round(float(dist.max()), 2),
        "dt_mean": round(float(dt.mean()), 2),
        "dt_median": round(float(dt.median()), 2),
        "ddepth_median": round(float(matched["ddepth"].median()), 1),
    }
    # Ölçek çiftlerine göre kırılım (ML↔mb gibi sistematik farklar burada görünür)
    labels = (matched["magtype_a"].str.upper().replace("", "?")
              + " / " + matched["magtype_b"].str.upper().replace("", "?"))
    scale = (matched.assign(pair=labels)
             .groupby("pair")
             .agg(n=("dmag", "size"), dmag_mean=("dmag", "mean"), dmag_median=("dmag", "median"))
             .round(3).sort_values("n", ascending=False))
    out["scale_pairs"] = [
        {"pair": idx, "n": int(r["n"]), "dmag_mean": float(r["dmag_mean"]),
         "dmag_median": float(r["dmag_median"])}
        for idx, r in scale.iterrows()
    ]
    return out


def compare_window(start: str, end: str, min_mag: float = 4.0,
                   fetchers: dict = None) -> dict:
    """AFAD ile USGS'i verilen pencerede karşılaştırır.

    fetchers parametresi test edilebilirlik içindir (ağ çağrılarını değiştirmek).
    """
    fetchers = fetchers or FETCHERS
    cats = {name: fn(start, end, min_mag) for name, fn in fetchers.items()}
    names = list(cats)

    result = {
        "window": {"start": start, "end": end, "min_mag": min_mag},
        "catalogs": [
            {"source": n, "count": int(len(cats[n])),
             "mag_types": sorted({x for x in cats[n]["mag_type"].unique() if x})}
            for n in names
        ],
        "comparisons": [],
        "notes": [],
    }

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            result["comparisons"].append(
                compare_pair(cats[names[i]], cats[names[j]], names[i], names[j]))

    if any(c["count"] == 0 for c in result["catalogs"]):
        result["notes"].append(
            "Bir katalogda hiç kayıt yok. USGS'in Türkiye'deki fiilî kapsama "
            "eşiği ~M4.0'dır; daha küçük depremler yalnızca AFAD/Kandilli'de bulunur.")
    return result


def sample_pairs(start: str, end: str, min_mag: float = 4.0,
                 limit: int = 50, fetchers: dict = None) -> list[dict]:
    """Karşılaştırma tablosu için eşleşmiş olay çiftleri (en büyükten)."""
    fetchers = fetchers or FETCHERS
    names = list(fetchers)
    if len(names) < 2:
        return []
    a = fetchers[names[0]](start, end, min_mag)
    b = fetchers[names[1]](start, end, min_mag)
    matched = match_catalogs(a, b)
    if matched.empty:
        return []
    order = matched[["mag_a", "mag_b"]].max(axis=1).sort_values(ascending=False).index
    out = matched.loc[order].head(limit).copy()
    out["time_a"] = out["time_a"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out["time_b"] = out["time_b"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out.to_dict(orient="records")


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    _end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _start = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    print(json.dumps(compare_window(_start, _end, 4.0), ensure_ascii=False, indent=2, default=str))
