#!/usr/bin/env bash
# 前台运行 uvicorn，供 systemd 使用。
# 端口取自 ISAS_SERVER_PORT 环境变量，否则读 config/app.json，均失败回落 28080。
# 与 start.sh 的区别：本脚本不后台化、不写 PID，直接 exec 让 systemd 跟踪主进程。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="${ISAS_VENV:-$SCRIPT_DIR/.venv}"
PYTHON="$VENV/bin/python"

if [ -z "${ISAS_SERVER_PORT:-}" ]; then
  ISAS_SERVER_PORT=$(python3 -c "import json;print(json.load(open('$SCRIPT_DIR/config/app.json'))['server']['port'])" 2>/dev/null || echo 28080)
fi
HOST="${ISAS_SERVER_HOST:-0.0.0.0}"

exec "$PYTHON" -m uvicorn app.backend.main:app --host "$HOST" --port "$ISAS_SERVER_PORT"
