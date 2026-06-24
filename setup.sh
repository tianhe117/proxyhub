#!/bin/bash
# ============================================================================
# ProxyHub one-line deployment script (§9)
# ============================================================================
set -e

echo "=== ProxyHub Setup ==="
echo ""

# 1. System dependencies
echo "[1/3] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv curl simple-obfs

# 2. Python environment
echo "[2/3] Setting up Python environment..."
if [ ! -d venv ]; then
    python3 -m venv venv
fi
./venv/bin/pip install -q flask pyyaml

# 3. Directory structure
echo "[3/3] Creating directories..."
mkdir -p bin config data

echo ""
echo "Setup complete."
echo "Run: ./venv/bin/python run.py"
echo "Then open http://<server-ip>:8080"
