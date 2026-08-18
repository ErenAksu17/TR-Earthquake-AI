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
