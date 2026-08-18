#!/usr/bin/env bash
# ProxyHub v2 - venv 模式一键初始化：建 venv + 装 requirements + 建运行时目录。
# 部署在 Ubuntu 上使用；Windows 开发环境不跑此脚本。
set -euo pipefail

cd "$(dirname "$0")"

# 1. 创建 venv（若不存在）
if [ ! -d venv ]; then
    echo "[1/3] 创建 venv..."
    python3 -m venv venv
fi

# 2. 安装依赖
echo "[2/3] 安装依赖..."
./venv/bin/pip install -q -r requirements.txt

# 3. 建运行时目录（data/bin 供手动放置 sing-box，logs 供启动日志）
echo "[3/3] 创建 data/bin 与 logs 目录..."
mkdir -p data/bin logs

echo ""
echo "初始化完成。运行 ./start.sh 启动。"
