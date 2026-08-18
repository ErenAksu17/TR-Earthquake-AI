"""Çoklu katalog karşılaştırma testleri — eşleştirme mantığı ve ağ mock'ları."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest

from src import catalog_compare as cc


def cat(rows, source="X"):
    """SCHEMA'ya uygun küçük katalog üret."""
    df = pd.DataFrame(rows)
    df["eventDate"] = pd.to_datetime(df["eventDate"])
    for col, default in (("depth", 10.0), ("mag_type", ""), ("location", ""), ("event_id", "")):
        if col not in df:
            df[col] = default
    df["source"] = source
    return df[cc.SCHEMA]


class TestMatching:

    def test_same_event_matched(self):
        # 2 sn ve 6 km farkla aynı deprem — eşleşmeli
        a = cat([{"eventDate": "2023-02-06 01:17:32", "latitude": 37.277, "longitude": 37.040,
                  "magnitude": 7.7, "mag_type": "MW"}], "AFAD")
        b = cat([{"eventDate": "2023-02-06 01:17:34", "latitude": 37.226, "longitude": 37.014,
                  "magnitude": 7.8, "mag_type": "mww"}], "USGS")
        m = cc.match_catalogs(a, b)
        assert len(m) == 1
        assert m.iloc[0]["dmag"] == pytest.approx(-0.1)
        assert m.iloc[0]["dt_s"] == 2.0
        assert 3 < m.iloc[0]["dist_km"] < 10

    def test_magnitude_difference_never_blocks_match(self):
        # Büyüklük farkı ölçüt olmamalı — 1.5 fark olsa da eşleşmeli
        a = cat([{"eventDate": "2024-01-01 00:00:00", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 4.0}])
        b = cat([{"eventDate": "2024-01-01 00:00:03", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 5.5}])
        m = cc.match_catalogs(a, b)
        assert len(m) == 1
        assert m.iloc[0]["dmag"] == pytest.approx(-1.5)

    def test_distant_events_not_matched(self):
        a = cat([{"eventDate": "2024-01-01 00:00:00", "latitude": 36.0, "longitude": 26.0,
                  "magnitude": 5.0}])
        b = cat([{"eventDate": "2024-01-01 00:00:05", "latitude": 41.0, "longitude": 43.0,
                  "magnitude": 5.0}])
        assert cc.match_catalogs(a, b).empty

    def test_time_gap_beyond_tolerance_not_matched(self):
        a = cat([{"eventDate": "2024-01-01 00:00:00", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 5.0}])
        b = cat([{"eventDate": "2024-01-01 00:10:00", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 5.0}])
        assert cc.match_catalogs(a, b).empty

    def test_one_to_one_no_double_matching(self):
        # Bir A olayına iki B adayı: yalnızca biri eşleşmeli
        a = cat([{"eventDate": "2024-01-01 00:00:00", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 5.0}])
        b = cat([
            {"eventDate": "2024-01-01 00:00:02", "latitude": 39.0, "longitude": 35.0, "magnitude": 5.0},
            {"eventDate": "2024-01-01 00:00:20", "latitude": 39.05, "longitude": 35.05, "magnitude": 4.8},
        ])
        m = cc.match_catalogs(a, b)
        assert len(m) == 1
        assert m.iloc[0]["dt_s"] == 2.0          # zamanca en yakın seçilir
        assert bool(m.iloc[0]["ambiguous"]) is True   # belirsizlik işaretlenir

    def test_unambiguous_match_not_flagged(self):
        a = cat([{"eventDate": "2024-01-01 00:00:00", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 5.0}])
        b = cat([{"eventDate": "2024-01-01 00:00:02", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 5.0}])
        assert bool(cc.match_catalogs(a, b).iloc[0]["ambiguous"]) is False

    def test_empty_inputs(self):
        a = cat([{"eventDate": "2024-01-01 00:00:00", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 5.0}])
        assert cc.match_catalogs(a, cc._empty()).empty
        assert cc.match_catalogs(cc._empty(), a).empty

    def test_multiple_events_matched_pairwise(self):
        rows_a = [{"eventDate": f"2024-01-0{i} 00:00:00", "latitude": 39.0 + i * 0.01,
                   "longitude": 35.0, "magnitude": 4.0 + i * 0.1} for i in range(1, 6)]
        rows_b = [{"eventDate": f"2024-01-0{i} 00:00:03", "latitude": 39.0 + i * 0.01,
                   "longitude": 35.0, "magnitude": 4.1 + i * 0.1} for i in range(1, 6)]
        m = cc.match_catalogs(cat(rows_a), cat(rows_b))
        assert len(m) == 5
        assert all(m["dmag"].round(2) == -0.1)


class TestCompareStats:

    def _pair(self):
        rows_a = [{"eventDate": f"2024-01-0{i} 00:00:00", "latitude": 39.0, "longitude": 35.0,
                   "magnitude": 5.0, "mag_type": "ML"} for i in range(1, 5)]
        rows_b = [{"eventDate": f"2024-01-0{i} 00:00:02", "latitude": 39.0, "longitude": 35.0,
                   "magnitude": 4.8, "mag_type": "mb"} for i in range(1, 5)]
        return cat(rows_a, "AFAD"), cat(rows_b, "USGS")

    def test_summary_counts_and_stats(self):
        a, b = self._pair()
        out = cc.compare_pair(a, b, "AFAD", "USGS")
        assert out["matched"] == 4
        assert out["only_a"] == 0 and out["only_b"] == 0
        assert out["stats"]["dmag_median"] == pytest.approx(0.2)

    def test_unmatched_counted(self):
        a, b = self._pair()
        extra = cat([{"eventDate": "2025-06-01 00:00:00", "latitude": 40.0, "longitude": 30.0,
                      "magnitude": 6.0}], "AFAD")
        out = cc.compare_pair(pd.concat([a, extra], ignore_index=True), b, "AFAD", "USGS")
        assert out["matched"] == 4
        assert out["only_a"] == 1

    def test_scale_pair_breakdown(self):
        a, b = self._pair()
        out = cc.compare_pair(a, b, "AFAD", "USGS")
        assert out["scale_pairs"][0]["pair"] == "ML / MB"
        assert out["scale_pairs"][0]["n"] == 4

    def test_no_matches_returns_null_stats(self):
        a = cat([{"eventDate": "2024-01-01 00:00:00", "latitude": 36.0, "longitude": 26.0,
                  "magnitude": 5.0}], "AFAD")
        b = cat([{"eventDate": "2025-01-01 00:00:00", "latitude": 41.0, "longitude": 43.0,
                  "magnitude": 5.0}], "USGS")
        out = cc.compare_pair(a, b, "AFAD", "USGS")
        assert out["matched"] == 0
        assert out["stats"] is None


class TestFetchersMocked:
    """Ağ katmanı mock'lanır — ayrıştırma ve UTC dönüşümü doğrulanır."""

    def test_afad_parsing_and_utc(self, monkeypatch):
        payload = [{
            "eventID": "725902", "date": "2023-02-06T01:17:32",
            "latitude": "37.27728", "longitude": "37.03996", "depth": "8.6",
            "magnitude": "7.7", "type": "MW", "location": "Pazarcık (Kahramanmaraş)",
        }]

        class R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return payload

        monkeypatch.setattr(cc.requests, "get", lambda *a, **k: R())
        df = cc.fetch_afad("2023-02-06", "2023-02-06", 7.0)
        assert len(df) == 1
        assert df.iloc[0]["eventDate"] == pd.Timestamp("2023-02-06 01:17:32")
        assert df.iloc[0]["mag_type"] == "MW"
        assert df.iloc[0]["source"] == "AFAD"

    def test_usgs_parsing(self, monkeypatch):
        payload = {"features": [{
            "id": "us6000jllz",
            "properties": {"time": 1675646254342, "mag": 7.8, "magType": "mww", "place": "Pazarcik"},
            "geometry": {"coordinates": [37.0143, 37.2256, 10.0]},
        }]}

        class R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return payload

        monkeypatch.setattr(cc.requests, "get", lambda *a, **k: R())
        df = cc.fetch_usgs("2023-02-06", "2023-02-06", 7.0)
        assert len(df) == 1
        assert df.iloc[0]["magnitude"] == 7.8
        assert df.iloc[0]["latitude"] == pytest.approx(37.2256)
        assert df.iloc[0]["mag_type"] == "mww"

    def test_network_failure_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise cc.requests.exceptions.ConnectionError("ağ yok")

        monkeypatch.setattr(cc.requests, "get", boom)
        assert cc.fetch_afad("2024-01-01", "2024-01-02").empty
        assert cc.fetch_usgs("2024-01-01", "2024-01-02").empty

    def test_compare_window_with_injected_fetchers(self):
        a = cat([{"eventDate": "2024-01-01 00:00:00", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 5.0, "mag_type": "ML"}], "AFAD")
        b = cat([{"eventDate": "2024-01-01 00:00:02", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 4.9, "mag_type": "mb"}], "USGS")
        fetchers = {"AFAD": lambda s, e, m: a, "USGS": lambda s, e, m: b}
        out = cc.compare_window("2024-01-01", "2024-01-02", 4.0, fetchers=fetchers)
        assert out["comparisons"][0]["matched"] == 1
        assert out["catalogs"][0]["mag_types"] == ["ML"]
        assert out["notes"] == []

    def test_empty_catalog_produces_coverage_note(self):
        a = cat([{"eventDate": "2024-01-01 00:00:00", "latitude": 39.0, "longitude": 35.0,
                  "magnitude": 3.0}], "AFAD")
        fetchers = {"AFAD": lambda s, e, m: a, "USGS": lambda s, e, m: cc._empty()}
        out = cc.compare_window("2024-01-01", "2024-01-02", 3.0, fetchers=fetchers)
        assert len(out["notes"]) == 1
        assert "M4.0" in out["notes"][0]

    def test_sample_pairs_sorted_by_magnitude(self):
        a = cat([
            {"eventDate": "2024-01-01 00:00:00", "latitude": 39.0, "longitude": 35.0, "magnitude": 4.2},
            {"eventDate": "2024-01-02 00:00:00", "latitude": 39.0, "longitude": 35.0, "magnitude": 6.1},
        ], "AFAD")
        b = cat([
            {"eventDate": "2024-01-01 00:00:02", "latitude": 39.0, "longitude": 35.0, "magnitude": 4.3},
            {"eventDate": "2024-01-02 00:00:02", "latitude": 39.0, "longitude": 35.0, "magnitude": 6.0},
        ], "USGS")
        fetchers = {"AFAD": lambda s, e, m: a, "USGS": lambda s, e, m: b}
        pairs = cc.sample_pairs("2024-01-01", "2024-01-03", 4.0, 10, fetchers=fetchers)
        assert len(pairs) == 2
        assert pairs[0]["mag_a"] == 6.1              # en büyük başta
        assert pairs[0]["time_a"].endswith("Z")      # UTC işaretli
