import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString

# Depremleri oku
df = pd.read_excel("data/merged_quakes.xlsx")
df = df.dropna(subset=["latitude", "longitude", "magnitude", "eventDate"])
df["geometry"] = df.apply(lambda r: Point(r["longitude"], r["latitude"]), axis=1)
quakes_gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

# Fay hatlarını oku
faylar = gpd.read_file("data/diri_faylar.geojson")
faylar = faylar.to_crs("EPSG:4326")

# Buffer oluştur (10 km mesafe içinde olan depremler eşleşsin)
faylar["geometry"] = faylar["geometry"].buffer(0.1)  # yaklaşık 10 km

# Eşleştir
matched = gpd.sjoin(quakes_gdf, faylar, how="inner", predicate="intersects")

# Fay bazlı grupla
grouped = matched.groupby("catalog_name").agg({
    "magnitude": ["count", "mean", "max"],
    "eventDate": "max"
})
grouped.columns = ["Deprem Sayısı", "Ortalama Mw", "En Büyük Mw", "Son Deprem"]
grouped["Yıl Geçti"] = pd.Timestamp.now().year - pd.to_datetime(grouped["Son Deprem"]).dt.year

# Basit risk puanı
grouped["Risk Skoru"] = (
    (grouped["Deprem Sayısı"] * grouped["Ortalama Mw"]) / (grouped["Yıl Geçti"] + 1)
).round(2)

# Kaydet
grouped.reset_index().to_csv("data/fay_risk_skorlari.csv", index=False)
print("✅ Risk skoru hesaplandı: data/fay_risk_skorlari.csv")
