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
from datetime import date
from streamlit_folium import folium_static
import folium
from folium.plugins import FastMarkerCluster, HeatMap
import geopandas as gpd
from shapely.geometry import box
import json
import os

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
div[data-testid="metric-container"] label { color: #8899aa !important; font-size: 12px !important; }
div[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #fff !important; font-size: 24px !important; font-weight: 700 !important;
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

# ── Renk ─────────────────────────────────────────────────────────────────────
def mag_color(m):
    if m >= 7:   return "#e74c3c"
    elif m >= 6: return "#e67e22"
    elif m >= 5: return "#f1c40f"
    else:        return "#3498db"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.spinner("Veriler yükleniyor..."):
    df = load_data()
    faults = load_faults()

st.sidebar.markdown("## 🌍 TR Earthquake AI")
st.sidebar.markdown("---")

sayfa = st.sidebar.radio("Sayfa", ["🗺️ Harita", "📈 Analiz", "📊 Veri"])

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

# Filtre uygula
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
# SAYFA 1 — HARİTA
# ═══════════════════════════════════════════════════════════════════════════════
if sayfa == "🗺️ Harita":
    st.title("🗺️ Deprem Haritası")

    # KPI
    son30 = f[f["eventDate"] >= pd.Timestamp.now() - pd.Timedelta(days=30)]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Kayıt",    f"{len(f):,}")
    c2.metric("En Büyük",        f"M {f['magnitude'].max():.1f}")
    c3.metric("Ortalama",        f"M {f['magnitude'].mean():.2f}")
    c4.metric("Son 30 Gün",      f"{len(son30):,}")

    st.markdown("---")

    # Harita ayarları
    k1, k2 = st.columns([2, 2])
    with k1:
        mod = st.radio("Görünüm", ["Kümeleme", "Isı Haritası", "İşaretçiler"], horizontal=True)
    with k2:
        fay_goster = st.checkbox("Diri Fay Hatları", value=True)

    # Harita oluştur
    m = folium.Map(location=[39, 35], zoom_start=6, tiles="CartoDB.DarkMatter", prefer_canvas=True)

    if mod == "Kümeleme":
        pts = f[["latitude", "longitude"]].dropna().values.tolist()
        FastMarkerCluster(pts).add_to(m)

    elif mod == "Isı Haritası":
        heat = f[["latitude", "longitude", "magnitude"]].dropna().values.tolist()
        HeatMap(heat, radius=12, blur=18,
                gradient={0.2: "blue", 0.5: "cyan", 0.7: "yellow", 1.0: "red"}).add_to(m)

    else:  # İşaretçiler — max 1500 nokta
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

    # Scatter
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

    # Yıllık bar
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
        # Büyüklük histogram
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
        # Derinlik histogram
        fig3 = px.histogram(
            f, x="depth", nbins=40,
            color_discrete_sequence=["#3498db"],
            labels={"depth": "Derinlik (km)", "count": "Frekans"},
            title="Derinlik Dağılımı",
            template="plotly_dark",
        )
        fig3.update_layout(height=320, margin=dict(t=40, b=10))
        st.plotly_chart(fig3, use_container_width=True)

    # Yıl × Ay ısı haritası
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

    # Aylık çizgi
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
    c1.metric("Kayıt",    f"{len(gosterilen):,}")
    c2.metric("En Büyük", f"M {gosterilen['magnitude'].max():.1f}" if not gosterilen.empty else "—")
    c3.metric("Ort. Derinlik", f"{gosterilen['depth'].mean():.0f} km" if not gosterilen.empty else "—")

    tablo = gosterilen[["eventDate","latitude","longitude","depth","magnitude","location"]].rename(columns={
        "eventDate": "Tarih", "latitude": "Enlem", "longitude": "Boylam",
        "depth": "Derinlik (km)", "magnitude": "Büyüklük (Mw)", "location": "Yer",
    }).sort_values("Tarih", ascending=False).reset_index(drop=True)

    st.dataframe(tablo, use_container_width=True, height=500)

    csv = gosterilen.to_csv(index=False).encode("utf-8")
    st.download_button("📥 CSV İndir", data=csv, file_name="depremler.csv", mime="text/csv")
