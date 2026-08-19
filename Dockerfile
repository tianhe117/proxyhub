# ProxyHub v2 - multi-stage build
# Stage 1: bundle sing-box binary
# Stage 2: install Python deps + copy app/

# ---------- Stage 1: sing-box binary ----------
FROM python:3.12-slim AS builder

# Download sing-box binary (linux-amd64)
ARG SINGBOX_VERSION=1.13.13
RUN apt-get update && apt-get install -y --no-install-recommends curl tar && \
    curl -L -o /tmp/sing-box.tar.gz \
      "https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-linux-amd64.tar.gz" && \
    tar -xzf /tmp/sing-box.tar.gz -C /tmp && \
    mv /tmp/sing-box-*/sing-box /usr/local/bin/sing-box && \
    chmod +x /usr/local/bin/sing-box && \
    rm -rf /tmp/sing-box*

# ---------- Stage 2: application ----------
FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY run.py .

# Copy sing-box binary from builder
COPY --from=builder /usr/local/bin/sing-box /usr/local/bin/sing-box

# Create runtime directories
RUN mkdir -p data/bin logs

# Expose web UI port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8080/ || exit 1

# Start the application
CMD ["python", "run.py"]
