"""Doğrulama modülü testleri — N-testi istatistiği ve artık hesabı."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

from src.validation import (
    expected_count,
    intensity_residuals,
    load_dyfi,
    n_test,
    validate_aftershock_forecasts,
    validate_intensity,
    validate_sequence,
)


class TestNTest:
    """CSEP N-testi — Poisson kuyruk ölçütü."""

    def test_observed_matches_expected_passes(self):
        assert n_test(10.0, 10)["passed"] is True

    def test_wildly_over_observed_fails(self):
        # 1 beklenirken 30 gözlenirse model reddedilmeli
        r = n_test(1.0, 30)
        assert r["passed"] is False
        assert r["delta2"] > 0.975

    def test_wildly_under_observed_fails(self):
        # 100 beklenirken 0 gözlenirse model reddedilmeli
        r = n_test(100.0, 0)
        assert r["passed"] is False

    def test_zero_expected_is_undecidable(self):
        r = n_test(0.0, 3)
        assert r["passed"] is None

    def test_deltas_are_probabilities(self):
        r = n_test(15.0, 12)
        assert 0.0 <= r["delta1"] <= 1.0
        assert 0.0 <= r["delta2"] <= 1.0

    def test_small_deviation_still_passes(self):
        # Poisson saçılımı içindeki sapma reddedilmemeli
        assert n_test(20.0, 24)["passed"] is True


class TestExpectedCount:

    def test_scales_with_gutenberg_richter(self):
        omori = {"K": 100.0, "c": 0.1, "p": 1.1}
        n_mc = expected_count(omori, b=1.0, mc=4.0, target_mag=4.0, t_start=1, t_end=30)
        n_hi = expected_count(omori, b=1.0, mc=4.0, target_mag=5.0, t_start=1, t_end=30)
        # b=1 ⇒ bir büyüklük derecesi yukarısı ~10 kat az
        assert n_mc / n_hi == pytest.approx(10.0, rel=0.01)

    def test_longer_window_more_events(self):
        omori = {"K": 100.0, "c": 0.1, "p": 1.1}
        short = expected_count(omori, 1.0, 4.0, 4.0, 1, 10)
        long_ = expected_count(omori, 1.0, 4.0, 4.0, 1, 100)
        assert long_ > short

    def test_decay_reduces_later_windows(self):
        omori = {"K": 100.0, "c": 0.1, "p": 1.2}
        early = expected_count(omori, 1.0, 4.0, 4.0, 1, 11)
        late = expected_count(omori, 1.0, 4.0, 4.0, 101, 111)
        assert late < early


class TestIntensityValidation:

    def test_residuals_computed(self):
        df = intensity_residuals()
        assert len(df) > 100
        assert "residual" in df.columns
        # artık = gözlenen − tahmin
        row = df.iloc[0]
        assert row["residual"] == pytest.approx(row["observed_mmi"] - row["predicted_mmi"], abs=1e-9)

    def test_response_filter_applied(self):
        assert (load_dyfi(min_responses=5)["n_responses"] >= 5).all()

    def test_stricter_filter_yields_fewer(self):
        assert len(load_dyfi(min_responses=10)) < len(load_dyfi(min_responses=1))

    def test_summary_shape(self):
        v = validate_intensity()
        assert v["overall"]["observations"] > 100
        assert v["overall"]["mae"] > 0
        assert len(v["by_distance"]) >= 3
        assert len(v["caveats"]) >= 3

    def test_model_is_broadly_calibrated(self):
        # Yayımlanmış denklemin kendi sigması ~0.8-1.2; MAE bu mertebede olmalı
        v = validate_intensity()
        assert v["overall"]["mae"] < 1.5
        assert abs(v["overall"]["bias"]) < 0.5

    def test_scatter_sample_bounded(self):
        v = validate_intensity()
        assert 0 < len(v["scatter"]) <= 900


@pytest.fixture(scope="module")
def catalog():
    from src.pipeline import load_merged
    return load_merged()


class TestSequenceValidation:

    def test_kahramanmaras_sequence_testable(self, catalog):
        t0 = pd.Timestamp("2023-02-06 01:17:32")
        out = validate_sequence(catalog, t0, 37.288, 37.043, 7.8)
        assert out is not None
        assert out["expected"] > 0
        assert out["observed"] >= 0
        assert 0.5 < out["b"] < 2.0
        assert 0.5 < out["p"] < 2.5

    def test_no_leakage_learning_window_only(self, catalog):
        # Öğrenme penceresi uzarsa daha çok olayla model kurulur —
        # kısa pencere gelecekteki veriyi kullanmadığını gösterir
        t0 = pd.Timestamp("2023-02-06 01:17:32")
        short = validate_sequence(catalog, t0, 37.288, 37.043, 7.8, learn_days=3)
        long_ = validate_sequence(catalog, t0, 37.288, 37.043, 7.8, learn_days=14)
        assert short["learn_events"] < long_["learn_events"]

    def test_sparse_sequence_returns_none(self, catalog):
        # Artçısı olmayan uydurma bir konum test edilemez
        t0 = pd.Timestamp("1905-01-01")
        assert validate_sequence(catalog, t0, 36.5, 26.5, 6.0) is None

    def test_aggregate_report(self, catalog):
        v = validate_aftershock_forecasts(catalog, min_mag=6.0, limit=25)
        assert v["candidates"] > 0
        assert v["tested"] + v["skipped_insufficient_data"] == v["candidates"]
        assert len(v["caveats"]) >= 3
        if v["tested"]:
            assert 0.0 <= v["pass_rate"] <= 1.0
            for s in v["sequences"]:
                assert s["expected"] >= 0


class TestOperationalMetrics:
    """Poisson N-testini tamamlayan operasyonel tahmin ölçütleri."""

    def test_factor_two_and_bias_reported(self, catalog):
        v = validate_aftershock_forecasts(catalog, min_mag=5.5, limit=40)
        if not v["tested"]:
            pytest.skip("test edilebilir dizi yok")
        assert 0 <= v["within_factor_2"] <= v["tested"]
        assert 0.0 <= v["within_factor_2_rate"] <= 1.0
        assert v["median_log10_ratio"] is not None

    def test_factor_two_is_looser_than_poisson(self, catalog):
        # Aşırı saçılım nedeniyle "iki kat içinde" oranı N-testinden gevşek olmalı
        v = validate_aftershock_forecasts(catalog, min_mag=5.5, limit=40)
        if v["tested"] < 5:
            pytest.skip("örneklem küçük")
        assert v["within_factor_2_rate"] >= v["pass_rate"]

    def test_dispersion_caveat_present(self, catalog):
        v = validate_aftershock_forecasts(catalog, min_mag=5.5, limit=20)
        assert any("kümelen" in c.lower() for c in v["caveats"])
