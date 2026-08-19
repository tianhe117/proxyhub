#!/usr/bin/env bash
# ProxyHub v2 - venv mode initialization script
# Creates virtual environment, installs dependencies, and sets up runtime directories.
# For Ubuntu deployment; Windows dev environments should not run this script.
set -euo pipefail

cd "$(dirname "$0")"

# 1. Create virtual environment (if not exists)
if [ ! -d venv ]; then
    echo "[1/3] Creating virtual environment..."
    python3 -m venv venv
fi

# 2. Install dependencies
echo "[2/3] Installing dependencies..."
./venv/bin/pip install -q -r requirements.txt

# 3. Create runtime directories (data/bin for sing-box binary, logs for startup logs)
echo "[3/3] Creating data/bin and logs directories..."
mkdir -p data/bin logs

echo ""
echo "Initialization complete. Run ./start.sh to start the application."
