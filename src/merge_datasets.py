"""AFAD + USGS arşiv CSV'lerini tek Parquet kataloğunda birleştirir (dedup dahil)."""

import logging

import pandas as pd

from src.config import PATHS
from src.pipeline import build_merged

log = logging.getLogger(__name__)


def merge_afad_usgs(afad_path: str = None, usgs_path: str = None, output: str = None) -> pd.DataFrame:
    afad_path = afad_path or PATHS["afad_csv"]
    usgs_path = usgs_path or PATHS["usgs_csv"]
    output    = output    or PATHS["merged"]

    df_afad = pd.read_csv(afad_path)
    df_afad["provider"] = "afad"
    df_usgs = pd.read_csv(usgs_path)
    df_usgs["provider"] = "usgs"

    merged = build_merged([df_afad, df_usgs], output=output)
    log.info("Birleşik veri kaydedildi: %s (%d kayıt)", output, len(merged))
    return merged


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    merge_afad_usgs()
