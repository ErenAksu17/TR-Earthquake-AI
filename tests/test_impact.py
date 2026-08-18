"""Etki analizi testleri — IPE davranışı, bantlar, maruziyet verisi."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from src.config import IPE
from src.impact import (
    assess,
    hypocentral_distance_km,
    mmi_band,
    mmi_sigma,
    nearby_shelters,
    predict_mmi,
    radius_for_mmi,
    settlements,
)


class TestIPE:
    """Allen, Wald & Worden (2012) denkleminin fiziksel davranışı."""

    def test_mmi_decreases_with_distance(self):
        vals = [float(predict_mmi(7.0, d)) for d in (10, 25, 50, 100, 200, 300)]
        assert vals == sorted(vals, reverse=True)

    def test_mmi_increases_with_magnitude(self):
        vals = [float(predict_mmi(m, 50)) for m in (4.5, 5.5, 6.5, 7.5)]
        assert vals == sorted(vals)

    def test_kahramanmaras_epicentral_intensity_plausible(self):
        # M7.8, odak 8.6 km — episantrda VIII civarı beklenir (gözlenen IX;
        # nokta-kaynak varsayımı yakın alanı az tahmin eder, belgelenmiştir)
        mmi = float(predict_mmi(7.8, 8.6))
        assert 7.5 <= mmi <= 9.0

    def test_far_field_still_felt(self):
        # M7.8'in 200 km'de hâlâ hissedilir düzeyde olması beklenir
        assert 5.0 <= float(predict_mmi(7.8, 200)) <= 6.5

    def test_small_event_not_damaging_at_distance(self):
        # M4.5, 100 km — hasar eşiğinin (VI) çok altında
        assert float(predict_mmi(4.5, 100)) < 4.0

    def test_anelastic_term_only_beyond_50km(self):
        # 50 km'nin hemen altı/üstünde süreklilik korunmalı (sıçrama olmamalı)
        just_below = float(predict_mmi(6.5, 49.9))
        just_above = float(predict_mmi(6.5, 50.1))
        assert abs(just_below - just_above) < 0.02

    def test_sigma_decreases_with_distance(self):
        assert float(mmi_sigma(5)) > float(mmi_sigma(200))

    def test_sigma_within_published_bounds(self):
        for d in (0, 10, 50, 300):
            s = float(mmi_sigma(d))
            assert IPE["s1"] <= s <= IPE["s1"] + IPE["s2"] + 1e-9

    def test_vectorized_input(self):
        out = predict_mmi(6.0, np.array([10.0, 50.0, 100.0]))
        assert out.shape == (3,)


class TestDistance:

    def test_depth_included_in_hypocentral_distance(self):
        # Aynı noktada ama 100 km derinde → uzaklık ≈ 100 km
        d = float(hypocentral_distance_km(39.0, 35.0, 100.0, 39.0, 35.0))
        assert d == pytest.approx(100.0, abs=0.1)

    def test_surface_distance_correct(self):
        # 1 derece enlem ≈ 111 km
        d = float(hypocentral_distance_km(39.0, 35.0, 0.0, 40.0, 35.0))
        assert d == pytest.approx(111.2, abs=1.0)


class TestRadius:

    def test_radius_grows_with_magnitude(self):
        r6, _ = radius_for_mmi(6.0, 6.0, 10.0)
        r7, _ = radius_for_mmi(7.0, 6.0, 10.0)
        assert r7 > r6

    def test_unreachable_intensity_returns_none(self):
        # M4.0 asla MMI IX üretmez
        radius, truncated = radius_for_mmi(4.0, 9.0, 10.0)
        assert radius is None and truncated is False

    def test_beyond_model_range_flagged(self):
        # M7.8'de MMI III 300 km'yi aşar → kesildiği işaretlenmeli
        radius, truncated = radius_for_mmi(7.8, 3.0, 10.0)
        assert truncated is True
        assert radius == IPE["max_distance_km"]

    def test_higher_intensity_smaller_radius(self):
        r7, _ = radius_for_mmi(7.5, 7.0, 10.0)
        r6, _ = radius_for_mmi(7.5, 6.0, 10.0)
        assert r7 < r6


class TestBands:

    def test_band_labels(self):
        assert mmi_band(9.5)[0] == "IX+"
        assert mmi_band(8.2)[0] == "VIII"
        assert mmi_band(6.1)[0] == "VI"
        assert mmi_band(1.5)[0] == "II"


class TestAssess:

    def test_kahramanmaras_scenario(self):
        r = assess(7.8, 37.288, 37.043, 8.6)
        assert r["max_mmi"] >= 7.5
        assert r["total_settlements"] > 50
        assert r["total_population"] > 1_000_000
        # Gaziantep bu senaryoda şiddetli sarsıntı bandında olmalı
        names = {s["name"] for s in r["settlements"]}
        assert "Gaziantep" in names

    def test_bands_are_nested(self):
        # Daha düşük şiddet bandı her zaman daha çok yerleşim içerir
        r = assess(7.0, 40.7, 29.9, 10.0)
        counts = [b["settlements"] for b in r["bands"]]
        assert counts == sorted(counts)

    def test_population_monotone_with_band(self):
        r = assess(7.0, 40.7, 29.9, 10.0)
        pops = [b["population"] for b in r["bands"]]
        assert pops == sorted(pops)

    def test_small_event_limited_impact(self):
        big = assess(7.5, 39.0, 35.0, 10.0)
        small = assess(4.5, 39.0, 35.0, 10.0)
        assert small["total_settlements"] < big["total_settlements"]

    def test_offshore_event_far_from_settlements(self):
        # Akdeniz açıkları, küçük deprem — kayda değer etki beklenmez
        r = assess(4.0, 35.2, 28.0, 10.0)
        assert r["total_settlements"] == 0 or r["max_mmi"] < 5.0

    def test_caveats_always_present(self):
        r = assess(6.0, 39.0, 35.0, 10.0)
        assert len(r["caveats"]) >= 4
        assert any("hasar" in c.lower() for c in r["caveats"])

    def test_settlements_sorted_by_intensity(self):
        r = assess(7.0, 40.7, 29.9, 10.0)
        mmis = [s["mmi"] for s in r["settlements"]]
        assert mmis == sorted(mmis, reverse=True)


class TestExposureData:

    def test_settlement_dataset_sane(self):
        df = settlements()
        assert len(df) > 500
        assert df["population"].sum() > 50_000_000
        assert df["latitude"].between(35, 43).all()
        assert df["longitude"].between(25, 45).all()

    def test_only_administrative_seats(self):
        # Çifte sayımı önleyen kural: köy/mahalle (PPL) kayıtları olmamalı
        assert set(settlements()["fcode"].unique()) <= {"PPLC", "PPLA", "PPLA2", "PPLA3"}

    def test_istanbul_population_reasonable(self):
        df = settlements()
        ist = df[df["name"] == "Istanbul"]["population"].max()
        assert 13_000_000 < ist < 18_000_000


class TestShelters:

    def test_nearby_shelters_within_radius(self):
        fc = nearby_shelters(41.0, 28.98, 25.0)
        assert fc["type"] == "FeatureCollection"
        for f in fc["features"]:
            assert f["properties"]["distance_km"] <= 25.0

    def test_shelters_sorted_by_distance(self):
        fc = nearby_shelters(41.0, 28.98, 40.0)
        d = [f["properties"]["distance_km"] for f in fc["features"]]
        assert d == sorted(d)

    def test_incompleteness_is_disclosed(self):
        fc = nearby_shelters(41.0, 28.98, 10.0)
        assert "EKSİK" in fc["properties"]["note"].upper()

    def test_remote_area_has_no_shelters(self):
        fc = nearby_shelters(38.0, 44.5, 5.0)
        assert fc["properties"]["count"] == 0
