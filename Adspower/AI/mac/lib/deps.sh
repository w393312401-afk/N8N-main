#!/bin/bash
set -uo pipefail
# ==============================================================================
# 📦 deps.sh — 依赖检测与安装
# ==============================================================================

# --- 依赖缓存标记 ---
DEPS_MARKER="$RUNTIME_DIR/.deps_checked"
DEPS_CACHE_MINUTES=60

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: 缺少命令: $1，请先安装"
    exit 1
  fi
}

check_python_module() {
  python3 - <<'PY' >/dev/null 2>&1
import importlib, sys
modules = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "requests": "requests",
    "playwright": "playwright",
    "multipart": "python_multipart",
    "dotenv": "dotenv",
}
failed = []
for display_name, mod_name in modules.items():
    try:
        importlib.import_module(mod_name)
    except Exception:
        failed.append(display_name)
if failed:
    print(f"Missing: {', '.join(failed)}", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PY
}

install_python_dependencies() {
  log "检测到缺少 Python 依赖，开始安装..."
  pip3 install python-multipart playwright fastapi uvicorn requests python-dotenv \
    >>"$STARTUP_LOG" 2>&1 || { log "ERROR: pip 依赖安装失败，请查看 $STARTUP_LOG"; exit 1; }
  python3 -m playwright install chromium \
    >>"$STARTUP_LOG" 2>&1 || { log "ERROR: Playwright Chromium 安装失败，请查看 $STARTUP_LOG"; exit 1; }
}

check_all_deps() {
  # 如果缓存标记存在且在有效期内，跳过检测
  if [ -f "$DEPS_MARKER" ]; then
    local marker_age
    marker_age="$(find "$DEPS_MARKER" -mmin -"$DEPS_CACHE_MINUTES" 2>/dev/null)"
    if [ -n "$marker_age" ]; then
      log "依赖检测跳过（${DEPS_CACHE_MINUTES} 分钟内已检测通过）"
      return 0
    fi
  fi

  require_cmd python3
  require_cmd pip3
  require_cmd curl
  require_cmd lsof
  require_cmd ffmpeg

  if ! check_python_module; then
    install_python_dependencies
  else
    log "Python 依赖检测通过"
  fi

  # 写入缓存标记
  touch "$DEPS_MARKER"
}
