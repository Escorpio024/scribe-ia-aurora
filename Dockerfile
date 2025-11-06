FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1

# 🔧 Build tools + FFmpeg headers para PyAV
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config curl ca-certificates \
    ffmpeg \
    libavformat-dev libavcodec-dev libavdevice-dev libavfilter-dev \
    libswresample-dev libswscale-dev libavutil-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# (opcional) subir pip
RUN python -m pip install --upgrade pip

COPY api/requirements.txt /app/api/requirements.txt

# 👇 instala primero PyAV 12.x (muchas veces tiene wheel precompilado en aarch64)
#   si no hay wheel, compila (ya tienes toolchain y headers)
RUN python -m pip install "av>=12,<13" || true
RUN python -m pip install --no-cache-dir -r /app/api/requirements.txt

COPY api /app/api

EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]