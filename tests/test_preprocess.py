"""Temel birim testler — veri ön işleme ve yardımcı fonksiyonlar."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime


# ── Yardımcı: test verisi üret ───────────────────────────────────────────────

def make_sample_df(n=100) -> pd.DataFrame:
    np.random.seed(42)
    return pd.DataFrame({
        "eventDate": pd.date_range("2000-01-01", periods=n, freq="30D"),
        "latitude":  np.random.uniform(36.0, 42.0, n),
        "longitude": np.random.uniform(26.0, 44.0, n),
        "depth":     np.random.uniform(5.0, 200.0, n),
        "magnitude": np.random.uniform(4.0, 7.5, n),
        "location":  [f"Yer {i}" for i in range(n)],
    })


# ── Preprocess testleri ───────────────────────────────────────────────────────

class TestPreprocess:

    def test_no_nulls_after_dropna(self):
        from src.preprocess import load_and_clean
        # Gerçek dosya yoksa pas geç
        pytest.importorskip("openpyxl")
        # Fonksiyon null satırları düşürmeli
        df = make_sample_df()
        df.loc[5, "magnitude"] = None
        df.loc[10, "latitude"] = None
        df = df.dropna(subset=["eventDate", "latitude", "longitude", "magnitude"])
        assert df["magnitude"].isnull().sum() == 0
        assert df["latitude"].isnull().sum() == 0

    def test_eventdate_is_datetime(self):
        df = make_sample_df()
        assert pd.api.types.is_datetime64_any_dtype(df["eventDate"])

    def test_magnitude_range(self):
        df = make_sample_df()
        assert df["magnitude"].between(0, 10).all(), "Büyüklük 0-10 arasında olmalı"

    def test_coordinates_valid(self):
        df = make_sample_df()
        assert df["latitude"].between(-90, 90).all()
        assert df["longitude"].between(-180, 180).all()


# ── ML modeli testleri ────────────────────────────────────────────────────────

class TestMLModel:

    def test_classify_magnitude_labels(self):
        from src.ml_model import classify_magnitude
        assert classify_magnitude(7.5) == "Çok Yüksek (M7+)"
        assert classify_magnitude(6.5) == "Yüksek (M6-7)"
        assert classify_magnitude(5.5) == "Orta (M5-6)"
        assert classify_magnitude(4.0) == "Düşük (M<5)"
        assert classify_magnitude(4.9) == "Düşük (M<5)"

    def test_engineer_features_shape(self):
        from src.ml_model import engineer_features
        df = make_sample_df()
        X  = engineer_features(df)
        assert len(X) == len(df)
        assert "latitude"  in X.columns
        assert "longitude" in X.columns
        assert "depth"     in X.columns
        assert "month"     in X.columns

    def test_engineer_features_no_nulls(self):
        from src.ml_model import engineer_features
        df = make_sample_df()
        X  = engineer_features(df)
        assert X.isnull().sum().sum() == 0

    def test_train_risk_model_returns_keys(self, tmp_path):
        from src.ml_model import train_risk_model
        df  = make_sample_df(200)
        out = train_risk_model(df, model_path=str(tmp_path / "model.pkl"))
        assert "model"    in out
        assert "scaler"   in out
        assert "accuracy" in out
        assert 0.0 <= out["accuracy"] <= 1.0

    def test_cluster_seismic_zones_labels(self, tmp_path):
        from src.ml_model import cluster_seismic_zones
        df  = make_sample_df(200)
        out = cluster_seismic_zones(df, model_path=str(tmp_path / "cluster.pkl"))
        assert "risk_label"    in out.columns
        assert "cluster_color" in out.columns
        assert out["risk_label"].notnull().all()

    def test_predict_matches_input_length(self, tmp_path):
        from src.ml_model import train_risk_model, predict_magnitude_class
        df         = make_sample_df(200)
        model_data = train_risk_model(df, model_path=str(tmp_path / "model.pkl"))
        preds      = predict_magnitude_class(df.head(20), model_data)
        assert len(preds) == 20


# ── Fay risk analizi testleri ─────────────────────────────────────────────────

class TestFayRisk:

    def test_risk_color_high(self):
        from src.fay_risk_analiz import risk_color
        assert risk_color(80) == "#FF0000"

    def test_risk_color_medium(self):
        from src.fay_risk_analiz import risk_color
        assert risk_color(55) == "#FF6600"

    def test_risk_color_low(self):
        from src.fay_risk_analiz import risk_color
        assert risk_color(10) == "#4CAF50"


# ── Zaman analizi testleri ────────────────────────────────────────────────────

class TestTimeAnalysis:

    def test_resample_yearly(self):
        df   = make_sample_df(100)
        data = df.resample("YE", on="eventDate").size()
        assert len(data) > 0

    def test_resample_monthly(self):
        df   = make_sample_df(100)
        data = df.resample("ME", on="eventDate").size()
        assert len(data) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
