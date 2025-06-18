import pandas as pd
import matplotlib.pyplot as plt
import folium
from folium.plugins import HeatMap

def plot_magnitude_hist(df):
    plt.figure()
    df["magnitude"].hist(bins=20)
    plt.title("Deprem Büyüklüğü Dağılımı")
    plt.xlabel("Büyüklük")
    plt.ylabel("Frekans")
    plt.tight_layout()
    plt.show()

def plot_depth_vs_magnitude(df):
    plt.figure()
    plt.scatter(df["depth"], df["magnitude"], alpha=0.5)
    plt.title("Derinlik vs Büyüklük")
    plt.xlabel("Derinlik (km)")
    plt.ylabel("Büyüklük")
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def generate_heatmap(df, center_lat=39.0, center_lon=35.0, zoom_start=5):
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start)
    heat_data = [
        [row["latitude"], row["longitude"], row["magnitude"]]
        for _, row in df.iterrows()
        if not pd.isnull(row["latitude"]) and not pd.isnull(row["longitude"])
    ]
    HeatMap(heat_data, radius=8, blur=15, max_zoom=10).add_to(m)
    return m
