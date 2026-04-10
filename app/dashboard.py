import streamlit as st

st.set_page_config(
    page_title="TR Earthquake AI",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import plotly.express as px
import numpy as np
from datetime import date, datetime
from streamlit_folium import folium_static
import folium
from folium.plugins import FastMarkerCluster, HeatMap
import geopandas as gpd
from shapely.geometry import box
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.fetch_kandilli import get_live, api_status

# ── Yollar ───────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #0f1624; }

div[data-testid="metric-container"] {
    background: #1a2035;
    border-radius: 10px;
    padding: 14px 18px;
    border-left: 3px solid #e74c3c;
}
div[data-testid="metric-container"] label {
    color: #8899aa !important;
    font-size: 12px !important;
}
div[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #fff !important;
    font-size: 24px !important;
    font-weight: 700 !important;
}

.canli-badge {
    display: inline-block;
    background: #e74c3c;
    color: white;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 10px;
    border-radius: 999px;
    letter-spacing: 1px;
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0%   { opacity: 1; }
    50%  { opacity: 0.5; }
    100% { opacity: 1; }
}

.mag-chip {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

# ── Veri yükleme ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_data():
    path = os.path.join(DATA, "merged_quakes.xlsx")
    df = pd.read_excel(path)
    df["eventDate"] = pd.to_datetime(df["eventDate"], errors="coerce")
    df["magnitude"] = pd.to_numeric(df["magnitude"], errors="coerce")
    df["depth"]     = pd.to_numeric(df["depth"],     errors="coerce").fillna(0)
    df = df.dropna(subset=["eventDate", "latitude", "longitude", "magnitude"])
    return df.sort_values("eventDate").reset_index(drop=True)

@st.cache_resource(show_spinner=False)
def load_faults():
    path = os.path.join(DATA, "diri_faylar.geojson")
    try:
        gdf = gpd.read_file(path).to_crs("EPSG:4326")
        tr  = gdf[gdf.geometry.intersects(box(25, 35, 45, 43))]
        return json.loads(tr.to_json())
    except Exception:
        return None

@st.cache_data(ttl=60, show_spinner=False)   # 60 saniyede bir güncelle
def load_live(source):
    return get_live(source)

# ── Renk ─────────────────────────────────────────────────────────────────────
def mag_color(m):
    if m >= 7:   return "#e74c3c"
    elif m >= 6: return "#e67e22"
    elif m >= 5: return "#f1c40f"
    else:        return "#3498db"

def mag_label(m):
    if m >= 7:   return "🔴"
    elif m >= 6: return "🟠"
    elif m >= 5: return "🟡"
    else:        return "🔵"

# ── Veri yükle ───────────────────────────────────────────────────────────────
with st.spinner("Veriler yükleniyor..."):
    df     = load_data()
    faults = load_faults()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown("## 🌍 TR Earthquake AI")
st.sidebar.markdown("---")

sayfa = st.sidebar.radio(
    "Sayfa",
    ["🔴 Canlı Veriler", "🗺️ Harita", "📈 Analiz", "📊 Veri"],
    label_visibility="collapsed",
)

# Canlı sayfa için filtre yok
if sayfa != "🔴 Canlı Veriler":
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Filtreler**")

    DATE_MIN = df["eventDate"].min().date()
    DATE_MAX = date.today()

    start = st.sidebar.date_input("Başlangıç", DATE_MIN, min_value=DATE_MIN, max_value=DATE_MAX)
    end   = st.sidebar.date_input("Bitiş",     DATE_MAX, min_value=DATE_MIN, max_value=DATE_MAX)

    MAG_MIN = float(df["magnitude"].min())
    MAG_MAX = float(df["magnitude"].max())
    mag = st.sidebar.slider("Büyüklük (Mw)", MAG_MIN, MAG_MAX, (4.0, min(7.5, MAG_MAX)), 0.1)

    DEP_MAX = int(df["depth"].max()) if df["depth"].max() > 0 else 700
    dep = st.sidebar.slider("Derinlik (km)", 0, DEP_MAX, (0, min(100, DEP_MAX)))

    f = df[
        (df["eventDate"].dt.date >= start) &
        (df["eventDate"].dt.date <= end)   &
        (df["magnitude"].between(*mag))    &
        (df["depth"].between(*dep))
    ]

    st.sidebar.markdown("---")
    st.sidebar.caption(f"{len(f):,} kayıt gösteriliyor")

    if f.empty:
        st.warning("Seçilen filtreler için kayıt yok. Filtreleri genişletin.")
        st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SAYFA 0 — CANLI VERİLER (Kandilli API)
# ═══════════════════════════════════════════════════════════════════════════════
if sayfa == "🔴 Canlı Veriler":

    col_title, col_badge = st.columns([5, 1])
    with col_title:
        st.title("🔴 Canlı Deprem Verileri")
    with col_badge:
        st.markdown("<br>", unsafe_allow_html=True)
        durum = api_status()
        if durum:
            st.success("API Aktif")
        else:
            st.error("API Erişilemiyor")

    st.caption("Kaynak: Kandilli Rasathanesi & AFAD — Boğaziçi Üniversitesi | Her 60 saniyede güncellenir")

    # Kaynak seçimi
    k1, k2, k3 = st.columns([2, 2, 3])
    with k1:
        kaynak = st.selectbox("Veri Kaynağı", ["kandilli", "afad", "all"],
                              format_func=lambda x: {"kandilli": "Kandilli Rasathanesi", "afad": "AFAD", "all": "Tümü"}[x])
    with k2:
        min_mag_canli = st.selectbox("Min. Büyüklük", [0, 1, 2, 3, 4], index=0,
                                     format_func=lambda x: f"M {x}+")
    with k3:
        st.markdown("<br>", unsafe_allow_html=True)
        yenile = st.button("🔄 Şimdi Yenile", use_container_width=False)

    if yenile:
        st.cache_data.clear()

    with st.spinner("Kandilli Rasathanesi'nden veri çekiliyor..."):
        live_df = load_live(kaynak)

    if live_df.empty:
        st.error("Canlı veri alınamadı. İnternet bağlantınızı kontrol edin.")
        st.stop()

    # Büyüklük filtresi
    if min_mag_canli > 0:
        live_df = live_df[live_df["magnitude"] >= min_mag_canli]

    # KPI
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Son 24 Saat",   f"{len(live_df)} deprem")
    c2.metric("En Büyük",      f"M {live_df['magnitude'].max():.1f}" if not live_df.empty else "—")
    c3.metric("Ortalama",      f"M {live_df['magnitude'].mean():.2f}" if not live_df.empty else "—")
    c4.metric("Ort. Derinlik", f"{live_df['depth'].mean():.0f} km"   if not live_df.empty else "—")
    st.markdown("---")

    col_map, col_tablo = st.columns([3, 2])

    with col_map:
        st.subheader("Harita")
        m = folium.Map(location=[39, 35], zoom_start=6, tiles="CartoDB.DarkMatter", prefer_canvas=True)
        for _, r in live_df.iterrows():
            c = mag_color(r["magnitude"])
            folium.CircleMarker(
                location=[r["latitude"], r["longitude"]],
                radius=max(5, r["magnitude"] * 2.5),
                color=c, fill=True, fill_color=c, fill_opacity=0.8, weight=1,
                popup=folium.Popup(
                    f"<b>{r.get('location','')}</b><br>"
                    f"🏙️ {r.get('city','')}<br>"
                    f"📅 {str(r['eventDate'])[:19]}<br>"
                    f"<b>M {r['magnitude']:.1f}</b> — {r.get('depth',0):.0f} km",
                    max_width=220,
                ),
                tooltip=f"M {r['magnitude']:.1f} — {r.get('city','')}",
            ).add_to(m)
        if faults:
            folium.GeoJson(faults, style_function=lambda _: {"color": "#e74c3c", "weight": 1.2, "opacity": 0.5}).add_to(m)
        folium_static(m, width=680, height=480)

    with col_tablo:
        st.subheader("Son Depremler")
        tablo = live_df[["eventDate", "magnitude", "depth", "location", "city"]].copy()
        tablo["Zaman"]     = tablo["eventDate"].dt.strftime("%H:%M:%S")
        tablo["Tarih"]     = tablo["eventDate"].dt.strftime("%d.%m.%Y")
        tablo["Büyüklük"]  = tablo["magnitude"].apply(lambda m: f"{mag_label(m)} M {m:.1f}")
        tablo["Derinlik"]  = tablo["depth"].apply(lambda d: f"{d:.0f} km")
        tablo = tablo.rename(columns={"location": "Konum", "city": "İl"})
        tablo = tablo[["Tarih", "Zaman", "Büyüklük", "Derinlik", "Konum", "İl"]]

        st.dataframe(
            tablo.reset_index(drop=True),
            use_container_width=True,
            height=460,
        )

    # Saatlik dağılım
    st.subheader("Saatlik Dağılım (Son 24 Saat)")
    live_df["saat"] = live_df["eventDate"].dt.hour
    saatlik = live_df.groupby("saat").size().reset_index(name="Adet")
    # Tüm saatleri göster
    saatlik_full = pd.DataFrame({"saat": range(24)}).merge(saatlik, on="saat", how="left").fillna(0)
    fig = px.bar(
        saatlik_full, x="saat", y="Adet",
        color="Adet", color_continuous_scale="RdYlBu_r",
        labels={"saat": "Saat", "Adet": "Deprem Sayısı"},
        template="plotly_dark",
    )
    fig.update_layout(height=280, margin=dict(t=10, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SAYFA 1 — HARİTA
# ═══════════════════════════════════════════════════════════════════════════════
elif sayfa == "🗺️ Harita":
    st.title("🗺️ Deprem Haritası")

    son30 = f[f["eventDate"] >= pd.Timestamp.now() - pd.Timedelta(days=30)]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Kayıt",  f"{len(f):,}")
    c2.metric("En Büyük",      f"M {f['magnitude'].max():.1f}")
    c3.metric("Ortalama",      f"M {f['magnitude'].mean():.2f}")
    c4.metric("Son 30 Gün",    f"{len(son30):,}")

    st.markdown("---")

    k1, k2 = st.columns([2, 2])
    with k1:
        mod = st.radio("Görünüm", ["Kümeleme", "Isı Haritası", "İşaretçiler"], horizontal=True)
    with k2:
        fay_goster = st.checkbox("Diri Fay Hatları", value=True)

    m = folium.Map(location=[39, 35], zoom_start=6, tiles="CartoDB.DarkMatter", prefer_canvas=True)

    if mod == "Kümeleme":
        pts = f[["latitude", "longitude"]].dropna().values.tolist()
        FastMarkerCluster(pts).add_to(m)

    elif mod == "Isı Haritası":
        heat = f[["latitude", "longitude", "magnitude"]].dropna().values.tolist()
        HeatMap(heat, radius=12, blur=18,
                gradient={0.2: "blue", 0.5: "cyan", 0.7: "yellow", 1.0: "red"}).add_to(m)

    else:
        sample = f if len(f) <= 1500 else f.nlargest(1500, "magnitude")
        for _, r in sample.iterrows():
            c = mag_color(r["magnitude"])
            folium.CircleMarker(
                location=[r["latitude"], r["longitude"]],
                radius=max(4, r["magnitude"] * 1.8),
                color=c, fill=True, fill_color=c, fill_opacity=0.7, weight=0.5,
                popup=f"{r.get('location','')} | M{r['magnitude']:.1f} | {str(r['eventDate'])[:10]}",
            ).add_to(m)

    if fay_goster and faults:
        folium.GeoJson(
            faults,
            style_function=lambda _: {"color": "#e74c3c", "weight": 1.5, "opacity": 0.7},
            tooltip=folium.GeoJsonTooltip(fields=["catalog_name"], aliases=["Fay:"]),
        ).add_to(m)

    folium.LayerControl().add_to(m)
    folium_static(m, width=1150, height=560)

    st.subheader("Büyüklük – Zaman")
    sample_sc = f if len(f) <= 5000 else f.sample(5000, random_state=1)
    fig = px.scatter(
        sample_sc, x="eventDate", y="magnitude",
        color="magnitude", color_continuous_scale="RdYlBu_r",
        opacity=0.5,
        labels={"eventDate": "Tarih", "magnitude": "Büyüklük (Mw)"},
        template="plotly_dark",
    )
    fig.update_layout(height=320, margin=dict(t=10, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SAYFA 2 — ANALİZ
# ═══════════════════════════════════════════════════════════════════════════════
elif sayfa == "📈 Analiz":
    st.title("📈 Zaman & İstatistik Analizi")

    yillik = f.resample("YE", on="eventDate").agg(
        Adet=("magnitude", "count"),
        OrtMw=("magnitude", "mean"),
    ).reset_index()
    yillik["Yıl"] = yillik["eventDate"].dt.year

    fig1 = px.bar(
        yillik, x="Yıl", y="Adet",
        color="OrtMw", color_continuous_scale="RdYlBu_r",
        labels={"Adet": "Deprem Sayısı", "OrtMw": "Ort. Mw"},
        title="Yıllık Deprem Sayısı",
        template="plotly_dark",
    )
    fig1.update_layout(height=360, margin=dict(t=40, b=10))
    st.plotly_chart(fig1, use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        fig2 = px.histogram(
            f, x="magnitude", nbins=40,
            color_discrete_sequence=["#e74c3c"],
            labels={"magnitude": "Büyüklük (Mw)", "count": "Frekans"},
            title="Büyüklük Dağılımı",
            template="plotly_dark",
        )
        fig2.update_layout(height=320, margin=dict(t=40, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    with col2:
        fig3 = px.histogram(
            f, x="depth", nbins=40,
            color_discrete_sequence=["#3498db"],
            labels={"depth": "Derinlik (km)", "count": "Frekans"},
            title="Derinlik Dağılımı",
            template="plotly_dark",
        )
        fig3.update_layout(height=320, margin=dict(t=40, b=10))
        st.plotly_chart(fig3, use_container_width=True)

    st.subheader("Yıl × Ay Aktivite Haritası")
    hm = f.copy()
    hm["Yıl"] = hm["eventDate"].dt.year
    hm["Ay"]  = hm["eventDate"].dt.month
    pivot = hm.groupby(["Yıl", "Ay"]).size().unstack(fill_value=0)
    fig4 = px.imshow(
        pivot,
        labels={"x": "Ay", "y": "Yıl", "color": "Deprem Sayısı"},
        color_continuous_scale="YlOrRd",
        aspect="auto",
        template="plotly_dark",
    )
    fig4.update_layout(height=400, margin=dict(t=10, b=10))
    st.plotly_chart(fig4, use_container_width=True)

    aylik = f.resample("ME", on="eventDate").size().reset_index(name="Adet")
    fig5 = px.line(
        aylik, x="eventDate", y="Adet",
        color_discrete_sequence=["#e74c3c"],
        labels={"eventDate": "Tarih", "Adet": "Deprem Sayısı"},
        title="Aylık Frekans",
        template="plotly_dark",
    )
    fig5.update_traces(fill="tozeroy", fillcolor="rgba(231,76,60,0.1)")
    fig5.update_layout(height=300, margin=dict(t=40, b=10))
    st.plotly_chart(fig5, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SAYFA 3 — VERİ
# ═══════════════════════════════════════════════════════════════════════════════
elif sayfa == "📊 Veri":
    st.title("📊 Veri Kümesi")

    ara = st.text_input("Konum Ara", placeholder="İstanbul, Ege, Marmara...")
    gosterilen = f.copy()
    if ara:
        gosterilen = gosterilen[gosterilen["location"].fillna("").str.contains(ara, case=False)]

    c1, c2, c3 = st.columns(3)
    c1.metric("Kayıt",         f"{len(gosterilen):,}")
    c2.metric("En Büyük",      f"M {gosterilen['magnitude'].max():.1f}" if not gosterilen.empty else "—")
    c3.metric("Ort. Derinlik", f"{gosterilen['depth'].mean():.0f} km"   if not gosterilen.empty else "—")

    tablo = gosterilen[["eventDate","latitude","longitude","depth","magnitude","location"]].rename(columns={
        "eventDate": "Tarih", "latitude": "Enlem", "longitude": "Boylam",
        "depth": "Derinlik (km)", "magnitude": "Büyüklük (Mw)", "location": "Yer",
    }).sort_values("Tarih", ascending=False).reset_index(drop=True)

    st.dataframe(tablo, use_container_width=True, height=500)

    csv = gosterilen.to_csv(index=False).encode("utf-8")
    st.download_button("📥 CSV İndir", data=csv, file_name="depremler.csv", mime="text/csv")
