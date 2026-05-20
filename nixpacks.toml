FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libexpat1 \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    libgeos-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .

RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

COPY backend/ .

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}