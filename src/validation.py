"""
Model doğrulama — projedeki tahminler gerçekle ne kadar uyuşuyor?

İki bağımsız test:

1) ŞİDDET MODELİ (src/impact.py) — USGS DYFI gözlemlerine karşı
   Tahmin edilen MMI ile insanların bildirdiği gözlenen şiddet kıyaslanır.
   Artık = gözlenen − tahmin  (pozitif ⇒ model AZ tahmin ediyor)

2) ARTÇI ŞOK TAHMİNİ (src/seismology.py) — sözde-ileriye dönük N-testi
   Dizinin ilk N günü ile model kurulur, sonraki M gün TAHMİN edilir ve
   gerçekleşenle kıyaslanır. Model kurulurken gelecekteki veri kullanılmaz
   (data leakage yok). CSEP N-testi ölçütü: gözlenen sayı, tahminin Poisson
   dağılımının uç kuyruklarında kalıyorsa model reddedilir.

Doğrulamanın kendi sınırları da gizlenmemeli:
- DYFI gönüllü katılımdır: kentsel alanlara yanlıdır, kırsalı az temsil eder.
- DYFI yüksek şiddetlerde doyuma uğrar (insanlar MMI 9 ile 10'u ayırt edemez).
- N-testi Poisson varsayar; artçı dizileri kümelenmiş olduğu için gerçek
  saçılım Poisson'dan geniştir → test gerçekte olduğundan biraz katıdır.
"""

import logging
import os

import numpy as np
import pandas as pd
from scipy.stats import poisson

from src.config import PATHS, VALIDATION
from src.impact import predict_mmi
from src.seismology import (
    _haversine_km,
    _omori_integral,
    b_value,
    estimate_mc,
    fit_omori,
    gk_windows,
)

log = logging.getLogger(__name__)


# ── 1) Şiddet modeli doğrulaması ─────────────────────────────────────────────

def load_dyfi(min_responses: int = None) -> pd.DataFrame:
    """DYFI gözlemlerini yükler ve gürültülü kutuları eler."""
    path = PATHS["dyfi"]
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"DYFI verisi yok: {path}. 'python -m src.prepare_validation' çalıştırın.")
    min_responses = VALIDATION["min_responses"] if min_responses is None else min_responses
    df = pd.read_parquet(path)
    return df[df["n_responses"] >= min_responses].reset_index(drop=True)


def intensity_residuals(min_responses: int = None) -> pd.DataFrame:
    """Her DYFI kutusu için tahmin, gözlem ve artığı hesaplar."""
    df = load_dyfi(min_responses).copy()
    if df.empty:
        return df
    df["rhyp_km"] = np.sqrt(df["epicentral_km"] ** 2 + df["event_depth_km"] ** 2)
    df["predicted_mmi"] = [
        float(predict_mmi(m, r)) for m, r in zip(df["event_mag"], df["rhyp_km"])
    ]
    # Pozitif artık ⇒ gerçek sarsıntı tahminden ŞİDDETLİ (model az tahmin etti)
    df["residual"] = df["observed_mmi"] - df["predicted_mmi"]
    return df


def _bin_stats(df: pd.DataFrame, label: str, bins: list[tuple], column: str,
               min_n: int = 20) -> list[dict]:
    out = []
    for lo, hi in bins:
        sel = df[(df[column] >= lo) & (df[column] < hi)]
        if len(sel) < min_n:
            continue
        out.append({
            "group": label,
            "range": f"{lo:g}–{hi:g}",
            "n": int(len(sel)),
            "bias": round(float(sel["residual"].mean()), 3),
            "mae": round(float(sel["residual"].abs().mean()), 3),
            "rmse": round(float(np.sqrt((sel["residual"] ** 2).mean())), 3),
        })
    return out


def validate_intensity(min_responses: int = None) -> dict:
    """Şiddet modelinin DYFI gözlemlerine karşı başarımı."""
    df = intensity_residuals(min_responses)
    if df.empty:
        return {"observations": 0, "note": "Filtreden geçen gözlem yok."}

    resid = df["residual"]
    overall = {
        "observations": int(len(df)),
        "events": int(df["event_id"].nunique()),
        "bias": round(float(resid.mean()), 3),
        "median_bias": round(float(resid.median()), 3),
        "mae": round(float(resid.abs().mean()), 3),
        "rmse": round(float(np.sqrt((resid ** 2).mean())), 3),
        "within_1_mmi": round(float((resid.abs() <= 1.0).mean()), 3),
    }

    by_distance = _bin_stats(df, "Uzaklık (km)",
                             [(0, 25), (25, 50), (50, 100), (100, 200), (200, 300)], "rhyp_km")
    by_magnitude = _bin_stats(df, "Büyüklük",
                              [(4.5, 5.5), (5.5, 6.5), (6.5, 7.0), (7.0, 8.5)], "event_mag")

    # Saçılım grafiği için örneklem (tahmin vs gözlem)
    sample = df.sample(min(len(df), 900), random_state=1)
    scatter = [{"predicted": round(float(r["predicted_mmi"]), 2),
                "observed": round(float(r["observed_mmi"]), 2),
                "distance_km": round(float(r["rhyp_km"]), 1),
                "magnitude": round(float(r["event_mag"]), 1)}
               for _, r in sample.iterrows()]

    return {
        "overall": overall,
        "by_distance": by_distance,
        "by_magnitude": by_magnitude,
        "scatter": scatter,
        "caveats": [
            "DYFI gönüllü katılıma dayanır; kentsel alanlara yanlıdır.",
            "Yüksek şiddetlerde DYFI doyuma uğrar (MMI 9 ile 10 ayırt edilemez).",
            f"Yalnızca en az {VALIDATION['min_responses']} anket içeren kutular kullanıldı; "
            "tek yanıtlı kutular çok gürültülüdür.",
        ],
    }


# ── 2) Artçı şok tahmini doğrulaması ─────────────────────────────────────────

def _sequence(catalog: pd.DataFrame, t0, lat, lon, mag, until_days: float) -> pd.DataFrame:
    """Ana şoku izleyen, mekânsal pencere içindeki artçılar."""
    radius_km, _ = gk_windows(mag)
    radius_km = max(radius_km, 50.0)
    end = t0 + pd.Timedelta(days=until_days)
    seq = catalog[(catalog["eventDate"] > t0) & (catalog["eventDate"] <= end)]
    if seq.empty:
        return seq
    d = _haversine_km(lat, lon, seq["latitude"].to_numpy(), seq["longitude"].to_numpy())
    return seq[d <= radius_km]


def expected_count(omori: dict, b: float, mc: float, target_mag: float,
                   t_start: float, t_end: float) -> float:
    """Omori + Gutenberg-Richter'den beklenen artçı sayısı."""
    integral = _omori_integral(omori["c"], omori["p"], t_start, t_end)
    return float(10 ** (-b * (target_mag - mc)) * omori["K"] * integral)


def n_test(expected: float, observed: int, alpha: float = None) -> dict:
    """CSEP N-testi: gözlenen sayı, Poisson tahmininin kuyruklarında mı?"""
    alpha = VALIDATION["n_test_alpha"] if alpha is None else alpha
    if expected <= 0:
        return {"expected": 0.0, "observed": int(observed), "delta1": None,
                "delta2": None, "passed": None}
    delta1 = float(1.0 - poisson.cdf(observed - 1, expected))   # gözlenenin en az bu kadar olma olasılığı
    delta2 = float(poisson.cdf(observed, expected))             # gözlenenin en fazla bu kadar olma olasılığı
    return {
        "expected": round(float(expected), 2),
        "observed": int(observed),
        "delta1": round(delta1, 4),
        "delta2": round(delta2, 4),
        "passed": bool(delta1 > alpha and delta2 > alpha),
    }


def validate_sequence(catalog: pd.DataFrame, t0, lat: float, lon: float, mag: float,
                      learn_days: float = None, forecast_days: float = None,
                      target_offset: float = None) -> dict | None:
    """Tek bir dizi için sözde-ileriye dönük test.

    Model YALNIZCA ilk learn_days günün verisiyle kurulur; sonraki
    forecast_days gün tahmin edilip gerçekleşenle kıyaslanır.
    """
    learn_days = learn_days if learn_days is not None else VALIDATION["learn_days"]
    forecast_days = forecast_days if forecast_days is not None else VALIDATION["forecast_days"]
    target_offset = VALIDATION["target_offset"] if target_offset is None else target_offset

    learn = _sequence(catalog, t0, lat, lon, mag, learn_days)
    if len(learn) < 25:
        return None

    mags = learn["magnitude"].to_numpy()
    mc = estimate_mc(mags)
    if mc is None:
        return None
    learn_mc = learn[learn["magnitude"] >= mc - 1e-9]
    if len(learn_mc) < 20:
        return None

    bres = b_value(learn_mc["magnitude"].to_numpy(), mc)
    if bres is None:
        return None

    t_days = ((learn_mc["eventDate"] - t0) / pd.Timedelta(days=1)).to_numpy()
    omori = fit_omori(t_days, T=learn_days)
    if omori is None:
        return None

    target_mag = mc + target_offset
    exp_n = expected_count(omori, bres["b"], mc, target_mag,
                           learn_days, learn_days + forecast_days)

    window = _sequence(catalog, t0, lat, lon, mag, learn_days + forecast_days)
    observed_df = window[(window["eventDate"] > t0 + pd.Timedelta(days=learn_days))
                         & (window["magnitude"] >= target_mag - 1e-9)]

    result = n_test(exp_n, len(observed_df))
    result.update({
        "time": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "magnitude": float(mag),
        "mc": float(mc),
        "b": float(bres["b"]),
        "p": float(omori["p"]),
        "target_mag": round(float(target_mag), 1),
        "learn_events": int(len(learn_mc)),
    })
    return result


def validate_aftershock_forecasts(catalog: pd.DataFrame, min_mag: float = 6.0,
                                  learn_days: float = None, forecast_days: float = None,
                                  limit: int = 40) -> dict:
    """Katalogdaki büyük diziler üzerinde toplu N-testi."""
    learn_days = learn_days if learn_days is not None else VALIDATION["learn_days"]
    forecast_days = forecast_days if forecast_days is not None else VALIDATION["forecast_days"]

    mains = (catalog[catalog["magnitude"] >= min_mag]
             .sort_values("eventDate", ascending=False).head(limit))

    tested, skipped = [], 0
    for _, m in mains.iterrows():
        out = validate_sequence(catalog, m["eventDate"], m["latitude"], m["longitude"],
                                m["magnitude"], learn_days, forecast_days)
        if out is None:
            skipped += 1
            continue
        out["location"] = m.get("location", "")
        tested.append(out)

    summary = {
        "candidates": int(len(mains)),
        "tested": len(tested),
        "skipped_insufficient_data": skipped,
        "learn_days": learn_days,
        "forecast_days": forecast_days,
        "sequences": tested,
    }
    if tested:
        passed = sum(1 for t in tested if t["passed"])
        total_exp = sum(t["expected"] for t in tested)
        total_obs = sum(t["observed"] for t in tested)
        under = sum(1 for t in tested if t["observed"] > t["expected"])
        summary.update({
            "passed": passed,
            "pass_rate": round(passed / len(tested), 3),
            "total_expected": round(total_exp, 1),
            "total_observed": total_obs,
            "ratio_observed_expected": round(total_obs / total_exp, 3) if total_exp > 0 else None,
            "under_forecast_count": under,
        })
    summary["caveats"] = [
        "Model yalnızca öğrenme penceresindeki veriyle kurulur; gelecekteki "
        "veri kullanılmaz (sözde-ileriye dönük test).",
        "N-testi Poisson varsayar; artçılar kümelendiği için gerçek saçılım daha "
        "geniştir, dolayısıyla test olduğundan biraz katıdır.",
        "Katalog tamlığı geçmişe gittikçe düşer; eski dizilerde artçı sayısı eksik olabilir.",
    ]
    return summary
