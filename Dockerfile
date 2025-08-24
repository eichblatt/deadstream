FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Install system deps (git for yourlib)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# 2. Copy pyproject, build & install
COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install --no-cache-dir .

# 3. Copy source and start Gunicorn
COPY . .
CMD ["gunicorn", "--bind", "0.0.0.0:${PORT}", "--workers", "2", "main:app"]
