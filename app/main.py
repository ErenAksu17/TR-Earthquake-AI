"""
TR Earthquake AI — FastAPI backend.

Uçlar:
  GET /api/live?source=all          Son 24 saat (canlı, 60 sn sunucu önbelleği)
  GET /api/quakes?...               Filtreli arşiv kataloğu (JSON veya CSV)
  GET /api/stats?...                Filtreli arşiv istatistikleri (grafikler için)
  GET /api/compare?...              Çoklu katalog karşılaştırması (AFAD vs USGS)
  GET /api/impact?...               Sarsıntı şiddeti ve yerleşim maruziyeti (IPE)
  GET /api/shelters?...             Toplanma alanları (OSM, eksik topluluk verisi)
  GET /api/validation/intensity     Şiddet modeli vs DYFI gözlemleri
  GET /api/validation/aftershock    Artçı tahmininin sözde-ileriye dönük N-testi
  GET /api/catalog/completeness     Kataloğun zamanla değişen tamlık eşiği
  GET /api/faults/sources           Fay kaynak modeli (Mmax, yinelenme, olasılık)
  GET /api/faults/geometry          Fay kaynaklarının GeoJSON geometrisi
  GET /api/scenario?fault_id=       Fay kırılma senaryosu (sonlu fay + zemin)
  GET /api/vs30                     Vs30 ızgarasının özeti ve sınırları
  GET /api/faults                   Sadeleştirilmiş diri fay GeoJSON'u
  GET /api/status                   Kaynak API erişilebilirlik durumu
  GET /                             Leaflet tabanlı arayüz (app/static)

Zaman kuralı: API tüm zamanları UTC (ISO 8601, 'Z' soneki) döner;
yerel saate çeviri istemcide yapılır.
"""

import io
import json
import os
import sys
import threading
import time

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.catalog_compare import compare_window, sample_pairs  # noqa: E402
from src.config import COMPARE, PATHS  # noqa: E402
from src.deepen_catalog import catalog_completeness  # noqa: E402
from src.fault_sources import load_fault_sources, sources_table  # noqa: E402
from src.scenario import run_scenario  # noqa: E402
from src.site_effects import vs30_summary  # noqa: E402
from src.fetch_kandilli import api_status, get_live  # noqa: E402
from src.impact import assess, nearby_shelters  # noqa: E402
from src.validation import validate_aftershock_forecasts, validate_intensity  # noqa: E402
from src.pipeline import load_merged  # noqa: E402
from src.seismology import (  # noqa: E402
    aftershock_forecast,
    b_value,
    b_value_grid,
    estimate_mc,
    gardner_knopoff,
    gr_curve,
)

app = FastAPI(title="TR Earthquake AI", version="2.0")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# ── Arşiv kataloğu (süreç başına bir kez yüklenir) ───────────────────────────
_catalog: pd.DataFrame | None = None
_catalog_lock = threading.Lock()


def catalog() -> pd.DataFrame:
    global _catalog
    with _catalog_lock:
        if _catalog is None:
            _catalog = load_merged()
        return _catalog


# ── Canlı veri önbelleği (rate limit: 40 istek/dk) ───────────────────────────
_LIVE_TTL = 60
_live_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_live_lock = threading.Lock()


def live_cached(source: str) -> pd.DataFrame:
    now = time.monotonic()
    with _live_lock:
        hit = _live_cache.get(source)
        if hit and now - hit[0] < _LIVE_TTL:
            return hit[1]
    df = get_live(source)
    with _live_lock:
        # Kaynak API düştüyse eski (bayat) veriyi tutmaya devam et
        if df.empty and hit:
            return hit[1]
        _live_cache[source] = (now, df)
    return df


def _records(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    out["eventDate"] = out["eventDate"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out.where(pd.notnull(out), None).to_dict(orient="records")


def _filter_catalog(
    start: str | None, end: str | None,
    min_mag: float, max_mag: float,
    min_depth: float, max_depth: float,
    q: str | None,
) -> pd.DataFrame:
    df = catalog()
    if start:
        df = df[df["eventDate"] >= pd.Timestamp(start)]
    if end:
        df = df[df["eventDate"] <= pd.Timestamp(end) + pd.Timedelta(days=1)]
    df = df[df["magnitude"].between(min_mag, max_mag)]
    df = df[df["depth"].between(min_depth, max_depth)]
    if q:
        df = df[df["location"].fillna("").str.contains(q, case=False, regex=False)]
    return df


# ── API uçları ────────────────────────────────────────────────────────────────

@app.get("/api/live")
def api_live(source: str = Query("all", pattern="^(kandilli|afad|all)$"),
             min_mag: float = 0.0):
    df = live_cached(source)
    if df.empty:
        raise HTTPException(status_code=503, detail="Canlı veri kaynaklarına erişilemiyor.")
    if min_mag > 0:
        df = df[df["magnitude"] >= min_mag]
    return {"count": len(df), "source": source, "quakes": _records(df)}


@app.get("/api/quakes")
def api_quakes(
    start: str | None = None,
    end: str | None = None,
    min_mag: float = 0.0,
    max_mag: float = 10.0,
    min_depth: float = 0.0,
    max_depth: float = 1000.0,
    q: str | None = None,
    limit: int = Query(5000, le=20000),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    df = _filter_catalog(start, end, min_mag, max_mag, min_depth, max_depth, q)
    df = df.sort_values("eventDate", ascending=False)
    total = len(df)

    if format == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return StreamingResponse(
            iter([buf.getvalue().encode("utf-8-sig")]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=depremler.csv"},
        )

    return {"total": total, "returned": min(total, limit), "quakes": _records(df.head(limit))}


@app.get("/api/stats")
def api_stats(
    start: str | None = None,
    end: str | None = None,
    min_mag: float = 0.0,
    max_mag: float = 10.0,
    min_depth: float = 0.0,
    max_depth: float = 1000.0,
    q: str | None = None,
):
    df = _filter_catalog(start, end, min_mag, max_mag, min_depth, max_depth, q)
    if df.empty:
        return {"total": 0}

    yearly = (
        df.groupby(df["eventDate"].dt.year)
        .agg(count=("magnitude", "size"), avg_mag=("magnitude", "mean"), max_mag=("magnitude", "max"))
        .round(2)
    )
    mag_hist = pd.cut(df["magnitude"], bins=[4, 4.5, 5, 5.5, 6, 6.5, 7, 8]).value_counts().sort_index()
    depth_hist = pd.cut(df["depth"], bins=[0, 10, 20, 40, 70, 100, 700]).value_counts().sort_index()

    return {
        "total": len(df),
        "max_mag": float(df["magnitude"].max()),
        "avg_mag": round(float(df["magnitude"].mean()), 2),
        "avg_depth": round(float(df["depth"].mean()), 1),
        "date_min": df["eventDate"].min().strftime("%Y-%m-%d"),
        "date_max": df["eventDate"].max().strftime("%Y-%m-%d"),
        "yearly": {
            "years": yearly.index.tolist(),
            "counts": yearly["count"].tolist(),
            "avg_mags": yearly["avg_mag"].tolist(),
            "max_mags": yearly["max_mag"].tolist(),
        },
        "mag_hist": {
            "labels": [f"{iv.left}–{iv.right}" for iv in mag_hist.index],
            "counts": mag_hist.tolist(),
        },
        "depth_hist": {
            "labels": [f"{int(iv.left)}–{int(iv.right)} km" for iv in depth_hist.index],
            "counts": depth_hist.tolist(),
        },
    }


# ── Sismoloji analizleri ─────────────────────────────────────────────────────

_declustered: pd.DataFrame | None = None
_bmap_cache: dict[str, list] = {}


_decluster_lock = threading.Lock()


def declustered_catalog() -> pd.DataFrame:
    """Gardner-Knopoff ile ayıklanmış katalog (süreç başına bir kez hesaplanır)."""
    global _declustered
    base = catalog()  # kendi kilidini alır — _decluster_lock içinde ÇAĞIRMA (deadlock)
    with _decluster_lock:
        if _declustered is None:
            _declustered = gardner_knopoff(base)
        return _declustered


@app.get("/api/analysis/gr")
def api_gr(
    start: str | None = None,
    end: str | None = None,
    min_mag: float = 0.0,
    max_mag: float = 10.0,
    declustered: bool = False,
):
    """Gutenberg-Richter analizi: Mc, b-değeri ve kümülatif eğri."""
    df = _filter_catalog(start, end, min_mag, max_mag, 0.0, 1000.0, None)
    if declustered:
        keep = declustered_catalog()
        df = df.merge(keep[keep["is_mainshock"]][["eventDate", "latitude", "longitude"]],
                      on=["eventDate", "latitude", "longitude"], how="inner")

    mags = df["magnitude"].to_numpy()
    if len(mags) < 50:
        raise HTTPException(status_code=400, detail="Bu filtrelerle güvenilir analiz için yeterli kayıt yok (min 50).")

    mc = estimate_mc(mags)
    fit = b_value(mags, mc) if mc is not None else None
    return {
        "n_total": int(len(mags)),
        "mc": mc,
        "fit": fit,
        "declustered": declustered,
        "curve": gr_curve(mags, mc, fit),
    }


@app.get("/api/analysis/decluster")
def api_decluster():
    """Katalog ayıklama özeti (Gardner-Knopoff)."""
    df = declustered_catalog()
    n = len(df)
    main = int(df["is_mainshock"].sum())
    return {
        "total": n,
        "mainshocks": main,
        "aftershocks": n - main,
        "aftershock_pct": round(100 * (n - main) / n, 1) if n else 0,
    }


@app.get("/api/analysis/bmap")
def api_bmap(declustered: bool = True, cell_deg: float = Query(1.0, ge=0.25, le=2.0)):
    """Izgara bazlı b-değeri haritası."""
    key = f"{declustered}-{cell_deg}"
    if key not in _bmap_cache:
        df = declustered_catalog()
        if declustered:
            df = df[df["is_mainshock"]]
        _bmap_cache[key] = b_value_grid(df, cell_deg=cell_deg)
    cells = _bmap_cache[key]
    return {"count": len(cells), "cells": cells, "declustered": declustered}


@app.get("/api/analysis/mainshocks")
def api_mainshocks(min_mag: float = 6.0, since: str = "1990-01-01",
                   limit: int = Query(30, le=100)):
    """Artçı şok tahmini için aday ana şoklar (en büyükten küçüğe).

    Varsayılan olarak modern enstrümantal dönemle (1990+) sınırlanır: daha eski
    ana şokların artçı dizileri M≥4 katalogda temsil edilmediğinden Omori
    uyumu kurulamaz.
    """
    df = catalog()
    df = df[(df["magnitude"] >= min_mag) & (df["eventDate"] >= pd.Timestamp(since))]
    df = df.sort_values("magnitude", ascending=False).head(limit)
    return {"mainshocks": _records(df[["eventDate", "latitude", "longitude", "magnitude", "location"]])}


@app.get("/api/analysis/aftershock")
def api_aftershock(time: str, lat: float, lon: float, mag: float):
    """Seçilen ana şok dizisi için Omori-Utsu / Reasenberg-Jones tahmini."""
    try:
        t0 = pd.Timestamp(time).tz_localize(None) if pd.Timestamp(time).tzinfo else pd.Timestamp(time)
    except ValueError:
        raise HTTPException(status_code=422, detail="Geçersiz zaman formatı.")
    return aftershock_forecast(catalog(), t0, lat, lon, mag)


# ── Çoklu katalog karşılaştırması ────────────────────────────────────────────

_compare_cache: dict[str, tuple[float, dict]] = {}
_compare_lock = threading.Lock()


@app.get("/api/compare")
def api_compare(
    start: str,
    end: str,
    min_mag: float = Query(4.0, ge=0.0, le=10.0),
    samples: int = Query(50, ge=0, le=200),
):
    """AFAD ve USGS kataloglarını verilen pencerede karşılaştırır.

    Canlı iki API'ye gittiği için sonuç 30 dakika önbelleklenir.
    """
    key = f"{start}|{end}|{min_mag}|{samples}"
    now = time.monotonic()
    with _compare_lock:
        hit = _compare_cache.get(key)
        if hit and now - hit[0] < COMPARE["cache_ttl_s"]:
            return hit[1]

    try:
        result = compare_window(start, end, min_mag)
        result["pairs"] = sample_pairs(start, end, min_mag, samples) if samples else []
    except Exception as e:  # ağ/kaynak hatalarını 502 olarak bildir
        raise HTTPException(status_code=502, detail=f"Katalog kaynaklarına erişilemedi: {e}")

    with _compare_lock:
        _compare_cache[key] = (now, result)
    return result


# ── Etki analizi (sarsıntı şiddeti + maruziyet) ──────────────────────────────

@app.get("/api/impact")
def api_impact(
    mag: float = Query(..., ge=3.0, le=9.0),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    depth: float = Query(10.0, ge=0.0, le=700.0),
    min_mmi: float = Query(3.0, ge=1.0, le=12.0),
):
    """Bir deprem (gerçek veya senaryo) için yerleşim bazlı şiddet analizi."""
    try:
        return assess(mag, lat, lon, depth, min_mmi=min_mmi)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/shelters")
def api_shelters(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(30.0, gt=0, le=200),
):
    """Çevredeki toplanma alanları — OSM topluluk verisi, EKSİKTİR."""
    return nearby_shelters(lat, lon, radius_km)


# ── Model doğrulama ──────────────────────────────────────────────────────────

_validation_cache: dict[str, object] = {}


@app.get("/api/validation/intensity")
def api_validate_intensity(min_responses: int = Query(3, ge=1, le=50)):
    """Şiddet modelinin gözlenen DYFI şiddetlerine karşı başarımı."""
    key = f"int-{min_responses}"
    if key not in _validation_cache:
        try:
            _validation_cache[key] = validate_intensity(min_responses)
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail=str(e))
    return _validation_cache[key]


@app.get("/api/validation/aftershock")
def api_validate_aftershock(
    min_mag: float = Query(5.5, ge=5.0, le=8.0),
    learn_days: float = Query(7.0, gt=0, le=90),
    forecast_days: float = Query(30.0, gt=0, le=365),
):
    """Artçı şok tahmininin geçmiş diziler üzerinde sözde-ileriye dönük testi."""
    key = f"aft-{min_mag}-{learn_days}-{forecast_days}"
    if key not in _validation_cache:
        _validation_cache[key] = validate_aftershock_forecasts(
            catalog(), min_mag=min_mag, learn_days=learn_days, forecast_days=forecast_days)
    return _validation_cache[key]


@app.get("/api/catalog/completeness")
def api_completeness():
    """Kataloğun dönemleri ve tamlık eşikleri — sayı karşılaştırma tuzağı uyarısı."""
    return catalog_completeness(catalog())


# ── Fay senaryoları ──────────────────────────────────────────────────────────

_scenario_cache: dict[str, dict] = {}


@app.get("/api/faults/sources")
def api_fault_sources(limit: int = Query(300, ge=1, le=1000)):
    """Büyük deprem üretebilen faylar — Mmax, yinelenme aralığı ve olasılıklar."""
    try:
        return {"faults": sources_table(limit=limit)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/faults/geometry")
def api_fault_geometry():
    """Fay kaynaklarının harita için GeoJSON'u."""
    try:
        gdf = load_fault_sources()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    cols = ["fault_id", "label", "slip_type", "mmax", "recurrence_years", "p30", "p50", "geometry"]
    return json.loads(gdf[[c for c in cols if c in gdf.columns]].to_json())


@app.get("/api/scenario")
def api_scenario(
    fault_id: str,
    rupture_fraction: float = Query(1.0, ge=0.05, le=1.0),
    magnitude: float | None = Query(None, ge=4.0, le=8.5),
):
    """Seçilen fay için kırılma senaryosu."""
    key = f"{fault_id}|{rupture_fraction}|{magnitude}"
    if key in _scenario_cache:
        return _scenario_cache[key]
    try:
        result = run_scenario(fault_id, rupture_fraction, magnitude)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if len(_scenario_cache) > 200:
        _scenario_cache.clear()
    _scenario_cache[key] = result
    return result


@app.get("/api/vs30")
def api_vs30():
    """Zemin (Vs30) ızgarasının özeti ve bilinen sınırları."""
    try:
        return vs30_summary()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/faults")
def api_faults():
    path = PATHS["faults_simple"]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Sadeleştirilmiş fay dosyası bulunamadı.")
    return FileResponse(path, media_type="application/geo+json",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/status")
def api_status_endpoint():
    return api_status()


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
