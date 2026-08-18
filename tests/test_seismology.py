"""Sismoloji modülü testleri — sentetik verilerle parametre geri kazanımı."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

from src.seismology import (
    _omori_integral,
    aftershock_forecast,
    b_value,
    b_value_grid,
    estimate_mc,
    fit_omori,
    gardner_knopoff,
    gk_windows,
    gr_curve,
)

RNG = np.random.default_rng(42)


def synthetic_gr_mags(n: int, b: float = 1.0, mc: float = 4.0, dm: float = 0.1) -> np.ndarray:
    """Gutenberg-Richter'e uyan sentetik büyüklükler (üstel dağılım + binleme).

    Sürekli büyüklükler Mc - dm/2'den başlatılır ki yuvarlama sonrası ilk bin
    (Mc) tam dolu olsun — Utsu binleme düzeltmesinin varsayımı budur.
    """
    beta = b * np.log(10)
    mags = (mc - dm / 2) + RNG.exponential(1 / beta, size=n)
    return np.round(mags / dm) * dm


class TestBValue:

    def test_recovers_b_of_one(self):
        mags = synthetic_gr_mags(5000, b=1.0, mc=4.0)
        res = b_value(mags, mc=4.0)
        assert res is not None
        assert res["b"] == pytest.approx(1.0, abs=0.05)

    def test_recovers_low_b(self):
        mags = synthetic_gr_mags(5000, b=0.7, mc=4.0)
        res = b_value(mags, mc=4.0)
        assert res["b"] == pytest.approx(0.7, abs=0.05)

    def test_uncertainty_shrinks_with_n(self):
        small = b_value(synthetic_gr_mags(100), mc=4.0)
        large = b_value(synthetic_gr_mags(5000), mc=4.0)
        assert large["b_err"] < small["b_err"]

    def test_too_few_events_returns_none(self):
        assert b_value(synthetic_gr_mags(10), mc=4.0) is None

    def test_mc_estimate_near_completeness(self):
        mags = synthetic_gr_mags(3000, b=1.0, mc=4.0)
        mc = estimate_mc(mags)
        # Tam katalogda mod en küçük bindedir → Mc ≈ 4.0 + 0.2
        assert 4.0 <= mc <= 4.4

    def test_gr_curve_monotone_decreasing(self):
        mags = synthetic_gr_mags(1000)
        fit = b_value(mags, mc=4.0)
        curve = gr_curve(mags, 4.0, fit)
        assert curve["counts"] == sorted(curve["counts"], reverse=True)
        assert "fit" in curve


class TestGardnerKnopoff:

    def test_windows_grow_with_magnitude(self):
        d5, t5 = gk_windows(5.0)
        d7, t7 = gk_windows(7.0)
        assert d7 > d5 and t7 > t5

    def test_aftershocks_flagged(self):
        # Ana şok + 5 gün içinde 10 km çevresinde 5 artçı + 1 yıl sonra bağımsız deprem
        rows = [{"eventDate": "2023-02-06 01:17:00", "latitude": 37.2, "longitude": 37.0, "magnitude": 7.8}]
        for i in range(5):
            rows.append({"eventDate": f"2023-02-{7+i:02d} 12:00:00",
                         "latitude": 37.25, "longitude": 37.05, "magnitude": 4.5})
        rows.append({"eventDate": "2024-06-01 00:00:00", "latitude": 40.0, "longitude": 30.0, "magnitude": 5.0})
        df = pd.DataFrame(rows)
        df["eventDate"] = pd.to_datetime(df["eventDate"])

        out = gardner_knopoff(df)
        assert out["is_mainshock"].sum() == 2          # ana şok + bağımsız deprem
        assert (~out["is_mainshock"]).sum() == 5       # artçılar

    def test_foreshock_not_flagged(self):
        # Klasik pencere yalnızca sonrayı tarar: önceki küçük deprem korunur
        df = pd.DataFrame([
            {"eventDate": "2023-02-05 01:00:00", "latitude": 37.2, "longitude": 37.0, "magnitude": 4.0},
            {"eventDate": "2023-02-06 01:17:00", "latitude": 37.2, "longitude": 37.0, "magnitude": 7.8},
        ])
        df["eventDate"] = pd.to_datetime(df["eventDate"])
        assert gardner_knopoff(df)["is_mainshock"].all()

    def test_empty_catalog(self):
        df = pd.DataFrame(columns=["eventDate", "latitude", "longitude", "magnitude"])
        df["eventDate"] = pd.to_datetime(df["eventDate"])
        assert gardner_knopoff(df).empty


def synthetic_omori_times(n: int, K_unused, c: float, p: float, T: float) -> np.ndarray:
    """Omori-Utsu yoğunluğundan ters dönüşümle örneklem (t ∈ (0, T])."""
    u = RNG.uniform(size=n)
    total = _omori_integral(c, p, 0.0, T)
    lam = u * total
    # Λ(t) = ((t+c)^(1-p) - c^(1-p)) / (1-p)  → t'yi çöz
    t = (lam * (1 - p) + c ** (1 - p)) ** (1 / (1 - p)) - c
    return t[(t > 0) & (t <= T)]


class TestOmori:

    def test_recovers_p(self):
        t = synthetic_omori_times(2000, None, c=0.1, p=1.2, T=100.0)
        fit = fit_omori(t, T=100.0)
        assert fit is not None
        assert fit["p"] == pytest.approx(1.2, abs=0.1)

    def test_integral_p_equals_one(self):
        # p=1 özel durumu logaritmik
        assert _omori_integral(0.1, 1.0, 0.0, 10.0) == pytest.approx(np.log(10.1 / 0.1))

    def test_too_few_returns_none(self):
        assert fit_omori(np.array([0.5, 1.0, 2.0])) is None


class TestForecast:

    def _build_sequence(self):
        t0 = pd.Timestamp("2023-02-06 01:17:00")
        times = synthetic_omori_times(400, None, c=0.05, p=1.1, T=30.0)
        mags = synthetic_gr_mags(len(times), b=1.0, mc=4.0)
        df = pd.DataFrame({
            "eventDate": t0 + pd.to_timedelta(times, unit="D"),
            "latitude": 37.2 + RNG.normal(0, 0.2, len(times)),
            "longitude": 37.0 + RNG.normal(0, 0.2, len(times)),
            "magnitude": mags,
        })
        return df, t0

    def test_forecast_structure_and_bounds(self):
        df, t0 = self._build_sequence()
        res = aftershock_forecast(df, t0, 37.2, 37.0, 7.8,
                                  now=t0 + pd.Timedelta(days=30))
        assert res["forecast"] is not None
        for f in res["forecast"]:
            assert 0.0 <= f["probability"] <= 1.0
            assert f["expected"] >= 0.0

    def test_probability_decreases_with_magnitude(self):
        df, t0 = self._build_sequence()
        res = aftershock_forecast(df, t0, 37.2, 37.0, 7.8,
                                  now=t0 + pd.Timedelta(days=30))
        by_h = [f for f in res["forecast"] if f["horizon_days"] == 7]
        probs = [f["probability"] for f in sorted(by_h, key=lambda x: x["min_mag"])]
        assert probs == sorted(probs, reverse=True)

    def test_sparse_sequence_returns_note(self):
        t0 = pd.Timestamp("2024-01-01")
        df = pd.DataFrame({
            "eventDate": [t0 + pd.Timedelta(hours=1)],
            "latitude": [39.0], "longitude": [35.0], "magnitude": [4.2],
        })
        res = aftershock_forecast(df, t0, 39.0, 35.0, 5.5,
                                  now=t0 + pd.Timedelta(days=7))
        assert res["forecast"] is None
        assert "note" in res


class TestBGrid:

    def test_grid_cells_have_valid_b(self):
        # Tek hücrede yoğun sentetik aktivite
        mags = synthetic_gr_mags(500, b=1.0, mc=4.0)
        df = pd.DataFrame({
            "latitude": 39.1 + RNG.uniform(-0.15, 0.15, len(mags)),
            "longitude": 35.1 + RNG.uniform(-0.15, 0.15, len(mags)),
            "magnitude": mags,
        })
        cells = b_value_grid(df, cell_deg=0.5, min_n=30)
        assert len(cells) >= 1
        assert all(0.3 < c["b"] < 2.0 for c in cells)
