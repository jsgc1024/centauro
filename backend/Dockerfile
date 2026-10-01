FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Pango y HarfBuzz: los pide WeasyPrint para el PDF de la cotizacion
# (seccion 114). La letra va adentro del codigo, en app/fuentes; DejaVu
# queda de respaldo para la letra que Inter no trae.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
