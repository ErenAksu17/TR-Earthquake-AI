"""Fay kaynak modeli, zemin etkisi ve senaryo motoru testleri."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from src.fault_sources import (
    load_fault_sources,
    poisson_probability,
    recurrence_years,
    rupture_magnitude,
    seismic_moment,
    wc1994_magnitude,
)
from src.scenario import predict_mmi_rrup, run_scenario
from src.site_effects import (
    mmi_site_delta,
    nehrp_class,
    pga_on_rock,
    site_amplification,
    vs30_at,
)


class TestScalingRelations:
    """Wells & Coppersmith (1994) ve moment dengesi."""

    def test_magnitude_grows_with_area(self):
        assert wc1994_magnitude(2000, 0.0) > wc1994_magnitude(200, 0.0)

    def test_known_area_magnitude(self):
        # 1000 km² doğrultu atımlı: 3.98 + 1.02*3 = 7.04
        assert wc1994_magnitude(1000, 0.0) == pytest.approx(7.04, abs=0.01)

    def test_faulting_style_changes_result(self):
        ss = wc1994_magnitude(1000, 0.0)      # doğrultu atımlı
        rev = wc1994_magnitude(1000, 90.0)    # ters
        nor = wc1994_magnitude(1000, -90.0)   # normal
        assert len({round(ss, 3), round(rev, 3), round(nor, 3)}) == 3

    def test_seismic_moment_scaling(self):
        # Bir büyüklük derecesi = 10^1.5 ≈ 31.6 kat moment
        assert seismic_moment(7.0) / seismic_moment(6.0) == pytest.approx(10 ** 1.5, rel=1e-6)

    def test_faster_slip_means_shorter_recurrence(self):
        fast = recurrence_years(1000, 20.0, 7.0)
        slow = recurrence_years(1000, 1.0, 7.0)
        assert fast < slow

    def test_recurrence_requires_slip(self):
        assert recurrence_years(1000, 0.0, 7.0) is None

    def test_poisson_probability_bounds(self):
        assert poisson_probability(50, 100) == pytest.approx(1 - np.exp(-0.5), abs=1e-9)
        assert poisson_probability(50, None) is None

    def test_partial_rupture_smaller_magnitude(self):
        full = rupture_magnitude(200, 15, 0.0)
        part = rupture_magnitude(50, 15, 0.0)
        assert part < full


class TestSiteEffects:

    def test_pga_decays_with_distance(self):
        vals = [float(pga_on_rock(7.0, d, 0.0)) for d in (0, 10, 50, 150)]
        assert vals == sorted(vals, reverse=True)

    def test_soft_soil_amplifies(self):
        # Yumuşak zemin, referans kayaya göre büyütür (uzak alan → doğrusal rejim)
        assert float(mmi_site_delta(250, 6.5, 80, 0.0)) > 0.2

    def test_rock_has_no_effect_at_reference(self):
        assert abs(float(mmi_site_delta(760, 7.0, 30, 0.0))) < 0.05

    def test_hard_rock_reduces_shaking(self):
        assert float(mmi_site_delta(1200, 7.0, 30, 0.0)) < 0

    def test_nonlinearity_near_fault(self):
        # Yumuşak zemin kuvvetli sarsıntıda doyar: yakında büyütme daha AZ olur
        near = float(mmi_site_delta(200, 7.5, 5, 0.0))
        far = float(mmi_site_delta(200, 7.5, 120, 0.0))
        assert near < far

    def test_amplification_is_finite(self):
        out = site_amplification(np.array([180.0, 400.0, 900.0]), np.array([0.3, 0.3, 0.3]))
        assert np.all(np.isfinite(out))

    def test_nehrp_classes(self):
        assert nehrp_class(1600)[0] == "A"
        assert nehrp_class(800)[0] == "B"
        assert nehrp_class(400)[0] == "C"
        assert nehrp_class(200)[0] == "D"
        assert nehrp_class(120)[0] == "E"

    def test_vs30_grid_lookup(self):
        # Adapazarı yumuşak zemindedir (1999'da ağır hasar görmüştü)
        soft = float(vs30_at(40.78, 30.40)[0])
        assert 100 < soft < 400

    def test_vs30_outside_grid_falls_back(self):
        assert float(vs30_at(5.0, 5.0)[0]) > 0


class TestRrupIPE:

    def test_mmi_decays_with_distance(self):
        vals = [float(predict_mmi_rrup(7.0, d)) for d in (0, 20, 80, 200)]
        assert vals == sorted(vals, reverse=True)

    def test_mmi_grows_with_magnitude(self):
        vals = [float(predict_mmi_rrup(m, 30)) for m in (5.0, 6.0, 7.0, 8.0)]
        assert vals == sorted(vals)

    def test_epicentral_intensity_plausible(self):
        assert 7.5 <= float(predict_mmi_rrup(7.5, 0)) <= 9.5


class TestFaultSources:

    def test_catalog_loads(self):
        g = load_fault_sources()
        assert len(g) > 100
        assert {"fault_id", "label", "mmax", "slip_rate"} <= set(g.columns)

    def test_all_above_threshold(self):
        assert (load_fault_sources()["mmax"] >= 6.5).all()

    def test_no_non_crustal_sources(self):
        types = load_fault_sources()["slip_type"].astype(str)
        assert not types.str.contains("Subduction|Spreading", case=False).any()

    def test_probabilities_are_valid(self):
        g = load_fault_sources()
        p = g["p50"].dropna()
        assert ((p >= 0) & (p <= 1)).all()


@pytest.fixture(scope="module")
def any_fault():
    return load_fault_sources().nlargest(1, "p50").iloc[0]["fault_id"]


class TestScenario:

    def test_scenario_runs(self, any_fault):
        r = run_scenario(any_fault, 1.0)
        assert r["rupture"]["magnitude"] > 5.0
        assert r["total_settlements"] > 0
        assert len(r["caveats"]) >= 4

    def test_partial_rupture_is_smaller(self, any_fault):
        full = run_scenario(any_fault, 1.0)
        part = run_scenario(any_fault, 0.3)
        assert part["rupture"]["magnitude"] < full["rupture"]["magnitude"]
        assert part["rupture"]["length_km"] < full["rupture"]["length_km"]

    def test_site_effect_reported_separately(self, any_fault):
        r = run_scenario(any_fault, 1.0)
        for s in r["settlements"][:20]:
            assert s["delta"] == pytest.approx(s["mmi"] - s["mmi_rock"], abs=0.02)
            assert s["vs30"] > 0

    def test_bands_nested(self, any_fault):
        r = run_scenario(any_fault, 1.0)
        counts = [b["settlements"] for b in r["bands"]]
        assert counts == sorted(counts)

    def test_unknown_fault_raises(self):
        with pytest.raises(KeyError):
            run_scenario("YOK-9999")

    def test_rupture_geometry_returned(self, any_fault):
        r = run_scenario(any_fault, 1.0)
        assert len(r["rupture"]["geometry"]) >= 2
