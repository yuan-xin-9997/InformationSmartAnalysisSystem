#!/usr/bin/env bash
# 停止信息智能分析系统 (Linux/macOS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/logs/server.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "未找到 PID 文件，服务可能未运行"; exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" >/dev/null 2>&1; then
  kill "$PID" 2>/dev/null || true
  sleep 2
  if kill -0 "$PID" >/dev/null 2>&1; then
    kill -9 "$PID" 2>/dev/null || true
  fi
  echo "已停止服务 (PID $PID)"
else
  echo "进程 $PID 未运行"
fi
rm -f "$PID_FILE"
