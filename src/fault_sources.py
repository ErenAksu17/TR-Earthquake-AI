"""
Fay kaynak modeli — hangi fay ne büyüklükte deprem üretebilir, ne sıklıkla?

Veri: GEM Global Active Faults Database'in Türkiye penceresi. Kayıtlar iki
hakemli sismik tehlike kaynak modelinden gelir:
    SHARE — Seismic Hazard Harmonization in Europe
    EMME  — Earthquake Model of the Middle East
Her fay için kayma hızı (tercih/alt/üst), eğim, rake ve sismojenik derinlik
aralığı verilidir. Fay ADI veri setinde YOKTUR (%0 doluluk) — bu yüzden faylar
geçtikleri yerleşimlere göre coğrafi olarak etiketlenir.

Hesap zinciri (her adımı yayımlanmış yöntem):

1) Kırılma alanı
       W = (lower_seis_depth − upper_seis_depth) / sin(dip)
       A = L × W
2) Maksimum büyüklük — Wells & Coppersmith (1994), rake'e göre:
       doğrultu atımlı : M = 3.98 + 1.02·log10(A)
       ters           : M = 4.33 + 0.90·log10(A)
       normal         : M = 3.93 + 1.02·log10(A)
   (katsayılar OpenQuake hazardlib/scalerel/wc1994.py ile birebir doğrulandı)
3) Yinelenme aralığı — sismik moment dengesi:
       Ṁ₀ = μ·A·ṡ           (μ = 3×10¹⁰ Pa, ṡ = kayma hızı)
       M₀  = 10^(1.5·M + 9.05)
       T   = M₀ / Ṁ₀
4) Olasılık — Poisson: P(t) = 1 − exp(−t/T)

YİNELENME BİR ALT SINIRDIR: Moment dengesi, biriken kaymanın TAMAMININ
karakteristik Mmax depremlerinde boşaldığını varsayar. Gerçekte kaymanın bir
kısmı asismik sürünme ve daha küçük depremlerle boşalır; bu yüzden hesaplanan
yinelenme aralığı gerçekte olduğundan KISA (olasılık ise YÜKSEK) çıkar.

NE DEĞİLDİR: Bu, "şu fay şu tarihte kırılacak" demek DEĞİLDİR. Poisson modeli
depremin hafızasız olduğunu varsayar; son kırılmadan bu yana geçen süreyi
hesaba katmaz (veri setinde `last_movement` alanı da boştur). Sonuç, uzun
dönem ortalama bir olasılıktır — sismik tehlike analizinin standart çıktısı.
"""

import logging
import math
import os
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from src.config import FAULT, MAP, PATHS, SOURCES

log = logging.getLogger(__name__)

MU = 3.0e10          # kabuk rijitliği (Pa)
DEFAULT_DIP = 90.0   # eğim bilinmiyorsa düşey kabul
DEFAULT_UPPER = 0.0
DEFAULT_LOWER = 15.0


def _first_number(value) -> float | None:
    """'(1.55,0.8,2.22)' ya da '(38,,)' biçimindeki alandan tercih değerini alır."""
    if value is None:
        return None
    text = str(value)
    if text.strip().lower() in ("nan", "none", ""):
        return None
    match = re.search(r"-?\d+\.?\d*", text)
    return float(match.group()) if match else None


def _all_numbers(value) -> tuple[float | None, float | None, float | None]:
    """(tercih, alt, üst) üçlüsünü ayrıştırır; eksik olanlar None döner."""
    if value is None:
        return (None, None, None)
    text = str(value)
    if text.strip().lower() in ("nan", "none", ""):
        return (None, None, None)
    parts = text.strip("()").split(",")
    out: list[float | None] = []
    for p in parts[:3]:
        p = p.strip()
        try:
            out.append(float(p) if p else None)
        except ValueError:
            out.append(None)
    while len(out) < 3:
        out.append(None)
    return (out[0], out[1], out[2])


def wc1994_magnitude(area_km2: float, rake: float | None) -> float:
    """Wells & Coppersmith (1994) alan → büyüklük ilişkisi."""
    if area_km2 <= 0:
        return float("nan")
    log_a = math.log10(area_km2)
    if rake is None:
        return 4.07 + 0.98 * log_a
    if (-45 <= rake <= 45) or rake >= 135 or rake <= -135:
        return 3.98 + 1.02 * log_a          # doğrultu atımlı
    if rake > 0:
        return 4.33 + 0.90 * log_a          # ters
    return 3.93 + 1.02 * log_a              # normal


def seismic_moment(magnitude: float) -> float:
    """Moment büyüklüğünden sismik moment (N·m) — Hanks & Kanamori (1979)."""
    return 10 ** (1.5 * magnitude + 9.05)


def recurrence_years(area_km2: float, slip_rate_mm_yr: float, magnitude: float) -> float | None:
    """Moment dengesinden ortalama yinelenme aralığı (yıl)."""
    if not slip_rate_mm_yr or slip_rate_mm_yr <= 0 or area_km2 <= 0:
        return None
    area_m2 = area_km2 * 1e6
    slip_m_yr = slip_rate_mm_yr / 1000.0
    moment_rate = MU * area_m2 * slip_m_yr          # N·m / yıl
    if moment_rate <= 0:
        return None
    return seismic_moment(magnitude) / moment_rate


def poisson_probability(years: float, recurrence: float | None) -> float | None:
    """Verilen sürede en az bir karakteristik deprem olasılığı."""
    if not recurrence or recurrence <= 0:
        return None
    return float(1.0 - math.exp(-years / recurrence))


def rupture_magnitude(length_km: float, width_km: float, rake: float | None) -> float:
    """Belirli bir kırılma uzunluğu için beklenen büyüklük (senaryo kurmak için)."""
    return wc1994_magnitude(max(length_km, 0.1) * max(width_km, 0.1), rake)


# ── Kaynak modelinin inşası ──────────────────────────────────────────────────

def _label_faults(gdf: gpd.GeoDataFrame) -> list[str]:
    """Fayları geçtikleri yerleşimlere göre etiketler (veri setinde ad yok)."""
    from src.impact import settlements

    towns = settlements()
    tl = towns["latitude"].to_numpy()
    tn = towns["longitude"].to_numpy()
    names = towns["name"].to_numpy()
    pops = towns["population"].to_numpy()

    labels = []
    for geom in gdf.geometry:
        coords = list(geom.coords)
        picks = [coords[0], coords[len(coords) // 2], coords[-1]]
        found: list[str] = []
        offshore = False
        for lon, lat in picks:
            d = np.sqrt(((tl - lat) * 111.0) ** 2
                        + ((tn - lon) * 111.0 * np.cos(math.radians(lat))) ** 2)
            near = np.argsort(d)[:6]
            # Yakındakiler arasından en büyük yerleşimi seç (tanınırlık için)
            best = near[np.argmax(pops[near])]
            if d[best] > 150:
                continue
            if d[best] > 55:
                offshore = True          # en yakın yerleşim uzak → deniz/kırsal
            name = str(names[best])
            if name not in found:
                found.append(name)
        if not found:
            labels.append("İsimsiz fay")
        else:
            base = " – ".join(found[:2])
            labels.append(f"{base} açıkları" if offshore and len(found) == 1 else base)
    return labels


def build_fault_sources(output: str = None, min_magnitude: float = None) -> gpd.GeoDataFrame:
    """GEM fay veritabanından Türkiye kaynak modelini üretir."""
    output = output or PATHS["fault_sources"]
    min_magnitude = min_magnitude if min_magnitude is not None else SOURCES["min_magnitude"]

    gdf = gpd.read_file(PATHS["faults"]).to_crs("EPSG:4326")
    gdf = gdf[gdf.geometry.intersects(box(*MAP["turkey_bbox"]))].copy()
    gdf = gdf[gdf.geometry.type == "LineString"].reset_index(drop=True)
    log.info("Türkiye penceresinde %d fay", len(gdf))

    # Wells & Coppersmith (1994) KABUK fayları için türetilmiştir; dalma-batma
    # arayüzleri ve açılma sırtları farklı ölçeklenir, bu yüzden dışlanır.
    non_crustal = gdf["slip_type"].astype(str).str.contains(
        "Subduction|Spreading", case=False, na=False)
    if non_crustal.any():
        log.info("Kabuk dışı kaynak dışlandı: %d", int(non_crustal.sum()))
        gdf = gdf[~non_crustal].reset_index(drop=True)

    metric = gdf.to_crs(FAULT["metric_crs"])
    gdf["length_km"] = (metric.length / 1000.0).to_numpy()
    gdf = gdf[np.isfinite(gdf["length_km"]) & (gdf["length_km"] > 1)].reset_index(drop=True)

    slip = gdf["net_slip_rate"].apply(_all_numbers)
    gdf["slip_rate"] = [s[0] for s in slip]
    gdf["slip_rate_min"] = [s[1] for s in slip]
    gdf["slip_rate_max"] = [s[2] for s in slip]
    gdf["dip"] = gdf["average_dip"].apply(_first_number).fillna(DEFAULT_DIP)
    gdf["rake"] = gdf["average_rake"].apply(_first_number)
    gdf["upper_km"] = gdf["upper_seis_depth"].apply(_first_number).fillna(DEFAULT_UPPER)
    gdf["lower_km"] = gdf["lower_seis_depth"].apply(_first_number).fillna(DEFAULT_LOWER)

    thickness = (gdf["lower_km"] - gdf["upper_km"]).clip(lower=1.0)
    dip_rad = np.radians(gdf["dip"].clip(lower=5.0, upper=90.0))
    gdf["width_km"] = (thickness / np.sin(dip_rad)).clip(upper=60.0)
    gdf["area_km2"] = gdf["length_km"] * gdf["width_km"]

    gdf["mmax"] = [wc1994_magnitude(a, r) for a, r in zip(gdf["area_km2"], gdf["rake"])]
    gdf["recurrence_years"] = [
        recurrence_years(a, s, m)
        for a, s, m in zip(gdf["area_km2"], gdf["slip_rate"], gdf["mmax"])
    ]
    for horizon in SOURCES["horizons"]:
        gdf[f"p{horizon}"] = [poisson_probability(horizon, t) for t in gdf["recurrence_years"]]

    # Sadece büyük deprem üretebilen faylar
    before = len(gdf)
    gdf = gdf[gdf["mmax"] >= min_magnitude].reset_index(drop=True)
    log.info("M≥%.1f üretebilen fay: %d (toplam %d)", min_magnitude, len(gdf), before)

    gdf = _deduplicate_sources(gdf)
    gdf["label"] = _label_faults(gdf)
    gdf["fault_id"] = [f"F{i:04d}" for i in range(len(gdf))]

    keep = ["fault_id", "label", "catalog_name", "slip_type", "rake", "dip",
            "upper_km", "lower_km", "length_km", "width_km", "area_km2", "mmax",
            "slip_rate", "slip_rate_min", "slip_rate_max", "recurrence_years",
            *[f"p{h}" for h in SOURCES["horizons"]], "geometry"]
    gdf = gdf[[c for c in keep if c in gdf.columns]]

    os.makedirs(os.path.dirname(output), exist_ok=True)
    if os.path.exists(output):
        os.remove(output)
    gdf.to_file(output, driver="GeoJSON")
    log.info("Fay kaynak modeli yazıldı: %s (%d fay)", output, len(gdf))
    return gdf


def _deduplicate_sources(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """SHARE ve EMME aynı fayları içerir — örtüşenleri teke indirir.

    İki kayıt, merkezleri birbirine yakınsa ve uzunlukları benzerse aynı fay
    sayılır. Kayma hızı daha iyi kısıtlanmış (alt/üst sınırı olan) kayıt tutulur.
    """
    if gdf.empty:
        return gdf
    cent = gdf.geometry.to_crs(FAULT["metric_crs"]).centroid.to_crs("EPSG:4326")
    lat = cent.y.to_numpy()
    lon = cent.x.to_numpy()
    length = gdf["length_km"].to_numpy()
    constrained = gdf["slip_rate_min"].notna().to_numpy()

    order = np.argsort(-length)          # uzun faylar önce
    keep = np.ones(len(gdf), dtype=bool)
    for idx in order:
        if not keep[idx]:
            continue
        dlat = (lat - lat[idx]) * 111.0
        dlon = (lon - lon[idx]) * 111.0 * math.cos(math.radians(float(lat[idx])))
        dist = np.sqrt(dlat ** 2 + dlon ** 2)
        rel_len = np.abs(length - length[idx]) / np.maximum(length[idx], 1e-9)
        dup = (dist <= SOURCES["dup_centroid_km"]) & (rel_len <= SOURCES["dup_length_frac"]) & keep
        dup[idx] = False
        if dup.any():
            # Kayma hızı kısıtlanmamışsa ve eşi kısıtlanmışsa, eşini tercih et
            if not constrained[idx]:
                better = np.where(dup & constrained)[0]
                if len(better):
                    keep[idx] = False
                    dup[better[0]] = False
            keep[dup] = False

    dropped = int((~keep).sum())
    if dropped:
        log.info("SHARE/EMME örtüşmesi: %d kayıt teke indirildi", dropped)
    return gdf[keep].reset_index(drop=True)


def load_fault_sources(path: str = None) -> gpd.GeoDataFrame:
    """Hazırlanmış fay kaynak modelini okur."""
    path = path or PATHS["fault_sources"]
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Fay kaynak modeli yok: {path}. 'python -m src.fault_sources' çalıştırın.")
    return gpd.read_file(path)


def sources_table(gdf: gpd.GeoDataFrame = None, limit: int = 300) -> list[dict]:
    """Arayüz için fay listesi — en yüksek olasılıklı önce."""
    gdf = load_fault_sources() if gdf is None else gdf
    sort_col = f"p{SOURCES['horizons'][-1]}"
    df = gdf.sort_values(sort_col, ascending=False, na_position="last").head(limit)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "fault_id": r["fault_id"],
            "label": r["label"],
            "model": r["catalog_name"],
            "slip_type": r["slip_type"],
            "length_km": round(float(r["length_km"]), 1),
            "width_km": round(float(r["width_km"]), 1),
            "mmax": round(float(r["mmax"]), 2),
            "slip_rate": float(r["slip_rate"]) if pd.notna(r["slip_rate"]) else None,
            "recurrence_years": (round(float(r["recurrence_years"]))
                                 if pd.notna(r["recurrence_years"]) else None),
            **{f"p{h}": (round(float(r[f"p{h}"]), 4) if pd.notna(r[f"p{h}"]) else None)
               for h in SOURCES["horizons"]},
        })
    return rows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    build_fault_sources()
