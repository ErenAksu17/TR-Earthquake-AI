"""
ML Modül — Sismik Risk Analizi
- K-Means: Sismik zon kümeleme (risk bölgeleri)
- Random Forest: Büyüklük sınıflandırması
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score
import joblib
import os
import logging

from src.config import ML, PATHS

log = logging.getLogger(__name__)


# ── Büyüklük sınıfı ──────────────────────────────────────────────────────────

MAGNITUDE_LABELS = {
    "Düşük (M<5)":          0,
    "Orta (M5-6)":          1,
    "Yüksek (M6-7)":        2,
    "Çok Yüksek (M7+)":     3,
}

LABEL_COLORS = {
    "Düşük (M<5)":      "#3399FF",
    "Orta (M5-6)":      "#FFAA00",
    "Yüksek (M6-7)":    "#FF6600",
    "Çok Yüksek (M7+)": "#FF0000",
}


def classify_magnitude(mag: float) -> str:
    if mag >= 7.0:   return "Çok Yüksek (M7+)"
    elif mag >= 6.0: return "Yüksek (M6-7)"
    elif mag >= 5.0: return "Orta (M5-6)"
    else:            return "Düşük (M<5)"


# ── Feature engineering ───────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Ham deprem verisinden ML özellikleri üret."""
    X = df[["latitude", "longitude", "depth"]].copy()

    dates = pd.to_datetime(df["eventDate"], errors="coerce")
    X["month"]       = dates.dt.month.fillna(0).astype(int)
    X["day_of_year"] = dates.dt.dayofyear.fillna(0).astype(int)
    X["year"]        = dates.dt.year.fillna(0).astype(int)

    # Türkiye merkezine uzaklık (kaba bir özellik)
    X["dist_to_center"] = np.sqrt((df["latitude"] - 39.0) ** 2 + (df["longitude"] - 35.0) ** 2)

    return X.fillna(0)


# ── Random Forest: büyüklük sınıflandırması ───────────────────────────────────

def train_risk_model(
    df: pd.DataFrame,
    model_path: str = None,
) -> dict:
    """
    RandomForest eğitir ve sonuçları döndürür.
    Returns: {"model", "scaler", "features", "report", "accuracy", "cv_scores"}
    """
    model_path = model_path or PATHS["risk_model"]

    X = engineer_features(df)
    y = df["magnitude"].apply(classify_magnitude)

    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y,
        test_size=ML["test_size"],
        random_state=ML["random_state"],
        stratify=y,
    )

    model = RandomForestClassifier(
        n_estimators=ML["rf_estimators"],
        random_state=ML["random_state"],
        n_jobs=-1,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)

    y_pred    = model.predict(X_test)
    accuracy  = accuracy_score(y_test, y_pred)
    report    = classification_report(y_test, y_pred, output_dict=True)
    cv_scores = cross_val_score(model, X_scaled, y, cv=5, scoring="accuracy")

    # Kaydet
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(
        {"model": model, "scaler": scaler, "features": list(X.columns)},
        model_path,
    )
    log.info("✅ RF modeli kaydedildi (accuracy=%.3f): %s", accuracy, model_path)

    return {
        "model":     model,
        "scaler":    scaler,
        "features":  list(X.columns),
        "report":    report,
        "accuracy":  accuracy,
        "cv_scores": cv_scores,
    }


def load_risk_model(model_path: str = None) -> dict | None:
    model_path = model_path or PATHS["risk_model"]
    if os.path.exists(model_path):
        return joblib.load(model_path)
    return None


def predict_magnitude_class(df: pd.DataFrame, model_data: dict) -> np.ndarray:
    """Verilen DataFrame için büyüklük sınıfı tahmin et."""
    X       = engineer_features(df)
    X_scaled = model_data["scaler"].transform(X)
    return model_data["model"].predict(X_scaled)


def predict_proba(df: pd.DataFrame, model_data: dict) -> np.ndarray:
    """Sınıf olasılıklarını döndür."""
    X        = engineer_features(df)
    X_scaled = model_data["scaler"].transform(X)
    return model_data["model"].predict_proba(X_scaled)


def get_feature_importance(model_data: dict) -> pd.DataFrame:
    """Feature importance DataFrame'i döndür."""
    importances = model_data["model"].feature_importances_
    features    = model_data["features"]
    return (
        pd.DataFrame({"Özellik": features, "Önem": importances})
        .sort_values("Önem", ascending=False)
        .reset_index(drop=True)
    )


# ── K-Means: Sismik zon kümeleme ─────────────────────────────────────────────

CLUSTER_RISK_NAMES = ["Çok Yüksek Risk", "Yüksek Risk", "Orta Risk", "Düşük Risk", "Çok Düşük Risk"]
CLUSTER_COLORS     = ["#FF0000", "#FF6600", "#FFAA00", "#66BB00", "#3399FF"]


def cluster_seismic_zones(
    df: pd.DataFrame,
    n_clusters: int = None,
    model_path: str = None,
) -> pd.DataFrame:
    """
    K-Means kümeleme → risk zonu etiketleri.
    Küme isimleri ortalama büyüklüğe göre sıralanır (yüksek = daha riskli).
    Returns: df kopyası + 'cluster_id', 'risk_label', 'cluster_color' sütunları
    """
    n_clusters = n_clusters or ML["n_clusters"]
    model_path = model_path or PATHS["cluster_model"]

    X = df[["latitude", "longitude"]].copy()
    X["magnitude_w"] = df["magnitude"] ** 2   # büyük depremler daha ağırlıklı

    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=n_clusters, random_state=ML["random_state"], n_init=10)
    labels = kmeans.fit_predict(X_scaled)

    # Her kümenin ortalama büyüklüğüne göre risk sırala
    df_out           = df.copy()
    df_out["_cluster"] = labels
    cluster_avg_mag  = df_out.groupby("_cluster")["magnitude"].mean().sort_values(ascending=False)
    rank_map         = {cid: i for i, cid in enumerate(cluster_avg_mag.index)}

    df_out["cluster_id"]    = df_out["_cluster"].map(rank_map)
    df_out["risk_label"]    = df_out["cluster_id"].map(lambda i: CLUSTER_RISK_NAMES[min(i, len(CLUSTER_RISK_NAMES)-1)])
    df_out["cluster_color"] = df_out["cluster_id"].map(lambda i: CLUSTER_COLORS[min(i, len(CLUSTER_COLORS)-1)])
    df_out.drop(columns=["_cluster"], inplace=True)

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump({"kmeans": kmeans, "scaler": scaler, "n_clusters": n_clusters}, model_path)
    log.info("✅ Küme modeli kaydedildi: %s", model_path)

    return df_out


def load_cluster_model(model_path: str = None) -> dict | None:
    model_path = model_path or PATHS["cluster_model"]
    if os.path.exists(model_path):
        return joblib.load(model_path)
    return None


def apply_cluster_labels(df: pd.DataFrame, cluster_data: dict) -> pd.DataFrame:
    """Kayıtlı küme modelini mevcut DataFrame'e uygula."""
    X = df[["latitude", "longitude"]].copy()
    X["magnitude_w"] = df["magnitude"] ** 2
    X_scaled = cluster_data["scaler"].transform(X)
    labels   = cluster_data["kmeans"].predict(X_scaled)

    df_out = df.copy()
    df_out["cluster_id"]    = labels
    df_out["risk_label"]    = df_out["cluster_id"].map(lambda i: CLUSTER_RISK_NAMES[min(i, len(CLUSTER_RISK_NAMES)-1)])
    df_out["cluster_color"] = df_out["cluster_id"].map(lambda i: CLUSTER_COLORS[min(i, len(CLUSTER_COLORS)-1)])
    return df_out


# ── CLI çalıştırma ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    df = pd.read_excel(PATHS["merged"])
    df["eventDate"] = pd.to_datetime(df["eventDate"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude", "magnitude", "eventDate"])

    print("📊 RF Modeli eğitiliyor...")
    result = train_risk_model(df)
    print(f"   Doğruluk: {result['accuracy']:.3f}")
    print(f"   CV Ortalama: {result['cv_scores'].mean():.3f} ± {result['cv_scores'].std():.3f}")

    print("\n🗺️  Sismik zonlar hesaplanıyor...")
    df_c = cluster_seismic_zones(df)
    print(df_c["risk_label"].value_counts())
