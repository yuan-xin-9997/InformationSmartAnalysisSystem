#!/usr/bin/env bash
# 停止信息智能分析系统 (Linux/macOS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/logs/server.pid"

# 部署目录属主（如 jenkins）才有写权限；若以其他用户运行，自动 sudo 到属主再执行。
OWNER=$(stat -c %U "$SCRIPT_DIR" 2>/dev/null || true)
if [ -z "${ISAS_NO_SUDO:-}" ] && [ -n "$OWNER" ] && [ "$(id -un)" != "$OWNER" ] && [ "$(id -un)" != "root" ] && command -v sudo >/dev/null 2>&1; then
  exec sudo -u "$OWNER" ISAS_NO_SUDO=1 bash "$0" "$@"
fi

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
