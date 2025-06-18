import pandas as pd
import os

def combine_excels(folder="data", output="data/merged_quakes.xlsx"):
    combined_df = pd.DataFrame()

    for file in os.listdir(folder):
        if file.endswith(".xlsx") and "Earthquake_" in file:
            path = os.path.join(folder, file)
            print(f"🔄 Yükleniyor: {file}")
            df = pd.read_excel(path)

            df = df.rename(columns={
                "Date": "eventDate",
                "Latitude": "latitude",
                "Longitude": "longitude",
                "Depth": "depth",
                "Magnitude": "magnitude",
                "Location": "location"
            })

            df = df[["eventDate", "latitude", "longitude", "depth", "magnitude", "location"]]
            combined_df = pd.concat([combined_df, df], ignore_index=True)

    combined_df["eventDate"] = pd.to_datetime(combined_df["eventDate"], errors="coerce")
    combined_df = combined_df.dropna(subset=["eventDate", "latitude", "longitude", "magnitude"])

    combined_df.to_excel(output, index=False)
    print(f"\n✅ Tüm veriler birleştirildi: {output}")

if __name__ == "__main__":
    combine_excels()
