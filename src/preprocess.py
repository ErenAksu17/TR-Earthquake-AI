import pandas as pd

def load_and_clean(filepath="data/merged_quakes.xlsx"):
    if filepath.endswith(".xlsx"):
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath)

    df = df.rename(columns={
        "Date": "eventDate",
        "Latitude": "latitude",
        "Longitude": "longitude",
        "Depth": "depth",
        "Magnitude": "magnitude",
        "Location": "location"
    })

    df["eventDate"] = pd.to_datetime(df["eventDate"], errors="coerce")

    df = df[["eventDate", "latitude", "longitude", "depth", "magnitude", "location"]]
    df = df.dropna(subset=["eventDate", "latitude", "longitude", "magnitude"])

    return df