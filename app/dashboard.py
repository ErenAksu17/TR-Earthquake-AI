"""
TR Earthquake AI — Ana Dashboard
Yeniden tasarlandı: estetik, hız optimizasyonları, ML entegrasyonu.
"""

import streamlit as st

st.set_page_config(
    page_title="TR Earthquake AI",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import date, timedelta
from streamlit_folium import st_folium
import geopandas as gpd
import folium
from folium.plugins import HeatMap, MiniMap, MarkerCluster
from shapely.geometry import box
import json
import os
import sys

# Proje kökünü path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import PATHS, MAP, DEFAULTS, ML
from src.ml_model import (
    train_risk_model, load_risk_model,
    cluster_seismic_zones, load_cluster_model, apply_cluster_labels,
    get_feature_importance, predict_magnitude_class,
    CLUSTER_RISK_NAMES, CLUSTER_COLORS, LABEL_COLORS,
)
from src.fay_risk_analiz import calculate_fault_risk, load_fault_risk, risk_color

# ── CSS ──────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* Sidebar stili */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1117 0%, #0f172a 100%);
    border-right: 1px solid #1e293b;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 15px !important;
    padding: 6px 0 !important;
}

/* Metrik kartlar */
div[data-testid="metric-container"] {
    background: #161b2e;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 16px 20px;
    border-left: 3px solid #ff4b4b;
}
div[data-testid="metric-container"] label {
    color: #8b949e !important;
    font-size: 12px !important;
    text-transform: uppercase;
    letter-spacing: 1px;
}
div[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #f0f6fc !important;
    font-size: 26px !important;
    font-weight: 700 !important;
}

/* Sayfa başlıkları */
.page-header {
    font-size: 28px;
    font-weight: 700;
    color: #f0f6fc;
    margin-bottom: 2px;
}
.page-subtitle {
    font-size: 14px;
    color: #8b949e;
    margin-bottom: 18px;
}

/* Bilgi kutusu */
.info-box {
    background: #161b2e;
    border: 1px solid #1e293b;
    border-left: 4px solid #3b82f6;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    color: #cbd5e1;
    font-size: 14px;
}

/* Risk tablosu */
.risk-table th {
    background: #1e293b !important;
    color: #94a3b8 !important;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Renk etiketleri */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
}
.badge-red    { background: rgba(255,75,75,0.15);  color: #ff4b4b; }
.badge-orange { background: rgba(255,102,0,0.15);  color: #ff6600; }
.badge-yellow { background: rgba(255,170,0,0.15);  color: #ffaa00; }
.badge-green  { background: rgba(76,175,80,0.15);  color: #4caf50; }
.badge-blue   { background: rgba(51,153,255,0.15); color: #3399ff; }

/* Sidebar logo */
.sidebar-logo {
    text-align: center;
    padding: 10px 0 20px 0;
    border-bottom: 1px solid #1e293b;
    margin-bottom: 20px;
}
.sidebar-logo h2 {
    color: #ff4b4b;
    font-size: 20px;
    font-weight: 800;
    margin: 8px 0 2px 0;
}
.sidebar-logo p {
    color: #8b949e;
    font-size: 11px;
    margin: 0;
}

/* Yükleme animasyonu gizleme */
[data-testid="stSpinner"] {
    background: #0e1117;
}
</style>
""", unsafe_allow_html=True)


# ── Veri yükleme (önbellekli) ─────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def load_data() -> pd.DataFrame:
    df = pd.read_excel(PATHS["merged"])
    df["eventDate"] = pd.to_datetime(df["eventDate"], errors="coerce")
    df = df.dropna(subset=["eventDate", "latitude", "longitude", "magnitude"])
    df["magnitude"] = pd.to_numeric(df["magnitude"], errors="coerce")
    df["depth"]     = pd.to_numeric(df.get("depth", pd.Series(dtype=float)), errors="coerce").fillna(0)
    df = df.sort_values("eventDate").reset_index(drop=True)
    return df


@st.cache_resource(show_spinner=False)
def load_fault_geodata() -> dict | None:
    """GeoJSON fay verisi — büyük dosya, bir kez yükle."""
    try:
        lon_min, lat_min, lon_max, lat_max = MAP["turkey_bbox"]
        gdf = gpd.read_file(PATHS["faults"]).to_crs("EPSG:4326")
        turkey = gdf[gdf.geometry.intersects(box(lon_min, lat_min, lon_max, lat_max))]
        return json.loads(turkey.to_json())
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def get_risk_model():
    return load_risk_model()


@st.cache_resource(show_spinner=False)
def get_cluster_model():
    return load_cluster_model()


# ── Renk yardımcıları ─────────────────────────────────────────────────────────

def mag_color(mag: float) -> str:
    if mag >= 7.0:   return "#FF0000"
    elif mag >= 6.0: return "#FF6600"
    elif mag >= 5.0: return "#FFAA00"
    else:            return "#3399FF"


# ── Harita oluşturma (önbellekli HTML) ───────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False, max_entries=20)
def _build_map_html(
    data_json: str,
    fault_json_str: str | None,
    view_mode: str,
    show_faults: bool,
) -> str:
    """Folium haritasını HTML string olarak önbellekle."""
    df = pd.read_json(data_json, convert_dates=["eventDate"])

    m = folium.Map(
        location=[MAP["center_lat"], MAP["center_lon"]],
        zoom_start=MAP["zoom"],
        tiles="CartoDB.DarkMatter",
        prefer_canvas=True,
    )
    MiniMap(toggle_display=True, tile_layer="CartoDB.DarkMatter").add_to(m)

    if view_mode == "heatmap":
        heat_data = df[["latitude", "longitude", "magnitude"]].dropna().values.tolist()
        HeatMap(
            heat_data,
            radius=12, blur=18, max_zoom=10,
            gradient={0.2: "blue", 0.5: "cyan", 0.7: "yellow", 0.9: "orange", 1.0: "red"},
        ).add_to(m)

    elif view_mode == "cluster":
        mc     = MarkerCluster(options={"maxClusterRadius": 60, "disableClusteringAtZoom": 10})
        sample = df if len(df) <= ML["max_map_points"] else df.sample(ML["max_map_points"], random_state=42)
        for _, r in sample.iterrows():
            c = mag_color(r["magnitude"])
            folium.CircleMarker(
                location=[r["latitude"], r["longitude"]],
                radius=max(4, r["magnitude"] * 1.6),
                popup=folium.Popup(
                    f"<div style='font-family:sans-serif;font-size:13px'>"
                    f"<b>{r.get('location','Bilinmiyor')}</b><br>"
                    f"📅 {str(r['eventDate'])[:10]}<br>"
                    f"🔴 <b>{r['magnitude']:.1f} Mw</b><br>"
                    f"⬇️ {r.get('depth', '?'):.0f} km</div>",
                    max_width=220,
                ),
                color=c, fill=True, fill_color=c, fill_opacity=0.75, weight=0.8,
            ).add_to(mc)
        mc.add_to(m)

    else:  # bireysel — en büyükler
        sample = df if len(df) <= 800 else df.nlargest(800, "magnitude")
        for _, r in sample.iterrows():
            c = mag_color(r["magnitude"])
            folium.CircleMarker(
                location=[r["latitude"], r["longitude"]],
                radius=max(3, r["magnitude"] * 2.0),
                popup=folium.Popup(
                    f"<div style='font-family:sans-serif;font-size:13px'>"
                    f"<b>{r.get('location','Bilinmiyor')}</b><br>"
                    f"📅 {str(r['eventDate'])[:10]}<br>"
                    f"🔴 <b>{r['magnitude']:.1f} Mw</b><br>"
                    f"⬇️ {r.get('depth', '?'):.0f} km</div>",
                    max_width=220,
                ),
                color=c, fill=True, fill_color=c, fill_opacity=0.65, weight=0.5,
            ).add_to(m)

    # Fay hatları
    if show_faults and fault_json_str:
        fault_data = json.loads(fault_json_str)
        folium.GeoJson(
            fault_data,
            name="Diri Fay Hatları",
            style_function=lambda _: {"color": "#FF4444", "weight": 1.5, "opacity": 0.75},
            tooltip=folium.GeoJsonTooltip(fields=["catalog_name"], aliases=["Fay:"]),
        ).add_to(m)

    # Lejant
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:#161b2e;border:1px solid #1e293b;border-radius:8px;
                padding:12px 16px;font-size:12px;color:#f0f6fc">
        <b>Büyüklük Lejantı</b><br>
        <span style="color:#FF0000">●</span> M7+ — Çok Yüksek<br>
        <span style="color:#FF6600">●</span> M6-7 — Yüksek<br>
        <span style="color:#FFAA00">●</span> M5-6 — Orta<br>
        <span style="color:#3399FF">●</span> M&lt;5 — Düşük
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl().add_to(m)

    return m._repr_html_()


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar(df: pd.DataFrame):
    st.sidebar.markdown("""
    <div class="sidebar-logo">
        <div style="font-size:36px">🌍</div>
        <h2>TR Earthquake AI</h2>
        <p>Deprem Analiz & Risk Platformu</p>
    </div>
    """, unsafe_allow_html=True)

    page = st.sidebar.radio(
        "📌 Sayfa",
        ["🗺️ Deprem Haritası", "🔥 Isı Haritası", "📈 Zaman Analizi", "🤖 Risk & AI", "📊 Veri Kümesi"],
        label_visibility="collapsed",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Filtreler")

    DATE_MIN = df["eventDate"].min().date()
    DATE_MAX = df["eventDate"].max().date()
    MAG_MIN  = float(df["magnitude"].min())
    MAG_MAX  = float(df["magnitude"].max())
    DEP_MAX  = int(df["depth"].max()) if df["depth"].max() > 0 else 700

    start     = st.sidebar.date_input("Başlangıç", DATE_MIN, min_value=DATE_MIN, max_value=DATE_MAX)
    end       = st.sidebar.date_input("Bitiş",     DATE_MAX, min_value=DATE_MIN, max_value=DATE_MAX)
    mag_range = st.sidebar.slider("Büyüklük (Mw)", MAG_MIN, MAG_MAX, (DEFAULTS["mag_min"], DEFAULTS["mag_max"]), 0.1)
    dep_range = st.sidebar.slider("Derinlik (km)", 0, DEP_MAX, (0, min(DEFAULTS["depth_max"], DEP_MAX)))

    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"Veri: {df['eventDate'].min().year}–{df['eventDate'].max().year} • "
        f"{len(df):,} kayıt"
    )

    return page, start, end, mag_range, dep_range


def apply_filters(df: pd.DataFrame, start, end, mag_range, dep_range) -> pd.DataFrame:
    return df[
        (df["eventDate"].dt.date >= start) &
        (df["eventDate"].dt.date <= end) &
        (df["magnitude"].between(*mag_range)) &
        (df["depth"].between(*dep_range))
    ]


# ── Sayfa: Deprem Haritası ────────────────────────────────────────────────────

def page_harita(df: pd.DataFrame, fault_geo):
    st.markdown('<p class="page-header">🗺️ Deprem Haritası</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Filtrelenmiş depremlerin interaktif harita görünümü</p>', unsafe_allow_html=True)

    # KPI satırı
    c1, c2, c3, c4 = st.columns(4)
    last_30 = df[df["eventDate"] >= pd.Timestamp.now() - pd.Timedelta(days=30)]
    c1.metric("Toplam Kayıt",      f"{len(df):,}")
    c2.metric("En Büyük Deprem",   f"M{df['magnitude'].max():.1f}")
    c3.metric("Ort. Büyüklük",     f"M{df['magnitude'].mean():.2f}")
    c4.metric("Son 30 Günde",      f"{len(last_30):,} deprem")

    st.divider()

    # Harita kontrolleri
    k1, k2, k3 = st.columns([2, 2, 1])
    with k1:
        view_mode = st.selectbox(
            "Görünüm Modu",
            ["cluster", "heatmap", "bireysel"],
            format_func=lambda x: {"cluster": "🔵 Kümeleme (Hızlı)", "heatmap": "🔥 Isı Haritası", "bireysel": "⚪ Bireysel İşaretçi"}[x],
        )
    with k2:
        show_faults = st.checkbox("🔴 Diri Fay Hatlarını Göster", value=True)
    with k3:
        if len(df) > ML["max_map_points"] and view_mode == "cluster":
            st.caption(f"⚡ {ML['max_map_points']:,}/{len(df):,} gösteriliyor")

    fault_json_str = json.dumps(fault_geo) if fault_geo else None
    data_json      = df.to_json(date_format="iso")

    with st.spinner("🗺️ Harita yükleniyor..."):
        map_html = _build_map_html(data_json, fault_json_str, view_mode, show_faults)
        st.components.v1.html(map_html, height=560, scrolling=False)

    # Scatter
    st.subheader("📈 Büyüklük – Zaman Dağılımı")
    sample = df.sample(min(6000, len(df)), random_state=42) if len(df) > 6000 else df
    fig = px.scatter(
        sample, x="eventDate", y="magnitude",
        color="magnitude", color_continuous_scale="RdYlBu_r",
        opacity=0.55, size_max=12,
        labels={"eventDate": "Tarih", "magnitude": "Büyüklük (Mw)", "location": "Yer"},
        hover_data={"location": True},
        template="plotly_dark",
    )
    fig.update_layout(height=350, margin=dict(t=10, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)


# ── Sayfa: Isı Haritası ───────────────────────────────────────────────────────

def page_isi_haritasi(df: pd.DataFrame, fault_geo):
    st.markdown('<p class="page-header">🔥 Yoğunluk Haritası</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Sismik aktivite yoğunluğu — derinlik ve büyüklük boyutlarıyla</p>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Büyüklük Isı Haritası", "Derinlik Isı Haritası"])

    with tab1:
        m = folium.Map(location=[MAP["center_lat"], MAP["center_lon"]], zoom_start=6, tiles="CartoDB.DarkMatter")
        heat_data = df[["latitude", "longitude", "magnitude"]].dropna().values.tolist()
        HeatMap(heat_data, radius=12, blur=18,
                gradient={0.2: "blue", 0.5: "cyan", 0.7: "yellow", 0.9: "orange", 1.0: "red"}).add_to(m)
        if fault_geo:
            folium.GeoJson(fault_geo, style_function=lambda _: {"color": "#FF4444", "weight": 1.2, "opacity": 0.6}).add_to(m)
        st_folium(m, use_container_width=True, height=500, returned_objects=[])

    with tab2:
        df_d = df.copy()
        df_d["depth_norm"] = (df_d["depth"] / df_d["depth"].max()).clip(0, 1)
        m2 = folium.Map(location=[MAP["center_lat"], MAP["center_lon"]], zoom_start=6, tiles="CartoDB.DarkMatter")
        heat_data2 = df_d[["latitude", "longitude", "depth_norm"]].dropna().values.tolist()
        HeatMap(heat_data2, radius=12, blur=18,
                gradient={0.2: "#00FF00", 0.5: "#FFFF00", 0.8: "#FF6600", 1.0: "#FF0000"}).add_to(m2)
        st_folium(m2, use_container_width=True, height=500, returned_objects=[])

    # Derinlik dağılımı
    st.subheader("📊 Derinlik Dağılımı")
    fig = px.histogram(
        df, x="depth", nbins=50, color_discrete_sequence=["#FF4B4B"],
        labels={"depth": "Derinlik (km)", "count": "Deprem Sayısı"},
        template="plotly_dark",
    )
    fig.update_layout(height=300, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)


# ── Sayfa: Zaman Analizi ──────────────────────────────────────────────────────

def page_zaman_analizi(df: pd.DataFrame):
    st.markdown('<p class="page-header">📈 Zaman Analizi</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Sismik aktivitenin yıllık, aylık ve mevsimsel örüntüleri</p>', unsafe_allow_html=True)

    # Yıllık
    yillik = df.resample("YE", on="eventDate").agg(
        Adet=("magnitude", "count"),
        Ortalama_Mw=("magnitude", "mean"),
    ).reset_index()
    yillik["Tarih"] = yillik["eventDate"].dt.year

    fig1 = px.bar(
        yillik, x="Tarih", y="Adet",
        color="Ortalama_Mw", color_continuous_scale="RdYlBu_r",
        labels={"Adet": "Deprem Sayısı", "Ortalama_Mw": "Ort. Mw"},
        title="📅 Yıllık Deprem Sayısı",
        template="plotly_dark",
    )
    fig1.update_layout(height=380, margin=dict(t=40, b=10))
    st.plotly_chart(fig1, use_container_width=True)

    col1, col2 = st.columns(2)

    # Aylık
    with col1:
        aylik = df.resample("ME", on="eventDate").size().reset_index(name="Adet")
        fig2 = px.line(
            aylik, x="eventDate", y="Adet",
            title="📆 Aylık Deprem Frekansı",
            labels={"eventDate": "Tarih", "Adet": "Deprem Sayısı"},
            template="plotly_dark", color_discrete_sequence=["#FF4B4B"],
        )
        fig2.update_traces(fill="tozeroy", fillcolor="rgba(255,75,75,0.1)")
        fig2.update_layout(height=320, margin=dict(t=40, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    # Büyüklük dağılımı
    with col2:
        fig3 = px.histogram(
            df, x="magnitude", nbins=40,
            title="📊 Büyüklük Dağılımı",
            labels={"magnitude": "Büyüklük (Mw)", "count": "Frekans"},
            template="plotly_dark", color_discrete_sequence=["#FF6600"],
        )
        fig3.update_layout(height=320, margin=dict(t=40, b=10))
        st.plotly_chart(fig3, use_container_width=True)

    # Mevsimsel ısı haritası (yıl × ay)
    st.subheader("🌡️ Yıl × Ay Sismik Isı Haritası")
    df_hm = df.copy()
    df_hm["Yıl"] = df_hm["eventDate"].dt.year
    df_hm["Ay"]  = df_hm["eventDate"].dt.month
    pivot = df_hm.groupby(["Yıl", "Ay"]).size().unstack(fill_value=0)
    fig4 = px.imshow(
        pivot,
        labels={"x": "Ay", "y": "Yıl", "color": "Deprem Sayısı"},
        color_continuous_scale="YlOrRd",
        aspect="auto",
        template="plotly_dark",
    )
    fig4.update_layout(height=420, margin=dict(t=10, b=10))
    st.plotly_chart(fig4, use_container_width=True)

    # Kümülatif
    st.subheader("📉 Kümülatif Deprem Sayısı")
    df_cum = df.sort_values("eventDate").copy()
    df_cum["Kümülatif"] = range(1, len(df_cum) + 1)
    fig5 = px.area(
        df_cum.iloc[::max(1, len(df_cum)//2000)],  # downsample for speed
        x="eventDate", y="Kümülatif",
        labels={"eventDate": "Tarih", "Kümülatif": "Toplam Deprem"},
        template="plotly_dark", color_discrete_sequence=["#3399FF"],
    )
    fig5.update_layout(height=300, margin=dict(t=10, b=10))
    st.plotly_chart(fig5, use_container_width=True)


# ── Sayfa: Risk & AI ─────────────────────────────────────────────────────────

def page_risk_ai(df: pd.DataFrame, fault_geo):
    st.markdown('<p class="page-header">🤖 Risk Analizi & Yapay Zeka</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Fay hattı risk skorları, sismik zon kümeleme ve büyüklük sınıflandırması</p>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["⚠️ Fay Risk Tablosu", "🗺️ Sismik Zon Haritası", "🤖 ML Tahmin Modeli"])

    # ── Tab 1: Fay Risk ──
    with tab1:
        st.subheader("Diri Fay Hatları Risk Skoru")

        col_btn, col_info = st.columns([1, 3])
        with col_btn:
            recalc = st.button("🔄 Risk Skorunu Yeniden Hesapla", use_container_width=True)

        risk_df = load_fault_risk()
        if recalc or risk_df is None:
            with st.spinner("Fay risk skoru hesaplanıyor..."):
                risk_df = calculate_fault_risk()

        if risk_df is not None and not risk_df.empty:
            # Risk (0-100) varsa göster
            display_cols = ["Fay Adı", "Deprem Sayısı", "Ortalama Mw", "En Büyük Mw", "Son Deprem", "Risk Skoru", "Risk (0-100)"]
            display_cols = [c for c in display_cols if c in risk_df.columns]
            top_n = risk_df.head(20)[display_cols].copy()

            # Renkli gösterim için stil
            def highlight_risk(val):
                if isinstance(val, (int, float)):
                    if val >= 75:   return "color: #FF0000; font-weight: bold"
                    elif val >= 50: return "color: #FF6600; font-weight: bold"
                    elif val >= 25: return "color: #FFAA00"
                    else:           return "color: #4CAF50"
                return ""

            styled = top_n.style.applymap(highlight_risk, subset=["Risk (0-100)"] if "Risk (0-100)" in top_n.columns else [])
            st.dataframe(styled, use_container_width=True, height=420)

            # Bar chart
            fig = px.bar(
                risk_df.head(15).sort_values("Risk Skoru"),
                x="Risk Skoru", y="Fay Adı",
                orientation="h",
                color="Risk Skoru",
                color_continuous_scale="RdYlGn_r",
                title="En Riskli 15 Fay Hattı",
                template="plotly_dark",
            )
            fig.update_layout(height=450, margin=dict(t=40, b=10), yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Fay risk skoru henüz hesaplanmadı veya veri bulunamadı.")

    # ── Tab 2: Sismik Zon Haritası ──
    with tab2:
        st.subheader("K-Means Sismik Zon Kümeleme")

        col_run, col_info = st.columns([1, 3])
        with col_run:
            run_cluster = st.button("🗺️ Kümeleri Hesapla / Güncelle", use_container_width=True)
        with col_info:
            st.markdown('<div class="info-box">Depremler coğrafi konumlarına ve büyüklüklerine göre 5 sismik riske zonu ayrılır. Kırmızı bölgeler tarihsel olarak en yoğun sismik aktiviteyi göstermektedir.</div>', unsafe_allow_html=True)

        cluster_data = get_cluster_model()

        if run_cluster or cluster_data is None:
            with st.spinner("Küme modeli hesaplanıyor..."):
                df_clustered = cluster_seismic_zones(df)
                st.cache_resource.clear()
                cluster_data = get_cluster_model()
        else:
            df_clustered = apply_cluster_labels(df, cluster_data)

        # Küme haritası
        m = folium.Map(location=[MAP["center_lat"], MAP["center_lon"]], zoom_start=6, tiles="CartoDB.DarkMatter")

        sample = df_clustered if len(df_clustered) <= ML["max_map_points"] else df_clustered.sample(ML["max_map_points"], random_state=42)
        for _, r in sample.iterrows():
            folium.CircleMarker(
                location=[r["latitude"], r["longitude"]],
                radius=3,
                color=r["cluster_color"],
                fill=True,
                fill_color=r["cluster_color"],
                fill_opacity=0.6,
                weight=0,
                tooltip=r["risk_label"],
            ).add_to(m)

        if fault_geo:
            folium.GeoJson(fault_geo, style_function=lambda _: {"color": "#FFFFFF", "weight": 1, "opacity": 0.4}).add_to(m)

        st_folium(m, use_container_width=True, height=500, returned_objects=[])

        # Zon dağılımı
        zone_counts = df_clustered["risk_label"].value_counts().reset_index()
        zone_counts.columns = ["Zon", "Sayı"]
        fig_z = px.pie(
            zone_counts, names="Zon", values="Sayı",
            color="Zon",
            color_discrete_map=dict(zip(CLUSTER_RISK_NAMES, CLUSTER_COLORS)),
            title="Sismik Zon Dağılımı",
            template="plotly_dark",
        )
        fig_z.update_layout(height=350)
        st.plotly_chart(fig_z, use_container_width=True)

    # ── Tab 3: ML Modeli ──
    with tab3:
        st.subheader("Random Forest — Büyüklük Sınıflandırması")

        col_train, col_status = st.columns([1, 3])
        with col_train:
            train_btn = st.button("🚀 Modeli Eğit / Yeniden Eğit", use_container_width=True)
        with col_status:
            model_data = get_risk_model()
            if model_data:
                st.success("✅ Eğitilmiş model mevcut.")
            else:
                st.warning("⚠️ Henüz eğitilmiş model yok. 'Modeli Eğit' butonuna bas.")

        if train_btn:
            with st.spinner("🤖 Model eğitiliyor... (bu 30-60 saniye sürebilir)"):
                result = train_risk_model(df)
                st.cache_resource.clear()
                model_data = result

            acc = result["accuracy"]
            cv  = result["cv_scores"]
            st.success(f"✅ Model eğitildi! Test doğruluğu: **{acc:.1%}** | CV: {cv.mean():.1%} ± {cv.std():.1%}")

        if model_data:
            col_a, col_b = st.columns(2)

            with col_a:
                # Feature importance
                fi = get_feature_importance(model_data)
                fig_fi = px.bar(
                    fi, x="Önem", y="Özellik",
                    orientation="h",
                    title="🎯 Feature Importance",
                    color="Önem",
                    color_continuous_scale="RdYlBu_r",
                    template="plotly_dark",
                )
                fig_fi.update_layout(height=350, margin=dict(t=40, b=10), yaxis_title="", coloraxis_showscale=False)
                st.plotly_chart(fig_fi, use_container_width=True)

            with col_b:
                # Classification report
                report = model_data.get("report", {})
                if report:
                    rows = []
                    for label, vals in report.items():
                        if isinstance(vals, dict):
                            rows.append({
                                "Sınıf": label,
                                "Hassasiyet": round(vals.get("precision", 0), 3),
                                "Duyarlılık":  round(vals.get("recall", 0), 3),
                                "F1-Score":    round(vals.get("f1-score", 0), 3),
                                "Destek":      int(vals.get("support", 0)),
                            })
                    if rows:
                        st.markdown("**📋 Sınıflandırma Raporu**")
                        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=250)

            # Tahmin dağılımı görselleştirme
            sample_pred = df.sample(min(3000, len(df)), random_state=42)
            preds = predict_magnitude_class(sample_pred, model_data)
            sample_pred = sample_pred.copy()
            sample_pred["Tahmin"] = preds

            fig_pred = px.scatter(
                sample_pred, x="longitude", y="latitude",
                color="Tahmin",
                color_discrete_map=LABEL_COLORS,
                opacity=0.6, size_max=6,
                title="🗺️ Tahmin Edilen Büyüklük Sınıfı (Coğrafi Dağılım)",
                labels={"longitude": "Boylam", "latitude": "Enlem"},
                template="plotly_dark",
            )
            fig_pred.update_layout(height=420, margin=dict(t=40, b=10))
            st.plotly_chart(fig_pred, use_container_width=True)


# ── Sayfa: Veri Kümesi ────────────────────────────────────────────────────────

def page_veri_kumesi(df: pd.DataFrame):
    st.markdown('<p class="page-header">📊 Veri Kümesi</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Tüm deprem kayıtlarını arayın, filtreleyin ve indirin</p>', unsafe_allow_html=True)

    col_a, col_b = st.columns([3, 1])
    with col_a:
        search = st.text_input("🔎 Konum Ara", placeholder="İstanbul, Ege, Kuzey...")
    with col_b:
        sort_by = st.selectbox("Sırala", ["eventDate ↓", "magnitude ↓", "depth ↓"])

    filtered = df.copy()
    if search:
        mask = df["location"].fillna("").str.contains(search, case=False, na=False)
        filtered = df[mask]

    sort_col  = sort_by.split(" ")[0]
    sort_asc  = "↑" in sort_by
    if sort_col in filtered.columns:
        filtered = filtered.sort_values(sort_col, ascending=sort_asc)

    # Özet
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gösterilen Kayıt", f"{len(filtered):,}")
    c2.metric("Tarih Aralığı",
              f"{filtered['eventDate'].min().year}–{filtered['eventDate'].max().year}" if not filtered.empty else "—")
    c3.metric("En Büyük", f"M{filtered['magnitude'].max():.1f}" if not filtered.empty else "—")
    c4.metric("Ort. Derinlik", f"{filtered['depth'].mean():.0f} km" if not filtered.empty else "—")

    st.divider()

    display = filtered[["eventDate", "latitude", "longitude", "depth", "magnitude", "location"]].rename(columns={
        "eventDate": "Tarih",
        "latitude":  "Enlem",
        "longitude": "Boylam",
        "depth":     "Derinlik (km)",
        "magnitude": "Büyüklük (Mw)",
        "location":  "Yer",
    }).reset_index(drop=True)

    st.dataframe(display, use_container_width=True, height=480)

    dl1, dl2 = st.columns(2)
    with dl1:
        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button("📥 CSV İndir", data=csv, file_name="tr_earthquake_data.csv", mime="text/csv", use_container_width=True)
    with dl2:
        excel_buf = filtered.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Tüm Veri (CSV)", data=excel_buf, file_name="tr_earthquake_full.csv", mime="text/csv", use_container_width=True)


# ── Ana uygulama ─────────────────────────────────────────────────────────────

def main():
    with st.spinner("📡 Veriler yükleniyor..."):
        df_raw     = load_data()
        fault_geo  = load_fault_geodata()

    page, start, end, mag_range, dep_range = render_sidebar(df_raw)
    df = apply_filters(df_raw, start, end, mag_range, dep_range)

    if df.empty:
        st.warning("⚠️ Seçilen filtreler için kayıt bulunamadı. Filtreleri genişletin.")
        return

    if page == "🗺️ Deprem Haritası":
        page_harita(df, fault_geo)
    elif page == "🔥 Isı Haritası":
        page_isi_haritasi(df, fault_geo)
    elif page == "📈 Zaman Analizi":
        page_zaman_analizi(df)
    elif page == "🤖 Risk & AI":
        page_risk_ai(df_raw, fault_geo)   # ML sayfası ham veriyle çalışır
    elif page == "📊 Veri Kümesi":
        page_veri_kumesi(df)


if __name__ == "__main__":
    main()
