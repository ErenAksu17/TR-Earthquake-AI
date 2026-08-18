"""
Zemin büyütmesi — aynı deprem yumuşak zeminde neden daha sert hissedilir?

Zincir (her katsayı kaynağından birebir doğrulandı):

1) Boore, Stewart, Seyhan & Atkinson (2014) — NGA-West2 yer hareketi denklemi.
   Kaya üzerindeki PGA ile Vs30'a bağlı saha terimleri hesaplanır.
   Katsayılar OpenQuake `hazardlib/gsim/boore_2014.py` kaynağından alınmıştır.

2) Saha büyütmesi = doğrusal terim (denklem 6) + doğrusal olmayan terim (7-8).
   Doğrusal olmayan terim, kuvvetli sarsıntıda yumuşak zeminin "doyması"nı
   modeller: zemin belirli bir seviyeden sonra daha fazla büyütmez, hatta söner.

3) Büyütme oranı MMI farkına çevrilir — Wald, Quitoriano, Heaton & Kanamori
   (1999): MMI = 3.66·log10(PGA) − 1.66  ⇒  ΔMMI = 3.66·log10(PGA_zemin/PGA_kaya)

NEDEN BÖYLE: Projedeki şiddet denklemi (Allen vd. 2012) Faz 5'te 1.387 DYFI
gözlemine karşı doğrulandı (sapma −0,01 MMI, MAE 0,83). Onu tamamen değiştirmek
yerine omurga olarak koruyup, üzerine fiziksel olarak türetilmiş bir zemin
düzeltmesi ekliyoruz. Böylece doğrulanmış temel korunur, eksik olan katman eklenir.

SINIR: Vs30 verisi topoğrafik eğimden türetilmiş ~1 km çözünürlüklü vekil
değerdir; sondaj değildir ve mikrobölgeleme yerine geçmez.
"""

import functools
import logging
import os

import numpy as np

from src.config import PATHS, VS30

log = logging.getLogger(__name__)

# Boore vd. (2014) PGA katsayıları — OpenQuake kaynağından birebir
BSSA14_PGA = {
    "e0": 0.4473, "e1": 0.4856, "e2": 0.2459, "e3": 0.4539,
    "e4": 1.431, "e5": 0.05053, "e6": -0.1662, "Mh": 5.5,
    "c1": -1.134, "c2": 0.1917, "c3": -0.008088, "h": 4.5, "Dc3": 0.0,
    "c": -0.6, "Vc": 1500.0, "f4": -0.15, "f5": -0.00701,
}
CONSTS = {"Mref": 4.5, "Rref": 1.0, "Vref": 760.0, "f1": 0.0, "f3": 0.1}

# Wald vd. (1999) PGA → MMI eğimi
WALD99_SLOPE = 3.66

# NEHRP zemin sınıfları (sunum için)
NEHRP_CLASSES = [
    (1500.0, "A", "Sert kaya"),
    (760.0, "B", "Kaya"),
    (360.0, "C", "Çok sıkı zemin / yumuşak kaya"),
    (180.0, "D", "Sıkı zemin"),
    (0.0, "E", "Yumuşak zemin"),
]


def nehrp_class(vs30: float) -> tuple[str, str]:
    """Vs30 değerini NEHRP zemin sınıfına çevirir."""
    for threshold, code, label in NEHRP_CLASSES:
        if vs30 >= threshold:
            return code, label
    return "E", "Yumuşak zemin"


def _style_term(rake: float | None) -> float:
    """Fay tipine göre sabit terim (kaynaktaki rake eşikleriyle aynı)."""
    C = BSSA14_PGA
    if rake is None:
        return C["e0"]
    if abs(rake) <= 30.0 or (180.0 - abs(rake)) <= 30.0:
        return C["e1"]          # doğrultu atımlı
    if 30.0 < rake < 150.0:
        return C["e3"]          # ters
    return C["e2"]              # normal


def pga_on_rock(magnitude: float, rjb_km, rake: float | None = None) -> np.ndarray:
    """Referans kaya (Vs30 = 760 m/s) üzerindeki medyan PGA (g)."""
    C = BSSA14_PGA
    rjb = np.asarray(rjb_km, dtype=float)

    dmag = magnitude - C["Mh"]
    mag_term = (C["e4"] * dmag + C["e5"] * dmag ** 2) if magnitude <= C["Mh"] else (C["e6"] * dmag)
    fm = _style_term(rake) + mag_term

    rval = np.sqrt(rjb ** 2 + C["h"] ** 2)
    fp = ((C["c1"] + C["c2"] * (magnitude - CONSTS["Mref"])) * np.log(rval / CONSTS["Rref"])
          + (C["c3"] + C["Dc3"]) * (rval - CONSTS["Rref"]))
    return np.exp(fm + fp)


def site_amplification(vs30, pga_rock) -> np.ndarray:
    """Doğrusal + doğrusal olmayan saha terimlerinin toplamı (doğal log)."""
    C = BSSA14_PGA
    vs = np.asarray(vs30, dtype=float)
    pga = np.asarray(pga_rock, dtype=float)

    # Doğrusal terim (denklem 6)
    flin_ratio = np.minimum(vs, C["Vc"]) / CONSTS["Vref"]
    f_lin = C["c"] * np.log(flin_ratio)

    # Doğrusal olmayan terim (denklem 7-8)
    v_s = np.minimum(vs, 760.0)
    f_2 = C["f4"] * (np.exp(C["f5"] * (v_s - 360.0)) - np.exp(C["f5"] * 400.0))
    f_nl = CONSTS["f1"] + f_2 * np.log((pga + CONSTS["f3"]) / CONSTS["f3"])

    return f_lin + f_nl


def mmi_site_delta(vs30, magnitude: float, rjb_km, rake: float | None = None) -> np.ndarray:
    """Zeminin MMI'ya katkısı (derece). Pozitif = zemin sarsıntıyı büyütüyor."""
    pga_rock = pga_on_rock(magnitude, rjb_km, rake)
    ln_amp = site_amplification(vs30, pga_rock)
    # ΔMMI = 3.66 · log10(oran);  log10(x) = ln(x)/ln(10)
    return WALD99_SLOPE * ln_amp / np.log(10.0)


# ── Vs30 ızgarası ────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _vs30_grid():
    path = PATHS["vs30"]
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Vs30 verisi yok: {path}. 'python -m src.prepare_vs30' çalıştırın.")
    data = np.load(path)
    return data["vs30"], data["lat"], data["lon"]


def vs30_at(lat, lon) -> np.ndarray:
    """Verilen noktalardaki Vs30 (m/s). Izgara dışı noktalar varsayılana düşer."""
    grid, glat, glon = _vs30_grid()
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    lon = np.atleast_1d(np.asarray(lon, dtype=float))

    i = np.clip(np.searchsorted(glat, lat), 0, len(glat) - 1)
    j = np.clip(np.searchsorted(glon, lon), 0, len(glon) - 1)
    values = grid[i, j].astype(float)

    inside = (lat >= glat[0]) & (lat <= glat[-1]) & (lon >= glon[0]) & (lon <= glon[-1])
    values[~inside | (values <= 0)] = VS30["default_ms"]
    return values


def vs30_summary() -> dict:
    """Izgaranın özeti — arayüzde kapsam ve sınır bilgisi için."""
    grid, glat, glon = _vs30_grid()
    valid = grid[grid > 0].astype(float)
    return {
        "rows": int(grid.shape[0]), "cols": int(grid.shape[1]),
        "resolution_deg": round(float(glat[1] - glat[0]), 5),
        "lat_range": [round(float(glat[0]), 2), round(float(glat[-1]), 2)],
        "lon_range": [round(float(glon[0]), 2), round(float(glon[-1]), 2)],
        "vs30_min": int(valid.min()), "vs30_max": int(valid.max()),
        "vs30_median": int(np.median(valid)),
        "source": "USGS küresel Vs30 (Heath vd. 2020), topoğrafik eğim vekili",
        "caveat": ("~1 km çözünürlük; sondaj ölçümü değildir ve mikrobölgeleme "
                   "raporunun yerine geçmez."),
    }
