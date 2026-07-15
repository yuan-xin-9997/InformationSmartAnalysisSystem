#!/usr/bin/env bash
# 查看信息智能分析系统状态 (Linux/macOS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/logs/server.pid"
PORT="${ISAS_SERVER_PORT:-28080}"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" >/dev/null 2>&1; then
    echo "运行中 (PID $PID)"
    if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
      echo "健康检查: OK (http://127.0.0.1:$PORT/api/health)"
    else
      echo "健康检查: 失败 (端口 $PORT 无响应)"
    fi
    exit 0
  else
    echo "PID $PID 未运行"; exit 1
  fi
else
  echo "未运行（无 PID 文件）"; exit 1
fi
