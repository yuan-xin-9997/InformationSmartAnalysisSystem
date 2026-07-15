#!/usr/bin/env bash
# 启动信息智能分析系统 (Linux/macOS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 部署目录属主（如 jenkins）才有写权限；若以其他用户运行，自动 sudo 到属主再执行。
OWNER=$(stat -c %U "$SCRIPT_DIR" 2>/dev/null || true)
if [ -z "${ISAS_NO_SUDO:-}" ] && [ -n "$OWNER" ] && [ "$(id -un)" != "$OWNER" ] && [ "$(id -un)" != "root" ] && command -v sudo >/dev/null 2>&1; then
  exec sudo -u "$OWNER" ISAS_NO_SUDO=1 bash "$0" "$@"
fi

VENV="${ISAS_VENV:-$SCRIPT_DIR/.venv}"
PYTHON="$VENV/bin/python"
LOG_DIR="$SCRIPT_DIR/logs"
DATA_DIR="$SCRIPT_DIR/data"
PID_FILE="$LOG_DIR/server.pid"

mkdir -p "$LOG_DIR" "$DATA_DIR" "$DATA_DIR/downloads"

# 首次部署：创建默认 password.txt
if [ ! -f "$DATA_DIR/password.txt" ]; then
  cat > "$DATA_DIR/password.txt" <<'EOF'
# 格式: username:password:role  (role 取值: admin | user)
# admin 默认拥有所有页面权限；user 的可见页面由管理员在权限管理页配置。
# 修改本文件后，新用户在下次登录时会自动同步到数据库。
admin:admin123:admin
EOF
  echo "已创建默认 $DATA_DIR/password.txt"
fi

# 虚拟环境 + 依赖
if [ ! -x "$PYTHON" ]; then
  echo "创建虚拟环境 $VENV ..."
  python3 -m venv "$VENV"
fi
if ! "$PYTHON" -c "import fastapi" >/dev/null 2>&1; then
  echo "安装后端依赖 ..."
  "$PYTHON" -m pip install --upgrade pip -q
  "$PYTHON" -m pip install -r "$SCRIPT_DIR/app/backend/requirements.txt" -q
fi

# 前端构建（dist 不存在且 npm 可用时）
if [ ! -d "$SCRIPT_DIR/app/frontend/dist" ] && command -v npm >/dev/null 2>&1; then
  echo "构建前端 ..."
  (cd "$SCRIPT_DIR/app/frontend" && npm install --no-audit --no-fund && npm run build) \
    || echo "警告: 前端构建失败，将仅提供后端 API"
fi

# 已在运行则提示
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  echo "服务已在运行 (PID $(cat "$PID_FILE"))"; exit 0
fi

HOST="${ISAS_SERVER_HOST:-0.0.0.0}"
# 端口优先取 ISAS_SERVER_PORT 环境变量；否则读 config/app.json；均失败回落 28080
if [ -z "${ISAS_SERVER_PORT:-}" ]; then
  ISAS_SERVER_PORT=$(python3 -c "import json;print(json.load(open('$SCRIPT_DIR/config/app.json'))['server']['port'])" 2>/dev/null || echo 28080)
fi
PORT="$ISAS_SERVER_PORT"
nohup "$PYTHON" -m uvicorn app.backend.main:app --host "$HOST" --port "$PORT" \
  > "$LOG_DIR/server.out" 2>&1 &
echo $! > "$PID_FILE"
echo "服务已启动 (PID $(cat "$PID_FILE"))，监听 $HOST:$PORT"
