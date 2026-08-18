"""
Etki analizi — bir deprem hangi yerleşimde ne şiddette hissedilir?

Yöntem: Allen, Wald & Worden (2012) makrosismik şiddet denklemi (IPE),
hipomerkez uzaklığı (Rhyp) varyantı:

    r_m  = m1 + m2·e^(M−5)
    MMI  = c0 + c1·M + c2·ln√(Rhyp² + r_m²)          (Rhyp ≤ 50 km)
    MMI += c4·ln(Rhyp/50)                             (Rhyp > 50 km, anelastik)
    σ    = s1 + s2 / (1 + (Rhyp/s3)²)

Bilinçli sınırlar — bunlar gizlenmemeli:
- NOKTA KAYNAK varsayımı. Büyük depremlerde fay onlarca km uzanır; bu model
  tek noktadan yayılım varsayar. DYFI gözlemlerine karşı ÖLÇÜLEN sapma
  (bkz. src/validation.py): genel sapma -0,01 MMI (yansız), MAE 0,83;
  ancak M≥6,5 olaylarda ortalama 0,45 derece FAZLA tahmin.
- ZEMİN ETKİSİ YOK. Alüvyon zeminlerde sarsıntı 1-2 MMI derece artabilir;
  bu model kaya/ortalama zemin için medyan değer verir.
- Bu bir HASAR tahmini değildir. Hasar; yapı stoku, yönetmelik ve zemine
  bağlıdır ve burada modellenmez.
- Nüfus verisi kaba mertebedir (bkz. prepare_exposure.py, il düzeyinde ±%30).
"""

import functools
import json
import logging
import os

import numpy as np
import pandas as pd

from src.config import EXPOSURE, IPE, PATHS

log = logging.getLogger(__name__)

# EMS-98 / MMI derecelerinin kabaca karşılığı (sunum için)
MMI_BANDS = [
    (9.0, "IX+", "Yıkıcı", "#67000d"),
    (8.0, "VIII", "Çok şiddetli", "#a50f15"),
    (7.0, "VII", "Şiddetli", "#ef3b2c"),
    (6.0, "VI", "Kuvvetli", "#fd8d3c"),
    (5.0, "V", "Orta", "#fecc5c"),
    (4.0, "IV", "Hafif", "#c7e9b4"),
    (3.0, "III", "Zayıf", "#7fcdbb"),
]
MIN_REPORTED_MMI = 3.0


def mmi_band(mmi: float) -> tuple[str, str, str]:
    """MMI değerini (roman rakamı, açıklama, renk) üçlüsüne çevirir."""
    for threshold, roman, label, color in MMI_BANDS:
        if mmi >= threshold:
            return roman, label, color
    return "II", "Hissedilmez", "#deebf7"


def hypocentral_distance_km(epi_lat, epi_lon, depth_km, lat, lon):
    """Hiposantr uzaklığı: yüzey mesafesi ile odak derinliğinin bileşkesi."""
    r = 6371.0
    p1, l1, p2, l2 = map(np.radians, (epi_lat, epi_lon, lat, lon))
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin((l2 - l1) / 2) ** 2
    surface = 2 * r * np.arcsin(np.sqrt(a))
    return np.sqrt(surface ** 2 + float(depth_km) ** 2)


def predict_mmi(magnitude: float, rhyp_km) -> np.ndarray:
    """Allen, Wald & Worden (2012) Rhyp varyantı — medyan MMI."""
    rhyp = np.asarray(rhyp_km, dtype=float)
    r_m = IPE["m1"] + IPE["m2"] * np.exp(magnitude - 5.0)
    mmi = (IPE["c0"] + IPE["c1"] * magnitude
           + IPE["c2"] * np.log(np.sqrt(rhyp ** 2 + r_m ** 2)))
    far = rhyp > IPE["anelastic_from_km"]
    mmi = np.where(far, mmi + IPE["c4"] * np.log(np.maximum(rhyp, 1e-9) / IPE["anelastic_from_km"]), mmi)
    return np.clip(mmi, 1.0, 12.0)


def mmi_sigma(rhyp_km) -> np.ndarray:
    """Tahminin standart sapması (uzaklığa bağlı)."""
    rhyp = np.asarray(rhyp_km, dtype=float)
    return IPE["s1"] + IPE["s2"] / (1.0 + (rhyp / IPE["s3"]) ** 2)


def radius_for_mmi(magnitude: float, target_mmi: float,
                   depth_km: float = 10.0) -> tuple[float | None, bool]:
    """Verilen MMI'nin görüldüğü yaklaşık yüzey yarıçapı.

    Döner: (yarıçap_km, model_sınırını_aşıyor_mu)
      - (None, False): bu şiddet episantrda bile oluşmuyor
      - (r, False)   : şiddet r km'de sona eriyor
      - (max, True)  : şiddet denklemin geçerli olduğu 300 km'yi aşıyor
    """
    if float(predict_mmi(magnitude, depth_km)) < target_mmi:
        return None, False
    for surface_km in np.arange(0.0, IPE["max_distance_km"] + 2.0, 2.0):
        rhyp = np.sqrt(surface_km ** 2 + depth_km ** 2)
        if float(predict_mmi(magnitude, rhyp)) < target_mmi:
            return float(surface_km), False
    return float(IPE["max_distance_km"]), True


@functools.lru_cache(maxsize=1)
def settlements() -> pd.DataFrame:
    """İdari merkez yerleşimleri (GeoNames)."""
    path = PATHS["settlements"]
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Yerleşim verisi yok: {path}. 'python -m src.prepare_exposure' çalıştırın.")
    return pd.read_parquet(path)


@functools.lru_cache(maxsize=1)
def shelters() -> dict:
    """Toplanma alanları (OSM, eksik topluluk verisi)."""
    path = PATHS["shelters"]
    if not os.path.exists(path):
        return {"type": "FeatureCollection", "features": [],
                "properties": {"count": 0, "note": "Veri dosyası yok."}}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def assess(magnitude: float, lat: float, lon: float, depth_km: float = 10.0,
           min_mmi: float = MIN_REPORTED_MMI, limit: int = 300) -> dict:
    """Bir deprem (gerçek ya da senaryo) için yerleşim bazlı etki analizi."""
    df = settlements().copy()
    df["rhyp_km"] = hypocentral_distance_km(lat, lon, depth_km,
                                            df["latitude"].to_numpy(), df["longitude"].to_numpy())
    df = df[df["rhyp_km"] <= IPE["max_distance_km"]]

    if df.empty:
        return _empty_result(magnitude, lat, lon, depth_km)

    df["mmi"] = predict_mmi(magnitude, df["rhyp_km"].to_numpy())
    df["sigma"] = mmi_sigma(df["rhyp_km"].to_numpy())
    df = df[df["mmi"] >= min_mmi].sort_values("mmi", ascending=False)

    if df.empty:
        return _empty_result(magnitude, lat, lon, depth_km)

    bands = []
    for threshold, roman, label, color in MMI_BANDS:
        sel = df[df["mmi"] >= threshold]
        if sel.empty:
            continue
        radius, truncated = radius_for_mmi(magnitude, threshold, depth_km)
        bands.append({
            "mmi_min": threshold, "roman": roman, "label": label, "color": color,
            "settlements": int(len(sel)),
            "population": int(sel["population"].sum()),
            "radius_km": radius,
            "beyond_model_range": truncated,
        })

    top = df.head(limit)
    return {
        "event": {"magnitude": float(magnitude), "lat": float(lat), "lon": float(lon),
                  "depth_km": float(depth_km)},
        "max_mmi": round(float(df["mmi"].max()), 2),
        "total_settlements": int(len(df)),
        "total_population": int(df["population"].sum()),
        "bands": bands,
        "settlements": [{
            "name": r["name"],
            "lat": float(r["latitude"]), "lon": float(r["longitude"]),
            "population": int(r["population"]),
            "distance_km": round(float(r["rhyp_km"]), 1),
            "mmi": round(float(r["mmi"]), 2),
            "sigma": round(float(r["sigma"]), 2),
            "roman": mmi_band(r["mmi"])[0],
        } for _, r in top.iterrows()],
        "caveats": [
            "Nokta kaynak varsayımı — büyük depremlerde fay onlarca km uzanır, "
            "bu model ise tek noktadan yayılım varsayar.",
            "ÖLÇÜLDÜ (Doğrulama sekmesi, 1.387 DYFI gözlemi): model genelde "
            "yansızdır (sapma -0,01 MMI, MAE 0,83) ancak M≥6,5 olaylarda şiddeti "
            "ortalama 0,45 derece FAZLA tahmin eder; küçük olaylarda ~0,2 derece az.",
            "Zemin büyütmesi modellenmez; alüvyon zeminlerde şiddet 1-2 derece artabilir.",
            "Bu bir hasar veya can kaybı tahmini DEĞİLDİR.",
            f"Denklem {IPE['max_distance_km']:.0f} km'ye kadar geçerlidir; "
            "bu uzaklığı aşan düşük şiddet bantları kesilmiştir.",
            f"Nüfus verisi kaba mertebedir (il düzeyinde ölçülen sapma "
            f"{EXPOSURE['province_error_low']:+.0%} ile {EXPOSURE['province_error_high']:+.0%}). "
            f"{EXPOSURE['coverage_note']}",
        ],
    }


def _empty_result(magnitude, lat, lon, depth_km) -> dict:
    return {
        "event": {"magnitude": float(magnitude), "lat": float(lat), "lon": float(lon),
                  "depth_km": float(depth_km)},
        "max_mmi": None, "total_settlements": 0, "total_population": 0,
        "bands": [], "settlements": [],
        "caveats": ["Bu büyüklük ve konumda kayda değer şiddet beklenen yerleşim yok."],
    }


def nearby_shelters(lat: float, lon: float, radius_km: float = 30.0, limit: int = 500) -> dict:
    """Verilen noktanın çevresindeki toplanma alanları (GeoJSON)."""
    fc = shelters()
    feats = []
    for f in fc.get("features", []):
        flon, flat = f["geometry"]["coordinates"]
        d = hypocentral_distance_km(lat, lon, 0.0, flat, flon)
        if d <= radius_km:
            g = dict(f)
            g["properties"] = {**f["properties"], "distance_km": round(float(d), 1)}
            feats.append(g)
    feats.sort(key=lambda x: x["properties"]["distance_km"])
    return {
        "type": "FeatureCollection",
        "properties": {
            "count": len(feats),
            "total_in_dataset": fc.get("properties", {}).get("count", 0),
            "source": "OpenStreetMap (ODbL)",
            "note": "Topluluk verisi — EKSİKTİR, AFAD resmî listesi değildir.",
        },
        "features": feats[:limit],
    }
