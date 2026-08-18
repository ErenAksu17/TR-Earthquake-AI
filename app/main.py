"""
TR Earthquake AI — FastAPI backend.

Uçlar:
  GET /api/live?source=all          Son 24 saat (canlı, 60 sn sunucu önbelleği)
  GET /api/quakes?...               Filtreli arşiv kataloğu (JSON veya CSV)
  GET /api/stats?...                Filtreli arşiv istatistikleri (grafikler için)
  GET /api/faults                   Sadeleştirilmiş diri fay GeoJSON'u
  GET /api/status                   Kaynak API erişilebilirlik durumu
  GET /                             Leaflet tabanlı arayüz (app/static)

Zaman kuralı: API tüm zamanları UTC (ISO 8601, 'Z' soneki) döner;
yerel saate çeviri istemcide yapılır.
"""

import io
import os
import sys
import threading
import time

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import PATHS  # noqa: E402
from src.fetch_kandilli import api_status, get_live  # noqa: E402
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
