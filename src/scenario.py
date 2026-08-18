"""
Fay kırılma senaryosu — "şu fay kırılırsa ne olur?"

Faz 4'teki etki analizinden iki temel farkı vardır:

1) SONLU FAY. Kaynak bir nokta değil, gerçek fay hattıdır; uzaklık her yerleşim
   için fay çizgisine en kısa mesafedir (Rjb). Bu yüzden burada şiddet
   denkleminin Rrup varyantı kullanılır (Faz 4 hiposantr varyantını kullanır).
   Faz 5 doğrulaması nokta-kaynak modelinin M≥6,5 olaylarda şiddeti ~0,45 derece
   fazla tahmin ettiğini ölçmüştü; sonlu kaynak bu sapmanın kaynağını giderir.

2) ZEMİN. Her yerleşimin Vs30 değeri ızgaradan okunur ve sarsıntıya zemin
   büyütmesi eklenir (bkz. src/site_effects.py). Çıktıda hem kaya üzerindeki
   hem zemin düzeltmeli şiddet ayrı ayrı verilir — fark görünür olsun diye.

Kırılma uzunluğu seçilebilir: fayın tamamı ya da bir bölümü. Büyüklük,
Wells & Coppersmith (1994) ile kırılan alandan hesaplanır — böylece "aynı fay,
farklı senaryo" karşılaştırması yapılabilir.
"""

import logging

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import substring

from src.config import FAULT, IPE_RRUP, VS30
from src.fault_sources import load_fault_sources, rupture_magnitude
from src.impact import MMI_BANDS, mmi_band, settlements
from src.site_effects import mmi_site_delta, nehrp_class, vs30_at

log = logging.getLogger(__name__)

MIN_REPORTED_MMI = 3.0


def predict_mmi_rrup(magnitude: float, rrup_km) -> np.ndarray:
    """Allen, Wald & Worden (2012) — kırılma yüzeyi uzaklığı (Rrup) varyantı.

    Katsayılar OpenQuake `hazardlib/gsim/allen_2012_ipe.py` ile birebir.
    """
    rrup = np.asarray(rrup_km, dtype=float)
    exponent = (1.0 + IPE_RRUP["c3"] * np.exp(magnitude - 5.0)) ** 2
    mmi = (IPE_RRUP["c0"] + IPE_RRUP["c1"] * magnitude
           + IPE_RRUP["c2"] * np.log(np.sqrt(rrup ** 2 + exponent)))
    return np.clip(mmi, 1.0, 12.0)


def mmi_sigma_rrup(rrup_km) -> np.ndarray:
    rrup = np.asarray(rrup_km, dtype=float)
    return IPE_RRUP["s1"] + IPE_RRUP["s2"] / (1.0 + (rrup / IPE_RRUP["s3"]) ** 2)


def _rupture_geometry(fault, rupture_fraction: float):
    """Fayın belirtilen oranı kadarını ortasından kırılma yüzeyi olarak alır."""
    geom = fault.geometry
    if rupture_fraction >= 0.999:
        return geom
    half = rupture_fraction / 2.0
    return substring(geom, 0.5 - half, 0.5 + half, normalized=True)


def run_scenario(fault_id: str, rupture_fraction: float = 1.0,
                 magnitude: float | None = None,
                 min_mmi: float = MIN_REPORTED_MMI,
                 limit: int = 250, sources: gpd.GeoDataFrame = None) -> dict:
    """Bir fay için kırılma senaryosu üretir."""
    gdf = load_fault_sources() if sources is None else sources
    match = gdf[gdf["fault_id"] == fault_id]
    if match.empty:
        raise KeyError(f"Fay bulunamadı: {fault_id}")
    fault = match.iloc[0]

    rupture_fraction = float(np.clip(rupture_fraction, 0.05, 1.0))
    rupture = _rupture_geometry(fault, rupture_fraction)
    rupture_len = float(fault["length_km"]) * rupture_fraction
    width = float(fault["width_km"])
    rake = float(fault["rake"]) if pd.notna(fault["rake"]) else None

    mag = float(magnitude) if magnitude else rupture_magnitude(rupture_len, width, rake)
    mag = float(np.clip(mag, 4.0, 8.5))
    ztor = float(fault["upper_km"]) if pd.notna(fault["upper_km"]) else 0.0

    # Yerleşimlerin kırılma yüzeyine yatay uzaklığı (Rjb)
    towns = settlements().copy()
    pts = gpd.GeoSeries(gpd.points_from_xy(towns["longitude"], towns["latitude"]),
                        crs="EPSG:4326").to_crs(FAULT["metric_crs"])
    line = gpd.GeoSeries([rupture], crs="EPSG:4326").to_crs(FAULT["metric_crs"]).iloc[0]
    towns["rjb_km"] = pts.distance(line).to_numpy() / 1000.0
    towns = towns[towns["rjb_km"] <= IPE_RRUP["max_distance_km"]].copy()
    if towns.empty:
        return _empty(fault, mag, rupture_len, rupture_fraction)

    # Kırılma yüzeyine uzaklık: yatay mesafe ile üst kenar derinliğinin bileşkesi
    towns["rrup_km"] = np.sqrt(towns["rjb_km"] ** 2 + ztor ** 2)

    towns["mmi_rock"] = predict_mmi_rrup(mag, towns["rrup_km"].to_numpy())
    towns["sigma"] = mmi_sigma_rrup(towns["rrup_km"].to_numpy())
    towns["vs30"] = vs30_at(towns["latitude"].to_numpy(), towns["longitude"].to_numpy())
    towns["delta"] = mmi_site_delta(towns["vs30"].to_numpy(), mag,
                                    towns["rjb_km"].to_numpy(), rake)
    towns["mmi"] = np.clip(towns["mmi_rock"] + towns["delta"], 1.0, 12.0)

    towns = towns[towns["mmi"] >= min_mmi].sort_values("mmi", ascending=False)
    if towns.empty:
        return _empty(fault, mag, rupture_len, rupture_fraction)

    bands = []
    for threshold, roman, label, color in MMI_BANDS:
        sel = towns[towns["mmi"] >= threshold]
        if sel.empty:
            continue
        bands.append({
            "mmi_min": threshold, "roman": roman, "label": label, "color": color,
            "settlements": int(len(sel)), "population": int(sel["population"].sum()),
        })

    amplified = towns[towns["delta"] > 0]
    top = towns.head(limit)

    return {
        "fault": {
            "fault_id": fault["fault_id"], "label": fault["label"],
            "model": fault["catalog_name"], "slip_type": fault["slip_type"],
            "length_km": round(float(fault["length_km"]), 1),
            "width_km": round(width, 1),
            "mmax": round(float(fault["mmax"]), 2),
            "slip_rate": float(fault["slip_rate"]) if pd.notna(fault["slip_rate"]) else None,
            "recurrence_years": (round(float(fault["recurrence_years"]))
                                 if pd.notna(fault["recurrence_years"]) else None),
            "p50": round(float(fault["p50"]), 4) if pd.notna(fault.get("p50")) else None,
        },
        "rupture": {
            "fraction": round(rupture_fraction, 3),
            "length_km": round(rupture_len, 1),
            "magnitude": round(mag, 2),
            "ztor_km": round(ztor, 1),
            "geometry": [[float(y), float(x)] for x, y in rupture.coords],
        },
        "max_mmi": round(float(towns["mmi"].max()), 2),
        "total_settlements": int(len(towns)),
        "total_population": int(towns["population"].sum()),
        "bands": bands,
        "site_effect": {
            "mean_delta": round(float(towns["delta"].mean()), 3),
            "max_delta": round(float(towns["delta"].max()), 3),
            "amplified_settlements": int(len(amplified)),
            "amplified_population": int(amplified["population"].sum()),
            "median_vs30": int(np.median(towns["vs30"])),
        },
        "settlements": [{
            "name": r["name"], "lat": float(r["latitude"]), "lon": float(r["longitude"]),
            "population": int(r["population"]),
            "rjb_km": round(float(r["rjb_km"]), 1),
            "mmi_rock": round(float(r["mmi_rock"]), 2),
            "mmi": round(float(r["mmi"]), 2),
            "delta": round(float(r["delta"]), 2),
            "sigma": round(float(r["sigma"]), 2),
            "vs30": int(r["vs30"]),
            "nehrp": nehrp_class(float(r["vs30"]))[0],
            "roman": mmi_band(float(r["mmi"]))[0],
        } for _, r in top.iterrows()],
        "caveats": _caveats(),
    }


def _empty(fault, mag, rupture_len, fraction) -> dict:
    return {
        "fault": {"fault_id": fault["fault_id"], "label": fault["label"]},
        "rupture": {"fraction": round(fraction, 3), "length_km": round(rupture_len, 1),
                    "magnitude": round(mag, 2), "geometry": []},
        "max_mmi": None, "total_settlements": 0, "total_population": 0,
        "bands": [], "site_effect": None, "settlements": [],
        "caveats": _caveats(),
    }


def _caveats() -> list[str]:
    return [
        "Bu bir SENARYODUR, tahmin değildir: fayın kırılacağı zamanı söylemez. "
        "Olasılıklar uzun dönem ortalamalardır (Poisson).",
        "Kırılma yüzeyi, fay hattının seçilen oranı kadar orta bölümü olarak alınır; "
        "gerçek kırılmalar segment sınırlarına ve pürüzlere göre şekillenir.",
        f"Zemin verisi ~{int(VS30['pad_deg'] * 0 + 1)} km çözünürlüklü, topoğrafik eğimden "
        "türetilmiş Vs30 vekilidir — sondaj değildir, mikrobölgeleme yerine geçmez.",
        "Şiddet denklemi 300 km'ye kadar geçerlidir; sıvılaşma, heyelan ve yapı "
        "hasarı modellenmez.",
        "Yerleşim nüfusları il/ilçe merkezleridir; il düzeyinde ölçülen sapma "
        "−%31 … +%32'dir (bkz. Etki Analizi).",
    ]


def compare_site_effect(fault_id: str, rupture_fraction: float = 1.0) -> dict:
    """Zemin etkisinin en belirgin olduğu yerleşimleri döndürür."""
    result = run_scenario(fault_id, rupture_fraction, limit=500)
    rows = sorted(result["settlements"], key=lambda s: -s["delta"])[:25]
    return {
        "fault": result["fault"], "rupture": result["rupture"],
        "site_effect": result["site_effect"], "most_amplified": rows,
    }
