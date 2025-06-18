import requests
import pandas as pd
from datetime import datetime
import os

BASE_URL = "https://deprem.afad.gov.tr/apiv2/event"

def ensure_data_folder():
    if not os.path.exists("data"):
        os.makedirs("data")

def fetch_all_m5_plus():
    all_data = []
    offset = 0
    limit = 500
    while True:
        params = {
            "start": "1900-01-01T00:00:00",
            "end": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "minmag": 5.0,
            "orderby": "timedesc",
            "limit": limit,
            "offset": offset
        }
        url = f"{BASE_URL}/filter"
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        json_data = resp.json()

        if isinstance(json_data, dict):
            data = json_data.get("result", [])
        elif isinstance(json_data, list):
            data = json_data
        else:
            print("Beklenmeyen veri formatı.")
            break

        if not data:
            break

        all_data.extend(data)
        offset += limit
        print(f"✔️ {offset} kayıt çekildi...")

    df = pd.DataFrame(all_data)
    return df

def save_m5_to_csv(filepath="data/m5_depremler.csv"):
    df = fetch_all_m5_plus()
    df.to_csv(filepath, index=False)
    print(f"\n✅ {len(df)} kayıt başarıyla kaydedildi: {filepath}")
    print("⏳ En eski tarih:", df['date'].min())
    print("🔥 En büyük deprem:", df['magnitude'].max())

if __name__ == "__main__":
    ensure_data_folder()
    save_m5_to_csv()
