FROM python:3.11-slim

# 1. Install git (and optionally build tools) for pip to fetch Git deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Copy only pyproject.toml (leverages Docker cache)
COPY pyproject.toml .

# 3. Install pip dependencies from pyproject.toml
RUN pip install --upgrade pip \
    && pip install --no-cache-dir .

# 4. Copy your application code
COPY . .

# 5. Expose the port your app uses
EXPOSE 8080

# 6. Launch your FastAPI app with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "deadstream.main:app"]
