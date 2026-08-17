# ProxyHub v2 - multi-stage build (deployment layer to be refined):
#   stage 1: bundle sing-box binary
#   stage 2: install Python deps + copy app/
FROM python:3.12-slim

WORKDIR /app
# TODO(deployment layer)
