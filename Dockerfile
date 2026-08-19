FROM python:3.12-slim

# Install system dependencies for health check
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/proxyhub

# Install Python dependencies (copied at build time for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code is mounted via docker-compose volumes, not copied here.
# This allows git pull updates without rebuilding the image.

EXPOSE 8080

CMD ["python", "run.py"]
