FROM python:3.11-slim

# Setup working directory
WORKDIR /app

# Install git if needed for VCS deps
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

# Copy your application code
COPY requirements.txt .
COPY setup.py .
COPY deadstream/ ./deadstream/

# Install pip dependencies from pyproject.toml
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install -e .

# 5. Expose the port your app uses
EXPOSE 8080

# 6. Launch your FastAPI app with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "deadstream.app:app"]
