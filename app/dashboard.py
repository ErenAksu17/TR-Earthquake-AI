import streamlit as st
st.set_page_config(page_title="TR Earthquake AI", layout="wide")

import pandas as pd
import plotly.express as px
import numpy as np
from datetime import date
from streamlit_folium import folium_static
import geopandas as gpd
import folium
import json
from shapely.geometry import box, LineString
from branca.colormap import linear

# ───────────────────────────────────────────────
# 1) VERİ YÜKLEME
# ───────────────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_excel("data/merged_quakes.xlsx")
    df["eventDate"] = pd.to_datetime(df["eventDate"], errors="coerce")
    df = df.dropna(subset=["eventDate", "latitude", "longitude", "magnitude"])
    df = df.rename(columns={
        "eventDate": "Tarih",
        "latitude": "Enlem",
        "longitude": "Boylam",
        "depth": "Derinlik (km)",
        "magnitude": "Büyüklük (Mw)",
        "location": "Yer"
    })
    return df

df = load_data()

# ───────────────────────────────────────────────
# 2) MENÜ
# ───────────────────────────────────────────────
menu = st.sidebar.radio("📌 Menü Seç", [
    "Deprem Haritası", "Zaman Analizi", "Veri Kümesi"
])

MAG_MIN, MAG_MAX = float(df["Büyüklük (Mw)"].min()), float(df["Büyüklük (Mw)"].max())
DEP_MIN, DEP_MAX = int(df["Derinlik (km)"].min()), int(df["Derinlik (km)"].max())
LAT_MIN, LAT_MAX = float(df["Enlem"].min()), float(df["Enlem"].max())
LON_MIN, LON_MAX = float(df["Boylam"].min()), float(df["Boylam"].max())
DATE_MIN, DATE_MAX = df["Tarih"].min().date(), df["Tarih"].max().date()

# ───────────────────────────────────────────────
# 3) DEPREM HARİTASI
# ───────────────────────────────────────────────
if menu == "Deprem Haritası":
    st.title("🗺️ Deprem Haritası")

    st.sidebar.header("🔍 Filtreler")

    start = st.sidebar.date_input("Başlangıç Tarihi", DATE_MIN)
    end = st.sidebar.date_input("Bitiş Tarihi", DATE_MAX)
    mag_range = st.sidebar.slider("Büyüklük (Mw)", MAG_MIN, MAG_MAX, (4.0, 7.5), 0.1)
    depth_range = st.sidebar.slider("Derinlik (km)", DEP_MIN, DEP_MAX, (0, 100))
    lat_range = st.sidebar.slider("Enlem", LAT_MIN, LAT_MAX, (35.0, 43.0))
    lon_range = st.sidebar.slider("Boylam", LON_MIN, LON_MAX, (25.0, 45.0))

    f = df[
        (df["Tarih"].dt.date.between(start, end)) &
        (df["Büyüklük (Mw)"].between(*mag_range)) &
        (df["Derinlik (km)"].between(*depth_range)) &
        (df["Enlem"].between(*lat_range)) &
        (df["Boylam"].between(*lon_range))
    ]

    def renk(b):
        return "red" if b >= 7 else "orange" if b >= 6 else "yellow" if b >= 5 else "blue"

    harita = folium.Map(location=[39, 35], zoom_start=6, tiles="cartodbpositron")

    for _, r in f.iterrows():
        folium.CircleMarker(
            location=[r["Enlem"], r["Boylam"]],
            radius=r["Büyüklük (Mw)"] * 1.5,
            popup=f"{r['Yer']} | {r['Büyüklük (Mw)']} Mw | {r['Tarih'].date()}",
            color=renk(r["Büyüklük (Mw)"]),
            fill=True,
            fill_opacity=0.7
        ).add_to(harita)

    # ── DİRİ FAY KATMANI ──
    try:
        fay_gdf = gpd.read_file("data/diri_faylar.geojson").to_crs("EPSG:4326")
        turkiye = fay_gdf[fay_gdf.geometry.intersects(box(25, 35, 45, 43))]
        turkiye_faylar = json.loads(turkiye.to_json())

        folium.GeoJson(
            turkiye_faylar,
            name="Diri Fay Hatları",
            style_function=lambda feat: {"color": "#FF0000", "weight": 2},
            tooltip=folium.GeoJsonTooltip(fields=["catalog_name"], aliases=["Fay Adı"])
        ).add_to(harita)

        folium.LayerControl().add_to(harita)
    except Exception as e:
        st.warning(f"Diri fay katmanı yüklenemedi: {e}")

    st.subheader("📍 Harita")
    folium_static(harita, width=1000, height=600)

    c1, c2, c3 = st.columns(3)
    c1.metric("Kayıt Sayısı", len(f))
    c2.metric("En Büyük", f["Büyüklük (Mw)"].max())
    c3.metric("Ortalama Derinlik", round(f["Derinlik (km)"].mean(), 1))

    st.subheader("📈 Büyüklük – Zaman")
    fig = px.scatter(
        f, x="Tarih", y="Büyüklük (Mw)",
        color="Büyüklük (Mw)", color_continuous_scale="turbo",
        labels={"Tarih": "Tarih", "Büyüklük (Mw)": "Mw"}
    )
    st.plotly_chart(fig, use_container_width=True)

# ───────────────────────────────────────────────
# 4) ZAMAN ANALİZİ
# ───────────────────────────────────────────────
elif menu == "Zaman Analizi":
    st.title("📈 Zaman Analizi")

    yillik = df.resample("Y", on="Tarih").size().reset_index(name="Adet")
    fig = px.bar(yillik, x="Tarih", y="Adet", title="Yıllara Göre Deprem Sayısı")
    st.plotly_chart(fig, use_container_width=True)

    aylik = df.resample("M", on="Tarih").size().reset_index(name="Adet")
    fig2 = px.line(aylik, x="Tarih", y="Adet", title="Aylık Deprem Frekansı")
    st.plotly_chart(fig2, use_container_width=True)

# ───────────────────────────────────────────────
# 5) VERİ KÜMESİ
# ───────────────────────────────────────────────
elif menu == "Veri Kümesi":
    st.title("📚 Veri Kümesi")

    iller = sorted(df["Yer"].dropna().unique().tolist())
    secili_il = st.selectbox("İl Seç (isteğe bağlı)", ["Tümü"] + iller)

    start = st.date_input("Başlangıç Tarihi", DATE_MIN, key="veri_start")
    end = st.date_input("Bitiş Tarihi", DATE_MAX, key="veri_end")
    mag_range = st.slider("Büyüklük Aralığı (Mw)", MAG_MIN, MAG_MAX, (4.0, 7.5), 0.1)

    veriler = df[
        (df["Tarih"].dt.date.between(start, end)) &
        (df["Büyüklük (Mw)"].between(*mag_range))
    ]
    if secili_il != "Tümü":
        veriler = veriler[veriler["Yer"] == secili_il]

    st.success(f"{len(veriler)} kayıt bulundu.")
    st.dataframe(veriler.sort_values("Tarih", ascending=False).reset_index(drop=True), use_container_width=True)

    csv = veriler.to_csv(index=False).encode("utf-8")
    st.download_button("📥 CSV İndir", data=csv, file_name="veri_kumesi.csv", mime="text/csv")