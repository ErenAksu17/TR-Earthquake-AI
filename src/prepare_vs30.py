"""
Zemin verisi — USGS küresel Vs30 ızgarasının Türkiye penceresi.

Vs30, üstteki 30 metrenin ortalama kayma dalgası hızıdır ve sarsıntının zemin
tarafından ne kadar büyütüleceğini belirleyen standart parametredir. Düşük Vs30
(yumuşak alüvyon) sarsıntıyı büyütür; yüksek Vs30 (kaya) söndürür.

Kaynak: USGS "global_vs30.grd" (Heath vd. 2020), 30 yay-saniye ≈ 1 km çözünürlük.
Dosya 610 MB'tır ancak HDF5 biçiminde 129×129 parçalar hâlinde saklandığı ve
sunucu HTTP aralık isteklerini desteklediği için YALNIZCA Türkiye penceresi
indirilir (~2400×960 hücre).

ÖNEMLİ SINIR — bu bir mikrobölgeleme verisi DEĞİLDİR:
Küresel Vs30 haritası ağırlıklı olarak TOPOĞRAFİK EĞİMDEN türetilmiş bir vekil
değerdir (Wald & Allen 2007); sondaj ölçümü değildir. Yaklaşık 1 km çözünürlük,
şehir ölçeğinde genel bir fikir verir ama parsel/bina ölçeğinde geçerli değildir.
Bir yapının zemin sınıfı için resmî zemin etüdü gerekir.
"""

import logging
import os

import numpy as np

from src.config import MAP, PATHS, VS30

log = logging.getLogger(__name__)

GLOBAL_VS30_URL = "https://apps.usgs.gov/shakemap_geodata/vs30/global_vs30.grd"


def build_vs30(output: str = None, url: str = GLOBAL_VS30_URL) -> dict:
    """Küresel ızgaradan Türkiye penceresini çekip sıkıştırılmış olarak kaydeder."""
    import fsspec
    import h5py

    output = output or PATHS["vs30"]
    lon_min, lat_min, lon_max, lat_max = MAP["turkey_bbox"]
    pad = VS30["pad_deg"]

    log.info("Küresel Vs30 ızgarası uzaktan açılıyor…")
    handle = fsspec.open(url, mode="rb", block_size=2 ** 20).open()
    with h5py.File(handle, "r") as h5:
        lon = h5["lon"][:]
        lat = h5["lat"][:]
        i0, i1 = np.searchsorted(lat, [lat_min - pad, lat_max + pad])
        j0, j1 = np.searchsorted(lon, [lon_min - pad, lon_max + pad])
        log.info("Pencere: %d satır × %d sütun", i1 - i0, j1 - j0)
        grid = h5["z"][i0:i1, j0:j1].astype("float32")
        lat_win = lat[i0:i1].astype("float64")
        lon_win = lon[j0:j1].astype("float64")

    valid = np.isfinite(grid) & (grid > 0)
    log.info("Vs30 aralığı: %.0f – %.0f m/s (geçerli hücre %%%.1f)",
             float(grid[valid].min()), float(grid[valid].max()), 100 * valid.mean())

    # uint16 yeterli (Vs30 ~100–2200 m/s); dosya boyutunu yarıya indirir
    packed = np.clip(np.nan_to_num(grid, nan=0.0), 0, 65535).astype("uint16")

    os.makedirs(os.path.dirname(output), exist_ok=True)
    np.savez_compressed(output, vs30=packed, lat=lat_win, lon=lon_win)
    size_mb = os.path.getsize(output) / 1e6
    log.info("Vs30 penceresi yazıldı: %s (%.2f MB)", output, size_mb)
    return {"rows": int(grid.shape[0]), "cols": int(grid.shape[1]), "size_mb": round(size_mb, 2)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    build_vs30()
