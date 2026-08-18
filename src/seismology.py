"""
İstatistiksel sismoloji araçları — operasyonel sismolojinin kullandığı yöntemler.

- Mc (tamlık büyüklüğü): maksimum eğrilik yöntemi (+0.2 düzeltme)
- b-değeri: Aki-Utsu maksimum olabilirlik (Utsu binleme düzeltmesi,
  Shi & Bolt belirsizliği)
- Katalog ayıklama: Gardner-Knopoff (1974) zaman-mesafe pencereleri
- Artçı şok tahmini: Omori-Utsu bozunum yasası MLE + Reasenberg-Jones (1989)
  tipi olasılık hesabı — USGS'in operasyonel artçı şok tahminlerinin temeli

Bilinçli sınırlar: Tam ETAS modeli (ikincil tetiklemeler) henüz yok; tahminler
YALNIZCA olasılıksaldır ve hiçbir deterministik "deprem tahmini" içermez.
"""

import logging

import numpy as np
import pandas as pd
from scipy.optimize import minimize

log = logging.getLogger(__name__)

DM = 0.1  # katalog büyüklük binleme adımı


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _days(series: pd.Series, t0: pd.Timestamp) -> np.ndarray:
    return ((series - t0) / pd.Timedelta(days=1)).to_numpy(dtype=float)


# ── Mc: tamlık büyüklüğü ─────────────────────────────────────────────────────

def estimate_mc(mags: np.ndarray, correction: float = 0.2) -> float | None:
    """Maksimum eğrilik yöntemi: en kalabalık büyüklük bini + düzeltme.

    Basit ama yaygın ilk tahmin (Wiemer & Wyss 2000; Woessner & Wiemer 2005
    +0.2 düzeltmesini önerir).
    """
    mags = np.asarray(mags, dtype=float)
    mags = mags[np.isfinite(mags)]
    if len(mags) < 30:
        return None
    edges = np.arange(mags.min() - DM / 2, mags.max() + DM, DM)
    counts, _ = np.histogram(mags, bins=edges)
    mode_center = edges[np.argmax(counts)] + DM / 2
    return round(float(mode_center + correction), 1)


# ── b-değeri: Aki-Utsu MLE ───────────────────────────────────────────────────

def b_value(mags: np.ndarray, mc: float, dm: float = DM) -> dict | None:
    """Aki-Utsu maksimum olabilirlik b-değeri (binleme düzeltmeli).

    b = log10(e) / (M_ort - (Mc - dm/2))
    Belirsizlik: Shi & Bolt (1982). a-değeri: log10(N) + b*Mc.
    """
    mags = np.asarray(mags, dtype=float)
    m = mags[mags >= mc - 1e-9]
    n = len(m)
    if n < 30:
        return None

    mean_m = m.mean()
    denom = mean_m - (mc - dm / 2)
    if denom <= 0:
        return None

    b = np.log10(np.e) / denom
    # Shi & Bolt (1982) belirsizliği
    var = np.sum((m - mean_m) ** 2) / (n * (n - 1))
    b_err = 2.30 * b ** 2 * np.sqrt(var)
    a = np.log10(n) + b * mc

    return {"b": round(float(b), 3), "b_err": round(float(b_err), 3),
            "a": round(float(a), 3), "n": int(n), "mc": float(mc)}


def gr_curve(mags: np.ndarray, mc: float | None, fit: dict | None, dm: float = DM) -> dict:
    """Gutenberg-Richter grafiği için kümülatif sayılar + fit doğrusu."""
    mags = np.asarray(mags, dtype=float)
    grid = np.round(np.arange(mags.min(), mags.max() + dm, dm), 2)
    cum = [(float(m), int((mags >= m - 1e-9).sum())) for m in grid]
    curve = {"mags": [c[0] for c in cum], "counts": [c[1] for c in cum]}
    if fit:
        curve["fit"] = [
            {"m": float(m), "n": float(10 ** (fit["a"] - fit["b"] * m))}
            for m in grid if m >= (mc or grid[0]) - 1e-9
        ]
    return curve


# ── Gardner-Knopoff katalog ayıklama ─────────────────────────────────────────

def gk_windows(mag: float) -> tuple[float, float]:
    """Gardner-Knopoff (1974) pencereleri → (mesafe_km, süre_gün)."""
    d_km = 10 ** (0.1238 * mag + 0.983)
    if mag >= 6.5:
        t_days = 10 ** (0.032 * mag + 2.7389)
    else:
        t_days = 10 ** (0.5409 * mag - 0.547)
    return float(d_km), float(t_days)


def gardner_knopoff(df: pd.DataFrame) -> pd.DataFrame:
    """Katalogdaki artçı şokları işaretler (is_mainshock sütunu ekler).

    Büyüklüğe göre büyükten küçüğe tarar; her ana şokun zaman-mesafe penceresi
    içindeki daha küçük depremler artçı sayılır. Klasik pencere yalnızca ana
    şoktan SONRASINA uygulanır (öncüller korunur).
    """
    df = df.sort_values("eventDate").reset_index(drop=True)
    n = len(df)
    if n == 0:
        return df.assign(is_mainshock=pd.Series(dtype=bool))

    t0 = df["eventDate"].iloc[0]
    times = _days(df["eventDate"], t0)
    mags = df["magnitude"].to_numpy(dtype=float)
    lats = df["latitude"].to_numpy(dtype=float)
    lons = df["longitude"].to_numpy(dtype=float)

    is_aftershock = np.zeros(n, dtype=bool)
    for idx in np.argsort(-mags, kind="stable"):
        if is_aftershock[idx]:
            continue
        d_km, t_days = gk_windows(mags[idx])
        dt = times - times[idx]
        cand = (dt > 0) & (dt <= t_days) & (~is_aftershock) & (mags <= mags[idx])
        cand[idx] = False
        if cand.any():
            ci = np.where(cand)[0]
            d = _haversine_km(lats[idx], lons[idx], lats[ci], lons[ci])
            is_aftershock[ci[d <= d_km]] = True

    out = df.copy()
    out["is_mainshock"] = ~is_aftershock
    return out


# ── Omori-Utsu bozunumu ──────────────────────────────────────────────────────

def _omori_integral(c: float, p: float, t1: float, t2: float) -> float:
    """∫_{t1}^{t2} (t+c)^-p dt"""
    if abs(p - 1.0) < 1e-9:
        return float(np.log((t2 + c) / (t1 + c)))
    return float(((t2 + c) ** (1 - p) - (t1 + c) ** (1 - p)) / (1 - p))


C_MAX = 10.0   # gün — fiziksel olarak makul üst sınır (tipik c: 0.01–1 gün)
P_MIN, P_MAX = 0.5, 2.5


def fit_omori(t_days: np.ndarray, T: float | None = None) -> dict | None:
    """Omori-Utsu yasası λ(t) = K/(t+c)^p için maksimum olabilirlik kestirimi.

    t_days: ana şoktan itibaren gün cinsinden artçı zamanları (t>0).
    K, (c,p) verildiğinde analitik olarak profillenir: K = n / I(c,p).

    Parametre sınıra dayanırsa `at_bound` ile bildirilir — bu genellikle uyum
    penceresinin çok uzun olduğunu (geç dönemde arka plan sismisitesinin
    karıştığını) ya da erken dönem katalog eksikliğini gösterir.
    """
    t = np.sort(np.asarray(t_days, dtype=float))
    t = t[t > 0]
    n = len(t)
    if n < 20:
        return None
    T = T or float(t.max())

    def neg_ll(theta):
        log_c, p = theta
        c = np.exp(log_c)
        if not (P_MIN <= p <= P_MAX) or not (1e-4 <= c <= C_MAX):
            return 1e12
        integral = _omori_integral(c, p, 0.0, T)
        if integral <= 0:
            return 1e12
        # K profillenmiş log-olabilirlik
        return -(n * np.log(n / integral) - p * np.sum(np.log(t + c)) - n)

    best = None
    for p0 in (0.9, 1.1, 1.3):
        res = minimize(neg_ll, x0=[np.log(0.1), p0], method="Nelder-Mead",
                       options={"xatol": 1e-4, "fatol": 1e-4, "maxiter": 2000})
        if best is None or res.fun < best.fun:
            best = res

    log_c, p = best.x
    c = float(np.exp(log_c))
    K = n / _omori_integral(c, p, 0.0, T)

    at_bound = []
    if c >= C_MAX * 0.99:
        at_bound.append("c")
    if p <= P_MIN * 1.01 or p >= P_MAX * 0.99:
        at_bound.append("p")

    out = {"K": round(float(K), 3), "c": round(c, 4), "p": round(float(p), 3),
           "n": int(n), "T_days": round(T, 2)}
    if at_bound:
        out["at_bound"] = at_bound
    # Tipik gözlenen aralık p≈0.9–1.4; dışına çıkması genellikle ana şok
    # sonrası katalog eksikliğini (küçük artçıların kaydedilememesi) gösterir
    if not (0.6 <= p <= 1.8):
        out["warning"] = ("p tipik aralığın (0.9–1.4) dışında — ana şok sonrası "
                          "katalog eksikliği uyumu bozuyor olabilir.")
    return out


# ── Reasenberg-Jones tipi artçı şok tahmini ──────────────────────────────────

def aftershock_forecast(
    catalog: pd.DataFrame,
    mainshock_time: pd.Timestamp,
    mainshock_lat: float,
    mainshock_lon: float,
    mainshock_mag: float,
    now: pd.Timestamp | None = None,
    horizons_days: tuple = (7, 30),
    target_mags: tuple = (4.0, 5.0, 6.0),
    fallback_b: float = 1.0,
    fit_window_days: float = 365.0,
) -> dict:
    """Bir ana şok dizisi için olasılıksal artçı şok tahmini.

    Dizinin Omori bozunumu ve G-R büyüklük dağılımından, önümüzdeki ufuklarda
    M≥m artçı beklenen sayısı ve en az bir tanesinin olma olasılığı hesaplanır:
        N(≥m, t1→t2) = 10^(-b(m-Mc)) · K · ∫(t+c)^-p dt
        P = 1 - exp(-N)
    """
    now = now or pd.Timestamp.now("UTC").tz_localize(None)
    d_km, _ = gk_windows(mainshock_mag)

    seq = catalog[
        (catalog["eventDate"] > mainshock_time)
        & (catalog["eventDate"] <= now)
    ].copy()
    if not seq.empty:
        dist = _haversine_km(mainshock_lat, mainshock_lon,
                             seq["latitude"].to_numpy(), seq["longitude"].to_numpy())
        seq = seq[dist <= max(d_km, 100.0)]

    result = {
        "mainshock": {
            "time": mainshock_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "magnitude": float(mainshock_mag),
            "lat": float(mainshock_lat), "lon": float(mainshock_lon),
        },
        "sequence_events": int(len(seq)),
        "elapsed_days": round(float((now - mainshock_time) / pd.Timedelta(days=1)), 2),
    }

    mags = seq["magnitude"].to_numpy(dtype=float)
    mc = estimate_mc(mags) if len(mags) >= 30 else None
    if mc is None:
        mc = float(np.floor(mags.min() * 10) / 10) if len(mags) else 4.0
    seq_mc = seq[seq["magnitude"] >= mc - 1e-9]

    bres = b_value(seq_mc["magnitude"].to_numpy(), mc)
    b = bres["b"] if bres else fallback_b
    result["b_value"] = b
    result["b_source"] = "sequence" if bres else "fallback"
    result["mc"] = mc

    t_days = _days(seq_mc["eventDate"], mainshock_time)
    elapsed = result["elapsed_days"]

    # Omori uyumu sınırlı bir pencerede yapılır: dizinin geç dönemi arka plan
    # sismisitesine karışır ve uzun pencerede c'yi şişirip p'yi bozar.
    fit_T = min(elapsed, fit_window_days)
    t_fit = t_days[t_days <= fit_T]
    omori = fit_omori(t_fit, T=fit_T) if len(t_fit) >= 20 else None
    result["omori"] = omori
    result["fit_window_days"] = round(float(fit_T), 2)

    if not omori:
        result["forecast"] = None
        result["note"] = ("Dizi henüz güvenilir bir Omori kestirimi için yeterli "
                         "artçı içermiyor (M≥Mc en az 20 kayıt gerekir).")
        return result

    forecasts = []
    for h in horizons_days:
        integral = _omori_integral(omori["c"], omori["p"], elapsed, elapsed + h)
        for m in target_mags:
            expected = 10 ** (-b * (m - mc)) * omori["K"] * integral
            forecasts.append({
                "horizon_days": h,
                "min_mag": m,
                "expected": round(float(expected), 3),
                "probability": round(float(1 - np.exp(-expected)), 4),
            })
    result["forecast"] = forecasts
    return result


# ── Bölgesel b-değeri haritası ───────────────────────────────────────────────

def b_value_grid(df: pd.DataFrame, cell_deg: float = 0.5, min_n: int = 30) -> list[dict]:
    """Izgara hücresi başına b-değeri (yeterli veri olan hücrelerde)."""
    cells = []
    if df.empty:
        return cells
    # Izgara sınırları verinin kapsamından türetilir — sabit bbox kullanmak
    # kenar kümeleri (Girit/Akdeniz, Van-İran sınırı) dışarıda bırakır
    lat0 = np.floor(df["latitude"].min() / cell_deg) * cell_deg
    lat1 = np.ceil(df["latitude"].max() / cell_deg) * cell_deg
    lon0 = np.floor(df["longitude"].min() / cell_deg) * cell_deg
    lon1 = np.ceil(df["longitude"].max() / cell_deg) * cell_deg
    lat_bins = np.arange(lat0, lat1 + cell_deg, cell_deg)
    lon_bins = np.arange(lon0, lon1 + cell_deg, cell_deg)

    df = df.copy()
    df["_li"] = np.digitize(df["latitude"], lat_bins)
    df["_lj"] = np.digitize(df["longitude"], lon_bins)

    for (li, lj), grp in df.groupby(["_li", "_lj"]):
        if len(grp) < min_n or li == 0 or lj == 0 or li >= len(lat_bins) or lj >= len(lon_bins):
            continue
        mags = grp["magnitude"].to_numpy(dtype=float)
        mc = estimate_mc(mags)
        if mc is None:
            continue
        res = b_value(mags, mc)
        if res is None:
            continue
        cells.append({
            "lat": round(float(lat_bins[li - 1] + cell_deg / 2), 3),
            "lon": round(float(lon_bins[lj - 1] + cell_deg / 2), 3),
            "cell_deg": cell_deg,
            **res,
        })
    return cells
