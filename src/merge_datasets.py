import pandas as pd

def merge_afad_usgs(afad_path="data/m5_depremler.csv", usgs_path="data/usgs_1900_1990.csv", output="data/merged_quakes.csv"):
    df_afad = pd.read_csv(afad_path)
    df_usgs = pd.read_csv(usgs_path)

    df = pd.concat([df_afad, df_usgs], ignore_index=True)
    df["eventDate"] = pd.to_datetime(df["eventDate"], errors="coerce")
    df = df.dropna(subset=["eventDate", "latitude", "longitude", "magnitude"])
    df = df.sort_values("eventDate")

    df.to_csv(output, index=False)
    print(f"✅ Birleştirilmiş veri kaydedildi: {output}")
    print(f"Toplam kayıt sayısı: {len(df)}")

if __name__ == "__main__":
    merge_afad_usgs()
