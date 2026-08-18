"""Veri temizleme — pipeline.clean üzerine ince bir sarmalayıcı."""

import pandas as pd

from src.config import PATHS
from src.pipeline import clean

COLUMN_MAP = {
    "Date": "eventDate",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Depth": "depth",
    "Magnitude": "magnitude",
    "Location": "location",
}


def load_and_clean(filepath: str = None) -> pd.DataFrame:
    filepath = filepath or PATHS["merged"]
    if filepath.endswith(".parquet"):
        df = pd.read_parquet(filepath)
    elif filepath.endswith(".xlsx"):
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath)

    df = df.rename(columns=COLUMN_MAP)
    df = clean(df)
    cols = [c for c in ["eventDate", "latitude", "longitude", "depth", "magnitude", "location", "provider"] if c in df.columns]
    return df[cols]
