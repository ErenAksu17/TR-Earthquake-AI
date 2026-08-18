"""Veri boru hattı testleri — dedup, saat dilimi normalizasyonu, temizleme."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.pipeline import clean, deduplicate, to_utc_naive


def make_df(rows):
    df = pd.DataFrame(rows)
    df["eventDate"] = pd.to_datetime(df["eventDate"])
    return df


class TestDeduplicate:

    def test_exact_duplicate_removed(self):
        df = make_df([
            {"eventDate": "2023-02-06 01:17:34", "latitude": 37.2, "longitude": 37.0, "magnitude": 7.8},
            {"eventDate": "2023-02-06 01:17:34", "latitude": 37.2, "longitude": 37.0, "magnitude": 7.8},
        ])
        assert len(deduplicate(df)) == 1

    def test_cross_source_same_event_merged(self):
        # Aynı deprem: 8 sn orijin zamanı farkı, 5 km episantr farkı, 0.2 büyüklük farkı
        df = make_df([
            {"eventDate": "2023-02-06 01:17:34", "latitude": 37.20, "longitude": 37.00, "magnitude": 7.8, "provider": "kandilli"},
            {"eventDate": "2023-02-06 01:17:42", "latitude": 37.24, "longitude": 37.02, "magnitude": 7.6, "provider": "afad"},
        ])
        out = deduplicate(df)
        assert len(out) == 1
        assert out.iloc[0]["provider"] == "afad"  # öncelikli kaynak tutulur

    def test_real_aftershock_preserved_by_magnitude_guard(self):
        # 10 sn arayla, yakın konumda ama büyüklüğü çok farklı iki kayıt:
        # ana şok + erken artçı — İKİSİ DE kalmalı
        df = make_df([
            {"eventDate": "2023-02-06 01:17:34", "latitude": 37.2, "longitude": 37.0, "magnitude": 7.8},
            {"eventDate": "2023-02-06 01:17:44", "latitude": 37.3, "longitude": 37.1, "magnitude": 5.1},
        ])
        assert len(deduplicate(df)) == 2

    def test_distant_events_same_time_preserved(self):
        # Aynı anda ülkenin iki ucunda iki deprem — ikisi de kalmalı
        df = make_df([
            {"eventDate": "2024-01-01 12:00:00", "latitude": 36.0, "longitude": 26.0, "magnitude": 4.5},
            {"eventDate": "2024-01-01 12:00:05", "latitude": 41.0, "longitude": 43.0, "magnitude": 4.5},
        ])
        assert len(deduplicate(df)) == 2

    def test_time_window_respected(self):
        # 5 dakika arayla aynı yerde iki kayıt: ayrı depremler sayılır
        df = make_df([
            {"eventDate": "2024-01-01 12:00:00", "latitude": 39.0, "longitude": 35.0, "magnitude": 4.5},
            {"eventDate": "2024-01-01 12:05:00", "latitude": 39.0, "longitude": 35.0, "magnitude": 4.5},
        ])
        assert len(deduplicate(df)) == 2

    def test_microsecond_resolution_dates(self):
        # pandas 3.x Excel okumaları datetime64[us] dönebilir — pencere yine saniye olmalı
        df = make_df([
            {"eventDate": "2024-01-01 12:00:00", "latitude": 39.0, "longitude": 35.0, "magnitude": 4.5},
            {"eventDate": "2024-01-01 13:00:00", "latitude": 39.0, "longitude": 35.0, "magnitude": 4.5},
        ])
        df["eventDate"] = df["eventDate"].astype("datetime64[us]")
        assert len(deduplicate(df)) == 2

    def test_empty_frame(self):
        assert deduplicate(pd.DataFrame()).empty


class TestUTCNormalization:

    def test_kandilli_local_to_utc(self):
        # Europe/Istanbul (UTC+3) → UTC: 3 saat geri
        s = to_utc_naive(pd.Series(["2024-06-15 15:00:00"]), source_tz="Europe/Istanbul")
        assert s.iloc[0] == pd.Timestamp("2024-06-15 12:00:00")

    def test_utc_input_unchanged(self):
        s = to_utc_naive(pd.Series(["2024-06-15 12:00:00"]))
        assert s.iloc[0] == pd.Timestamp("2024-06-15 12:00:00")

    def test_tz_aware_input_converted(self):
        aware = pd.Series(pd.to_datetime(["2024-06-15 15:00:00"])).dt.tz_localize("Europe/Istanbul")
        s = to_utc_naive(aware)
        assert s.iloc[0] == pd.Timestamp("2024-06-15 12:00:00")
        assert s.dt.tz is None


class TestClean:

    def test_invalid_rows_dropped(self):
        df = pd.DataFrame({
            "eventDate": ["2024-01-01", "bozuk", "2024-01-03"],
            "latitude":  [39.0, 39.0, 999.0],       # 999 geçersiz
            "longitude": [35.0, 35.0, 35.0],
            "magnitude": [4.5, 4.5, 4.5],
            "depth":     [10.0, 10.0, 10.0],
        })
        out = clean(df)
        assert len(out) == 1

    def test_magnitude_bounds(self):
        df = pd.DataFrame({
            "eventDate": ["2024-01-01", "2024-01-02"],
            "latitude":  [39.0, 39.0],
            "longitude": [35.0, 35.0],
            "magnitude": [4.5, 99.0],               # 99 geçersiz
            "depth":     [10.0, 10.0],
        })
        assert len(clean(df)) == 1

    def test_negative_depth_clipped(self):
        df = pd.DataFrame({
            "eventDate": ["2024-01-01"],
            "latitude":  [39.0],
            "longitude": [35.0],
            "magnitude": [4.5],
            "depth":     [-5.0],
        })
        assert clean(df)["depth"].iloc[0] == 0
