import requests
import pandas as pd
import os

def fetch_usgs_1900_1990(min_mag=5.0, output="data/usgs_1900_1990.csv"):
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": "1900-01-01",
        "endtime": "1989-12-31",
        "minmagnitude": min_mag,
        "limit": 20000,  # yüksek limit çünkü 90 yıl
        "orderby": "time-asc"
    }

    print("🔄 USGS verisi çekiliyor...")
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()

    records = []
    for feature in data["features"]:
        props = feature["properties"]
        coords = feature["geometry"]["coordinates"]
        records.append({
            "eventDate": pd.to_datetime(props["time"], unit='ms'),
            "latitude": coords[1],
            "longitude": coords[0],
            "depth": coords[2],
            "magnitude": props["mag"],
            "location": props["place"]
        })

    df = pd.DataFrame(records)
    os.makedirs("data", exist_ok=True)
    df.to_csv(output, index=False)
    print(f"✅ USGS verisi kaydedildi: {output}")
    print(df.head())

if __name__ == "__main__":
    fetch_usgs_1900_1990()
