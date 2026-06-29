FROM ubuntu:22.04

LABEL maintainer="liruixiang"
LABEL description="ProxyHub - Proxy service management panel"

ENV DEBIAN_FRONTEND=noninteractive

# ── System dependencies ──────────────────────────────────────────
# Ubuntu 22.04 的官方源里自带 python3、pip 和 simple-obfs
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        curl \
        simple-obfs \
        procps \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ──────────────────────────────────────────
WORKDIR /opt/proxyhub
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

EXPOSE 8080

# 对应 ubuntu 的 python3 命令
CMD ["python3", "run.py"]