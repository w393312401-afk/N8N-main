#!/bin/bash
set -u

SOURCE_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CORE_DIR="$PROJECT_DIR/core"
LOG_DIR="$PROJECT_DIR/logs"
RUNTIME_DIR="$PROJECT_DIR/runtime"
STARTUP_LOG="$LOG_DIR/startup.log"
APP_LOG="$LOG_DIR/server.log"
PID_FILE="$RUNTIME_DIR/server.pid"
HOST="127.0.0.1"
PORT="8000"
ADSPOWER_PORT="${ADSPOWER_PORT:-50325}"

mkdir -p "$LOG_DIR" "$RUNTIME_DIR"

ts() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  printf '[%s] %s\n' "$(ts)" "$1" | tee -a "$STARTUP_LOG"
}

fail() {
  log "ERROR: $1"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令: $1"
}

check_python_module() {
  python3 - <<PY >/dev/null 2>&1
import importlib
import sys
mods = ["fastapi", "uvicorn", "requests", "playwright", "python_multipart"]
for name in mods:
    try:
        importlib.import_module(name)
    except Exception:
        sys.exit(1)
sys.exit(0)
PY
}

install_python_dependencies() {
  log "检测到缺少 Python 依赖，开始安装..."
  pip3 install python-multipart playwright fastapi uvicorn requests >>"$STARTUP_LOG" 2>&1 || fail "pip 依赖安装失败，请查看 $STARTUP_LOG"
  python3 -m playwright install chromium >>"$STARTUP_LOG" 2>&1 || fail "Playwright Chromium 安装失败，请查看 $STARTUP_LOG"
}

is_port_in_use() {
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1
}

existing_server_pid() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1
}

ensure_core_layout() {
  [ -d "$CORE_DIR" ] || fail "未找到 core 目录: $CORE_DIR"
  [ -f "$CORE_DIR/app.py" ] || fail "未找到应用入口: $CORE_DIR/app.py"
}

check_adspower_api() {
  if curl -fsS --max-time 2 "http://127.0.0.1:${ADSPOWER_PORT}/status" >/dev/null 2>&1; then
    log "AdsPower 本地 API 可访问: ${ADSPOWER_PORT}"
  else
    log "WARNING: AdsPower 本地 API 当前不可访问: ${ADSPOWER_PORT}。服务仍会启动，但调用相关接口时可能失败。"
  fi
}

write_runtime_metadata() {
  local pid="$1"
  printf '%s\n' "$pid" > "$PID_FILE"
}

start_server() {
  require_cmd python3
  require_cmd pip3
  require_cmd curl
  require_cmd lsof
  require_cmd ffmpeg
  ensure_core_layout

  if is_port_in_use; then
    local pid
    pid="$(existing_server_pid)"
    fail "端口 ${PORT} 已被占用，当前监听 PID: ${pid:-unknown}"
  fi

  if ! check_python_module; then
    install_python_dependencies
  else
    log "Python 依赖检测通过"
  fi

  check_adspower_api

  log "启动 AdsPower All-in-One API"
  log "PROJECT_DIR=$PROJECT_DIR"
  log "CORE_DIR=$CORE_DIR"
  log "APP_LOG=$APP_LOG"

  cd "$CORE_DIR" || fail "无法切换到 $CORE_DIR"
  export PYTHONPATH="$CORE_DIR${PYTHONPATH:+:$PYTHONPATH}"
  export ADSPWR_PROJECT_DIR="$PROJECT_DIR"
  export ADSPWR_LOG_DIR="$LOG_DIR"
  export ADSPWR_RUNTIME_DIR="$RUNTIME_DIR"

  python3 app.py 2>&1 | tee -a "$APP_LOG"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  start_server
fi
