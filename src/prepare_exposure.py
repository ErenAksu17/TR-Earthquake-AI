"""
Maruziyet veri setlerini hazırlar (tek seferlik / periyodik çalıştırılır).

1) Yerleşim noktaları — GeoNames TR (CC BY 4.0)
   Yalnızca İDARİ MERKEZLER alınır (PPLC/PPLA/PPLA2/PPLA3): il ve ilçe
   merkezleri. Köy/mahalle kayıtları (PPL) bilinçli olarak DIŞARIDA bırakılır,
   çünkü GeoNames'te büyükşehir ilçeleri hem şehir toplamında hem ayrı kayıtlı
   olduğundan hepsi toplandığında nüfus şişer (İstanbul bbox'ı 25,0 milyon
   verirken gerçek nüfus 15,7 milyondur).

   Ölçülen doğruluk (TÜİK 2023 il nüfuslarına karşı, bu yöntemle):
       İstanbul +3%, Gaziantep +9%, Antalya -11%, İzmir -15%, Ankara -31%,
       Bursa +32%
   Yani il düzeyinde sapma yaklaşık ±%30'dur. Bu veri, nüfus maruziyetini
   KABA BÜYÜKLÜK MERTEBESİ olarak vermek içindir; kesin sayı iddiası taşımaz.

2) Toplanma alanları — OpenStreetMap (ODbL), emergency=assembly_point
   OSM'de Türkiye genelinde ~710 kayıt vardır; AFAD'ın resmî listesi çok daha
   büyüktür. Bu katman TOPLULUK VERİSİDİR ve EKSİKTİR — resmî kaynak yerine
   geçmez, yalnızca "yakında ne var" fikri verir.
"""

import io
import json
import logging
import os
import zipfile

import pandas as pd
import requests

from src.config import DATA_DIR, MAP, PATHS

log = logging.getLogger(__name__)

GEONAMES_URL = "https://download.geonames.org/export/dump/TR.zip"
OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
UA = {"User-Agent": "TR-Earthquake-AI/1.0 (github.com/ErenAksu17/TR-Earthquake-AI)"}

# İdari merkez kodları — nüfus çifte sayımını önlemek için yalnızca bunlar
SEAT_CODES = {"PPLC", "PPLA", "PPLA2", "PPLA3"}


def build_settlements(output: str = None) -> pd.DataFrame:
    """GeoNames TR'den idari merkez yerleşimlerini indirip Parquet'e yazar."""
    output = output or PATHS["settlements"]
    log.info("GeoNames TR indiriliyor…")
    resp = requests.get(GEONAMES_URL, headers=UA, timeout=180)
    resp.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    rows = []
    for line in zf.read("TR.txt").decode("utf-8").splitlines():
        f = line.split("\t")
        if len(f) < 15 or f[6] != "P" or f[7] not in SEAT_CODES:
            continue
        try:
            pop = int(f[14])
        except ValueError:
            continue
        if pop <= 0:
            continue
        rows.append({
            "name": f[1],
            "latitude": float(f[4]),
            "longitude": float(f[5]),
            "fcode": f[7],
            "admin1": f[10],
            "population": pop,
        })

    df = pd.DataFrame(rows)
    lon_min, lat_min, lon_max, lat_max = MAP["turkey_bbox"]
    df = df[df["latitude"].between(lat_min, lat_max) & df["longitude"].between(lon_min, lon_max)]
    df = df.sort_values("population", ascending=False).reset_index(drop=True)

    os.makedirs(os.path.dirname(output), exist_ok=True)
    df.to_parquet(output, index=False)
    log.info("Yerleşim verisi yazıldı: %s (%d nokta, %s kişi)",
             output, len(df), f"{df['population'].sum():,}")
    return df


def build_assembly_points(output: str = None) -> dict:
    """OSM'den toplanma alanlarını indirip GeoJSON olarak yazar."""
    output = output or PATHS["shelters"]
    lon_min, lat_min, lon_max, lat_max = MAP["turkey_bbox"]
    query = f"""[out:json][timeout:240];
(node["emergency"="assembly_point"]({lat_min},{lon_min},{lat_max},{lon_max});
 way["emergency"="assembly_point"]({lat_min},{lon_min},{lat_max},{lon_max}););
out center;"""

    elements = None
    for mirror in OVERPASS_MIRRORS:
        try:
            r = requests.post(mirror, data={"data": query}, headers=UA, timeout=300)
            if r.status_code == 200:
                elements = r.json().get("elements", [])
                log.info("Overpass yanıtı alındı (%s): %d kayıt", mirror, len(elements))
                break
            log.warning("Overpass %s → HTTP %d", mirror, r.status_code)
        except requests.exceptions.RequestException as e:
            log.warning("Overpass %s hatası: %s", mirror, e)

    if elements is None:
        raise ConnectionError("Hiçbir Overpass aynasına ulaşılamadı.")

    features = []
    for el in elements:
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": tags.get("name", ""),
                "operator": tags.get("operator", ""),
                "osm_id": f"{el.get('type')}/{el.get('id')}",
            },
        })

    fc = {
        "type": "FeatureCollection",
        "properties": {
            "source": "OpenStreetMap (ODbL)",
            "note": "Topluluk verisi — EKSİKTİR, AFAD resmî listesi değildir.",
            "count": len(features),
        },
        "features": features,
    }
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False)
    log.info("Toplanma alanları yazıldı: %s (%d nokta)", output, len(features))
    return fc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    build_settlements()
    build_assembly_points()
