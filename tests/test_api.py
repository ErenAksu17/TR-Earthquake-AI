"""FastAPI uç testleri — canlı kaynak mock'lanır, arşiv gerçek katalogla çalışır."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def fake_live(monkeypatch):
    df = pd.DataFrame({
        "eventDate":  pd.to_datetime(["2024-06-15 12:00:00", "2024-06-15 11:30:00"]),
        "latitude":   [39.0, 38.5],
        "longitude":  [35.0, 27.0],
        "depth":      [10.0, 7.0],
        "magnitude":  [4.2, 3.1],
        "location":   ["Test Merkez", "Ege Denizi"],
        "city":       ["Kayseri", "İzmir"],
        "provider":   ["kandilli", "kandilli"],
    })
    monkeypatch.setattr(main, "get_live", lambda source: df)
    main._live_cache.clear()
    yield df
    main._live_cache.clear()


class TestLive:

    def test_live_returns_utc_iso(self, client, fake_live):
        r = client.get("/api/live?source=kandilli")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert body["quakes"][0]["eventDate"].endswith("Z")

    def test_live_min_mag_filter(self, client, fake_live):
        r = client.get("/api/live?source=kandilli&min_mag=4")
        assert r.json()["count"] == 1

    def test_live_bad_source_rejected(self, client):
        assert client.get("/api/live?source=hacker").status_code == 422

    def test_live_unavailable_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(main, "get_live", lambda source: pd.DataFrame())
        main._live_cache.clear()
        assert client.get("/api/live?source=kandilli").status_code == 503
        main._live_cache.clear()


class TestArchive:

    def test_quakes_filtering(self, client):
        r = client.get("/api/quakes?min_mag=7&limit=100")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] > 0
        assert all(q["magnitude"] >= 7 for q in body["quakes"])

    def test_quakes_date_range(self, client):
        r = client.get("/api/quakes?start=2023-01-01&end=2023-12-31&limit=10000")
        body = r.json()
        assert body["total"] > 0
        assert all(q["eventDate"].startswith("2023") for q in body["quakes"])

    def test_quakes_csv_export(self, client):
        r = client.get("/api/quakes?min_mag=7.5&format=csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "eventDate" in r.text

    def test_stats_shape(self, client):
        r = client.get("/api/stats?min_mag=5")
        body = r.json()
        assert body["total"] > 0
        assert len(body["yearly"]["years"]) == len(body["yearly"]["counts"])
        assert sum(body["mag_hist"]["counts"]) <= body["total"]

    def test_faults_geojson(self, client):
        r = client.get("/api/faults")
        assert r.status_code == 200
        assert r.json()["type"] == "FeatureCollection"

    def test_index_served(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "TR Earthquake AI" in r.text


class TestSeismology:

    def test_gr_analysis(self, client):
        r = client.get("/api/analysis/gr?start=1990-01-01")
        assert r.status_code == 200
        body = r.json()
        assert body["mc"] is not None
        assert body["fit"] is not None
        assert 0.4 < body["fit"]["b"] < 2.0            # makul sismolojik aralık
        assert len(body["curve"]["mags"]) == len(body["curve"]["counts"])

    def test_gr_declustered_has_fewer_events(self, client):
        full = client.get("/api/analysis/gr?start=1990-01-01").json()
        decl = client.get("/api/analysis/gr?start=1990-01-01&declustered=true").json()
        assert decl["n_total"] < full["n_total"]

    def test_gr_too_narrow_returns_400(self, client):
        assert client.get("/api/analysis/gr?min_mag=7.8").status_code == 400

    def test_decluster_summary(self, client):
        d = client.get("/api/analysis/decluster").json()
        assert d["mainshocks"] + d["aftershocks"] == d["total"]
        assert 0 < d["aftershock_pct"] < 100

    def test_bmap_cells(self, client):
        d = client.get("/api/analysis/bmap").json()
        assert d["count"] > 0
        for c in d["cells"]:
            assert 0.2 < c["b"] < 2.5
            assert c["n"] >= 30

    def test_mainshock_candidates(self, client):
        d = client.get("/api/analysis/mainshocks?min_mag=6.5").json()
        assert len(d["mainshocks"]) > 0
        assert all(m["magnitude"] >= 6.5 for m in d["mainshocks"])
        mags = [m["magnitude"] for m in d["mainshocks"]]
        assert mags == sorted(mags, reverse=True)     # en büyükten küçüğe

    def test_aftershock_forecast_kahramanmaras(self, client):
        # 2023-02-06 M7.8 dizisi katalogda mevcut — uçtan uca gerçek veri testi
        r = client.get("/api/analysis/aftershock",
                       params={"time": "2023-02-06T01:17:34Z", "lat": 37.29, "lon": 37.04, "mag": 7.8})
        assert r.status_code == 200
        body = r.json()
        assert body["sequence_events"] > 50
        if body["forecast"]:
            assert all(0.0 <= f["probability"] <= 1.0 for f in body["forecast"])


class TestCompareEndpoint:
    """Karşılaştırma ucu — ağ katmanı mock'lanır (CI'da dış API'ye gidilmez)."""

    @pytest.fixture()
    def fake_sources(self, monkeypatch):
        import pandas as pd

        from src import catalog_compare as cc

        def mk(mag, mtype, offset_s, source):
            df = pd.DataFrame([{
                "source": source, "event_id": "1",
                "eventDate": pd.Timestamp("2024-05-01 12:00:00") + pd.Timedelta(seconds=offset_s),
                "latitude": 39.0, "longitude": 35.0, "depth": 10.0,
                "magnitude": mag, "mag_type": mtype, "location": "Test",
            }])
            return df[cc.SCHEMA]

        monkeypatch.setattr(main, "compare_window",
                            lambda s, e, m: cc.compare_window(s, e, m, fetchers={
                                "AFAD": lambda *a: mk(5.0, "ML", 0, "AFAD"),
                                "USGS": lambda *a: mk(4.8, "mb", 3, "USGS"),
                            }))
        monkeypatch.setattr(main, "sample_pairs",
                            lambda s, e, m, n: cc.sample_pairs(s, e, m, n, fetchers={
                                "AFAD": lambda *a: mk(5.0, "ML", 0, "AFAD"),
                                "USGS": lambda *a: mk(4.8, "mb", 3, "USGS"),
                            }))
        main._compare_cache.clear()
        yield
        main._compare_cache.clear()

    def test_compare_returns_matched_pair(self, client, fake_sources):
        r = client.get("/api/compare?start=2024-05-01&end=2024-05-02&min_mag=4.0")
        assert r.status_code == 200
        body = r.json()
        cmp = body["comparisons"][0]
        assert cmp["matched"] == 1
        assert cmp["stats"]["dmag_median"] == pytest.approx(0.2)
        assert body["pairs"][0]["magtype_a"] == "ML"

    def test_compare_result_is_cached(self, client, fake_sources):
        client.get("/api/compare?start=2024-05-01&end=2024-05-02&min_mag=4.0")
        assert len(main._compare_cache) == 1

    def test_compare_rejects_bad_magnitude(self, client):
        assert client.get("/api/compare?start=2024-01-01&end=2024-01-02&min_mag=99").status_code == 422

    def test_compare_source_failure_returns_502(self, client, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("kaynak yok")

        monkeypatch.setattr(main, "compare_window", boom)
        main._compare_cache.clear()
        assert client.get("/api/compare?start=2024-01-01&end=2024-01-02").status_code == 502
        main._compare_cache.clear()


class TestImpactEndpoints:

    def test_impact_scenario(self, client):
        r = client.get("/api/impact", params={"mag": 7.5, "lat": 40.75, "lon": 29.9, "depth": 10})
        assert r.status_code == 200
        b = r.json()
        assert b["max_mmi"] > 6.0
        assert b["total_settlements"] > 0
        assert len(b["caveats"]) >= 4

    def test_impact_bands_nested(self, client):
        b = client.get("/api/impact", params={"mag": 7.0, "lat": 39.0, "lon": 35.0}).json()
        counts = [x["settlements"] for x in b["bands"]]
        assert counts == sorted(counts)

    def test_impact_rejects_out_of_range_magnitude(self, client):
        assert client.get("/api/impact", params={"mag": 12, "lat": 39, "lon": 35}).status_code == 422

    def test_impact_requires_coordinates(self, client):
        assert client.get("/api/impact", params={"mag": 6.0}).status_code == 422

    def test_shelters_within_radius(self, client):
        r = client.get("/api/shelters", params={"lat": 41.0, "lon": 28.98, "radius_km": 20})
        assert r.status_code == 200
        fc = r.json()
        assert fc["type"] == "FeatureCollection"
        assert "EKSİK" in fc["properties"]["note"].upper()

    def test_shelters_rejects_bad_radius(self, client):
        assert client.get("/api/shelters",
                          params={"lat": 41.0, "lon": 28.98, "radius_km": 0}).status_code == 422


class TestValidationEndpoints:

    def test_intensity_validation(self, client):
        r = client.get("/api/validation/intensity")
        assert r.status_code == 200
        b = r.json()
        assert b["overall"]["observations"] > 100
        assert abs(b["overall"]["bias"]) < 0.5
        assert len(b["caveats"]) >= 3

    def test_intensity_validation_filter(self, client):
        loose = client.get("/api/validation/intensity?min_responses=1").json()
        strict = client.get("/api/validation/intensity?min_responses=10").json()
        assert strict["overall"]["observations"] < loose["overall"]["observations"]

    def test_intensity_rejects_bad_filter(self, client):
        assert client.get("/api/validation/intensity?min_responses=0").status_code == 422

    def test_aftershock_validation(self, client):
        r = client.get("/api/validation/aftershock")
        assert r.status_code == 200
        b = r.json()
        assert b["tested"] + b["skipped_insufficient_data"] == b["candidates"]
        for s in b["sequences"]:
            assert s["expected"] >= 0
            assert isinstance(s["observed"], int)

    def test_aftershock_rejects_bad_window(self, client):
        assert client.get("/api/validation/aftershock?learn_days=0").status_code == 422


class TestCatalogCompleteness:

    def test_completeness_eras(self, client):
        r = client.get("/api/catalog/completeness")
        assert r.status_code == 200
        b = r.json()
        assert len(b["eras"]) == 2
        assert sum(e["records"] for e in b["eras"]) == b["total"]
        # Modern dönem daha düşük eşikte ve daha çok kayıt içermeli
        historic, modern = b["eras"]
        assert modern["nominal_min_mag"] < historic["nominal_min_mag"]
        assert "karşılaştırılamaz" in b["warning"]
