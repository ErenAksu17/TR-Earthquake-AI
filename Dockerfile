# TR Earthquake AI — üretim imajı
# Yalnızca çalışma zamanı için gerekenler kopyalanır; ham veri (Excel'ler ve
# 12 MB'lık küresel fay veritabanı) imaja girmez — bunlar sadece veri yeniden
# inşası için gereklidir ve depoda durur.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# geopandas/shapely/pyarrow manylinux tekerlekleriyle gelir; sistem GDAL gerekmez
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodu ve derlenmiş arayüz
COPY src/ ./src/
COPY app/ ./app/

# Çalışma zamanı veri dosyaları (ham kaynaklar hariç)
COPY data/merged_quakes.parquet \
     data/diri_faylar_simplified.geojson \
     data/yerlesimler.parquet \
     data/toplanma_alanlari.geojson \
     data/dyfi_gozlemler.parquet \
     data/fay_kaynaklari.geojson \
     data/vs30_turkiye.npz \
     ./data/

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
