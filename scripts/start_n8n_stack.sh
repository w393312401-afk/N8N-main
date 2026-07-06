#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/runtime"
N8N_ENV_FILE="${N8N_ENV_FILE:-$HOME/.n8n/n8n.env}"
N8N_HOST="127.0.0.1"
N8N_PORT="5678"
N8N_URL="http://${N8N_HOST}:${N8N_PORT}"
N8N_LOG="$RUNTIME_DIR/n8n.log"
N8N_ERR_LOG="$RUNTIME_DIR/n8n.err.log"
N8N_PID_FILE="$RUNTIME_DIR/n8n.pid"
N8N_BIN="${N8N_BIN:-$HOME/.local/bin/n8n}"
LAUNCHD_LOG_DIR="$HOME/Library/Logs/N8N-main"
LAUNCHD_OUT_LOG="$LAUNCHD_LOG_DIR/n8n.log"
LAUNCHD_ERR_LOG="$LAUNCHD_LOG_DIR/n8n.err.log"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LAUNCH_AGENT_LABEL="com.fly.n8n.background"
LAUNCH_AGENT_PLIST="$LAUNCH_AGENT_DIR/${LAUNCH_AGENT_LABEL}.plist"
LAUNCHCTL_DOMAIN="gui/$(id -u)"

mkdir -p "$RUNTIME_DIR"

load_n8n_env_if_present() {
  if [ -f "$N8N_ENV_FILE" ]; then
    # shellcheck disable=SC1090
    set -a
    source "$N8N_ENV_FILE"
    set +a
  fi
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

http_ready() {
  local url="$1"
  curl -fsS --max-time 2 "$url" >/dev/null 2>&1
}

wait_for_http() {
  local url="$1"
  local timeout="${2:-60}"
  local elapsed=0

  until http_ready "$url"; do
    sleep 1
    elapsed=$((elapsed + 1))
    if [ "$elapsed" -ge "$timeout" ]; then
      return 1
    fi
  done
}

write_launch_agent() {
  mkdir -p "$LAUNCH_AGENT_DIR"
  mkdir -p "$LAUNCHD_LOG_DIR"
  cat > "$LAUNCH_AGENT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LAUNCH_AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>export HOME='${HOME}'; export USER='$(id -un)'; export LOGNAME='$(id -un)'; export PATH='${HOME}/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'; set -a; [ -f '${N8N_ENV_FILE}' ] &amp;&amp; . '${N8N_ENV_FILE}'; set +a; export NODE_FUNCTION_ALLOW_BUILTIN="\${NODE_FUNCTION_ALLOW_BUILTIN:-os,path,fs,http,https,url,child_process}"; export N8N_RUNNERS_TASK_REQUEST_TIMEOUT="\${N8N_RUNNERS_TASK_REQUEST_TIMEOUT:-7200}"; export N8N_RUNNERS_TASK_TIMEOUT="\${N8N_RUNNERS_TASK_TIMEOUT:-7200}"; export EXTERNAL_HOOK_FILES="\${EXTERNAL_HOOK_FILES:-${ROOT_DIR}/scripts/n8n_hooks.js}"; cd '${HOME}'; exec '${N8N_BIN}' start</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${HOME}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LAUNCHD_OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${LAUNCHD_ERR_LOG}</string>
</dict>
</plist>
PLIST
}

launch_agent_loaded() {
  launchctl print "${LAUNCHCTL_DOMAIN}/${LAUNCH_AGENT_LABEL}" >/dev/null 2>&1
}

start_n8n_if_needed() {
  load_n8n_env_if_present
  write_launch_agent

  if ! launch_agent_loaded; then
    log "启动 n8n 后台服务（LaunchAgent，24小时保持运行）: ${N8N_URL}"
    launchctl bootstrap "$LAUNCHCTL_DOMAIN" "$LAUNCH_AGENT_PLIST" 2>/dev/null || true
  fi

  launchctl kickstart -k "${LAUNCHCTL_DOMAIN}/${LAUNCH_AGENT_LABEL}" >/dev/null 2>&1 || true

  if wait_for_http "$N8N_URL" 90; then
    local n8n_pid
    n8n_pid="$(pgrep -f "n8n start" | head -n 1 || true)"
    [ -n "$n8n_pid" ] && echo "$n8n_pid" > "$N8N_PID_FILE"
    log "n8n 已就绪并在后台保持运行: ${N8N_URL}"
  else
    log "n8n 启动失败，请检查日志: $LAUNCHD_OUT_LOG / $LAUNCHD_ERR_LOG"
    exit 1
  fi
}

print_status() {
  if http_ready "$N8N_URL"; then
    log "n8n: RUNNING ${N8N_URL}"
  else
    log "n8n: STOPPED ${N8N_URL}"
  fi

  if launch_agent_loaded; then
    log "后台守护: ENABLED ${LAUNCH_AGENT_LABEL}"
  else
    log "后台守护: DISABLED ${LAUNCH_AGENT_LABEL}"
  fi
}

stop_n8n_stack() {
  log "开始停止 n8n 后台服务..."

  if launch_agent_loaded; then
    log "正在卸载后台守护: ${LAUNCH_AGENT_LABEL}"
    launchctl bootout "$LAUNCHCTL_DOMAIN" "$LAUNCH_AGENT_PLIST" 2>/dev/null || true
  fi

  log "正在停止 n8n 服务..."
  if [ -f "$N8N_PID_FILE" ]; then
    local n8n_pid
    n8n_pid="$(cat "$N8N_PID_FILE" 2>/dev/null || true)"
    if [ -n "$n8n_pid" ]; then
      if kill -0 "$n8n_pid" 2>/dev/null; then
        log "正在停止 n8n (PID: $n8n_pid)..."
        kill "$n8n_pid" 2>/dev/null || true
        # 等待最多 10 秒让其退出
        for _ in {1..10}; do
          if ! kill -0 "$n8n_pid" 2>/dev/null; then
            break
          fi
          sleep 1
        done
        # 如果还在运行，强杀
        if kill -0 "$n8n_pid" 2>/dev/null; then
          log "n8n 未能优雅退出，正在强制结束 (PID: $n8n_pid)..."
          kill -9 "$n8n_pid" 2>/dev/null || true
        fi
      fi
    fi
    rm -f "$N8N_PID_FILE"
  fi

  # 兜底清理：检查是否有其他残留的 n8n 进程
  local residual_n8n_pids
  residual_n8n_pids="$(pgrep -f "n8n start" 2>/dev/null || true)"
  if [ -n "$residual_n8n_pids" ]; then
    log "检测到残留 n8n 进程，正在清理..."
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      log "结束残留 n8n 进程 (PID: $pid)"
      kill -9 "$pid" 2>/dev/null || true
    done <<< "$residual_n8n_pids"
  fi

  # 停止 flow2api 后台服务并清理相关进程
  log "正在停止 flow2api 服务与相关后台进程..."
  local flow2api_plist="$HOME/Library/LaunchAgents/com.local.flow2api.plist"
  if [ -f "$flow2api_plist" ]; then
    launchctl unload "$flow2api_plist" 2>/dev/null || true
  fi

  # 精准终止端口占用
  local flow2api_pids
  flow2api_pids="$(lsof -t -i :8080 2>/dev/null || true)"
  if [ -n "$flow2api_pids" ]; then
    for pid in $flow2api_pids; do
      kill -9 "$pid" 2>/dev/null || true
    done
  fi

  # 查杀后台残留的 python main.py 进程
  local flow2api_py_pids
  flow2api_py_pids="$(pgrep -f "python.*main\.py" 2>/dev/null || true)"
  if [ -n "$flow2api_py_pids" ]; then
    for pid in $flow2api_py_pids; do
      kill -9 "$pid" 2>/dev/null || true
    done
  fi

  # 查杀 uvicorn 进程
  local uvicorn_pids
  uvicorn_pids="$(pgrep -f "uvicorn.*src\.main" 2>/dev/null || true)"
  if [ -n "$uvicorn_pids" ]; then
    for pid in $uvicorn_pids; do
      kill -9 "$pid" 2>/dev/null || true
    done
  fi

  # 查杀 chromium 进程
  local chrome_pids
  chrome_pids="$(pgrep -f "chromium.*--remote-debugging" 2>/dev/null || true)"
  if [ -n "$chrome_pids" ]; then
    for pid in $chrome_pids; do
      kill -9 "$pid" 2>/dev/null || true
    done
  fi

  # 清理 pid 文件
  rm -f "/Users/fly/.gemini/antigravity-ide/scratch/flow2api/flow2api_server.pid" 2>/dev/null || true

  log "N8N 堆栈所有服务与 flow2api 后台进程已停止"
  print_status
}

case "${1:-start}" in
  start)
    start_n8n_if_needed
    print_status
    ;;
  status)
    print_status
    ;;
  stop|clean|cleanup)
    stop_n8n_stack
    ;;
  *)
    echo "用法: $0 [start|status|stop]"
    exit 1
    ;;
esac
