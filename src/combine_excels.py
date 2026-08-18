"""Ham Earthquake_*.xlsx dosyalarını tek katalogda birleştirir.

Not: Earthquake_4/5/6/7 dosyaları büyüklük eşiğine göre alınmış, ÖRTÜŞEN
dışa aktarımlardır (bir M7 depremi dördünde birden yer alır). Tekilleştirme
pipeline.build_merged içinde yapılır.
"""

import logging
import os

import pandas as pd

from src.config import DATA_DIR, PATHS
from src.pipeline import build_merged
from src.preprocess import COLUMN_MAP

log = logging.getLogger(__name__)


def combine_excels(folder: str = None, output: str = None) -> pd.DataFrame:
    folder = folder or DATA_DIR
    output = output or PATHS["merged"]

    frames = []
    for file in sorted(os.listdir(folder)):
        if file.endswith(".xlsx") and "Earthquake_" in file:
            log.info("Yükleniyor: %s", file)
            df = pd.read_excel(os.path.join(folder, file))
            frames.append(df.rename(columns=COLUMN_MAP))

    if not frames:
        log.warning("Birleştirilecek dosya bulunamadı: %s", folder)
        return pd.DataFrame()

    merged = build_merged(frames, output=output)
    log.info("Tüm veriler birleştirildi: %s (%d kayıt)", output, len(merged))
    return merged


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    combine_excels()
