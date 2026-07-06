#!/bin/bash
# ==============================================================================
# 🚀 server.sh — 进程管理 (启动 / 停止 / 状态)
# 依赖: 必须先 source env.sh
# ==============================================================================

# --- 颜色定义 ---
if [ -t 1 ]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
  CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; DIM=''; NC=''
fi

# --- 日志工具 ---
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { printf '[%s] %s\n' "$(ts)" "$1" | tee -a "$STARTUP_LOG"; }

# --- 日志轮转 ---
rotate_log() {
  local file="$1" max_size="${2:-10485760}"  # 默认 10MB
  if [ -f "$file" ]; then
    local file_size
    file_size="$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)"
    if [ "$file_size" -gt "$max_size" ]; then
      mv "$file" "${file}.$(date +%Y%m%d%H%M%S).bak"
      log "日志已轮转: $file"
    fi
  fi
}

# --- 进程查询 ---
service_pid() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1
}

service_command() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  ps -p "$pid" -o command= 2>/dev/null
}

is_port_in_use() {
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1
}

service_pids() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u
}

pid_cwd() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

pid_in_core_dir() {
  local pid="$1"
  [ "$(pid_cwd "$pid")" = "$CORE_DIR" ]
}

project_process_pids() {
  local pids pid
  pids="$(pgrep -f 'app\.py|uvicorn|watchfiles' 2>/dev/null)" || return 0
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    pid_in_core_dir "$pid" && printf '%s\n' "$pid"
  done <<< "$pids"
}

child_pids_of() {
  local parent_pid="$1"
  pgrep -P "$parent_pid" 2>/dev/null | sort -u
}

descendant_pids_of() {
  local root_pid="$1"
  local child_pid children
  children="$(child_pids_of "$root_pid")"
  [ -n "$children" ] || return 0
  printf '%s\n' "$children"
  while IFS= read -r child_pid; do
    [ -n "$child_pid" ] || continue
    descendant_pids_of "$child_pid"
  done <<< "$children"
}

service_related_pids() {
  local seed_pids all_pids pid

  seed_pids="$(printf '%s\n%s\n' "$(service_pids)" "$(project_process_pids)" | awk 'NF { print }' | sort -u)"
  all_pids="$seed_pids"

  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    all_pids="$(printf '%s\n%s\n' "$all_pids" "$(descendant_pids_of "$pid")")"
  done <<< "$seed_pids"

  printf '%s\n' "$all_pids" | awk 'NF { print }' | sort -u
}

terminate_service_processes() {
  local signal="${1:-TERM}"
  local pids pid

  pids="$(service_related_pids)"
  [ -n "$pids" ] || return 1

  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    kill "-$signal" "$pid" 2>/dev/null || true
  done <<< "$pids"

  return 0
}

# --- PID 文件管理 ---
write_pid_file() {
  local pid="$1"
  echo "$pid" > "$PID_FILE"
}

read_pid_file() {
  [ -f "$PID_FILE" ] && cat "$PID_FILE" 2>/dev/null
}

clean_pid_file() {
  rm -f "$PID_FILE" 2>/dev/null
}

# --- 检查进程是否存活 ---
any_pid_alive() {
  local pids="$1" pid
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    kill -0 "$pid" 2>/dev/null && return 0
  done <<< "$pids"
  return 1
}

# --- 状态打印 ---
print_status() {
  local pid
  pid="$(service_pid)"
  if [ -n "$pid" ]; then
    echo -e "当前状态: ${GREEN}● 运行中${NC} (PID: ${BOLD}$pid${NC})"
    echo -e "  ${DIM}$(service_command "$pid")${NC}"
  else
    echo -e "当前状态: ${RED}● 未运行${NC}"
  fi
}

# --- 停止服务 ---
wait_for_port_release() {
  local retries="${1:-20}"
  while [ "$retries" -gt 0 ]; do
    is_port_in_use || return 0
    sleep 0.5
    retries=$((retries - 1))
  done
  return 1
}

stop_service() {
  local pids pid
  pids="$(service_related_pids)"

  if [ -n "$pids" ]; then
    echo "准备停止以下服务相关进程:"
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      echo -e "  PID: ${BOLD}$pid${NC} — $(service_command "$pid")"
    done <<< "$pids"

    terminate_service_processes TERM

    # 用 kill -0 检查缓存的 PID 是否还存活，避免反复扫描进程树
    for _ in {1..20}; do
      if ! any_pid_alive "$pids"; then
        clean_pid_file
        echo -e "${GREEN}✓ 已停止所有服务相关进程${NC}"
        return 0
      fi
      sleep 0.5
    done

    echo -e "${YELLOW}普通停止超时，尝试 SIGKILL ...${NC}"
    terminate_service_processes KILL
    sleep 1
    if ! any_pid_alive "$pids"; then
      clean_pid_file
      echo -e "${GREEN}✓ 已强制停止所有服务相关进程${NC}"
    else
      echo -e "${RED}✗ 停止失败，仍有残留进程:${NC}"
      local remain
      remain="$(service_related_pids)"
      while IFS= read -r pid; do
        [ -n "$pid" ] || continue
        echo -e "  PID: ${BOLD}$pid${NC} — $(service_command "$pid")"
      done <<< "$remain"
      return 1
    fi
  else
    echo "当前没有检测到运行中的服务相关进程"
  fi
}

force_interrupt_service() {
  local combined_pids=""

  combined_pids="$(service_related_pids)"
  if [ -z "$combined_pids" ]; then
    echo "当前没有检测到需要彻底中断的服务进程"
    return 0
  fi

  echo "准备彻底中断以下进程:"
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    echo -e "  PID: ${BOLD}$pid${NC} — $(service_command "$pid")"
  done <<< "$combined_pids"

  terminate_service_processes KILL
  sleep 1

  if ! any_pid_alive "$combined_pids"; then
    clean_pid_file
    echo -e "${GREEN}✓ 已彻底中断服务相关进程${NC}"
  else
    echo -e "${RED}✗ 仍有残留进程，请手动检查:${NC}"
    local remain_pids
    remain_pids="$(service_related_pids)"
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      echo -e "  PID: ${BOLD}$pid${NC} — $(service_command "$pid")"
    done <<< "$remain_pids"
    return 1
  fi
}

stop_existing_if_needed() {
  local pids pid
  pids="$(service_related_pids)"
  [ -n "$pids" ] || return 0

  log "检测到旧的服务相关进程，准备启动前清理:"
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    log "清理 PID=$pid"
    service_command "$pid"
  done <<< "$pids"

  terminate_service_processes TERM
  for _ in {1..20}; do
    if ! any_pid_alive "$pids" && ! is_port_in_use; then
      clean_pid_file
      log "旧进程已停止，端口 ${PORT} 已释放"
      return 0
    fi
    sleep 0.5
  done

  log "普通停止未完全释放端口，尝试强制结束残留进程"
  terminate_service_processes KILL
  sleep 1

  if ! any_pid_alive "$pids" && ! is_port_in_use; then
    clean_pid_file
    log "旧进程已强制停止，端口 ${PORT} 已释放"
  else
    log "ERROR: 无法释放端口 ${PORT}，请手动检查以下残留进程"
    local remain
    remain="$(service_related_pids)"
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      log "残留 PID=$pid"
      service_command "$pid"
    done <<< "$remain"
    exit 1
  fi
}

# --- 检查 AdsPower API ---
check_adspower_api() {
  if curl -fsS --max-time 2 "http://127.0.0.1:${ADSPOWER_PORT}/status" >/dev/null 2>&1; then
    log "AdsPower 本地 API 可访问: ${ADSPOWER_PORT}"
    return 0
  else
    log "WARNING: AdsPower 本地 API 当前不可访问: ${ADSPOWER_PORT}。服务仍会启动，但调用相关接口时可能失败。"
    return 1
  fi
}

# --- 健康检查 ---
health_check() {
  echo ""
  echo -e "${BOLD}--- API 服务 ---${NC}"
  if curl -fsS --max-time 3 "http://${HOST}:${PORT}/" >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} API 服务正常 (${HOST}:${PORT})"
  else
    echo -e "  ${RED}✗${NC} API 服务不可达 (${HOST}:${PORT})"
  fi

  echo -e "${BOLD}--- AdsPower ---${NC}"
  if curl -fsS --max-time 2 "http://127.0.0.1:${ADSPOWER_PORT}/status" >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} AdsPower API 正常 (127.0.0.1:${ADSPOWER_PORT})"
  else
    echo -e "  ${RED}✗${NC} AdsPower API 不可达 (127.0.0.1:${ADSPOWER_PORT})"
  fi

  local pid
  pid="$(service_pid)"
  echo -e "${BOLD}--- 系统资源 ---${NC}"
  if [ -n "$pid" ]; then
    local mem cpu
    mem="$(ps -p "$pid" -o rss= 2>/dev/null | xargs)"
    cpu="$(ps -p "$pid" -o %cpu= 2>/dev/null | xargs)"
    if [ -n "$mem" ]; then
      echo -e "  内存: ${BOLD}$((mem / 1024)) MB${NC}  CPU: ${BOLD}${cpu}%${NC}"
    fi
  else
    echo -e "  ${DIM}服务未运行，无法获取资源信息${NC}"
  fi
  echo ""
}

# --- 实时日志 ---
tail_log() {
  local log_file="${1:-$APP_LOG}"
  if [ -f "$log_file" ]; then
    echo -e "${DIM}按 Ctrl+C 返回菜单...${NC}"
    echo ""
    tail -f "$log_file" 2>/dev/null
  else
    echo -e "${YELLOW}⚠️ 日志文件不存在: $log_file${NC}"
  fi
}

# --- 启动服务 ---
start_server() {
  local mode_name="${1:-stable}"

  [ -d "$CORE_DIR" ] || { log "ERROR: 未找到 core 目录: $CORE_DIR"; exit 1; }
  [ -f "$CORE_DIR/app.py" ] || { log "ERROR: 未找到应用入口: $CORE_DIR/app.py"; exit 1; }

  if is_port_in_use || [ -n "$(project_process_pids)" ]; then
    stop_existing_if_needed
  fi

  # 日志轮转（覆盖 logs/ 下所有 .log，含外部写入的 nohup 日志）
  for _logf in "$LOG_DIR"/*.log; do
    [ -e "$_logf" ] && rotate_log "$_logf"
  done

  check_all_deps
  check_adspower_api

  log "启动 AdsPower All-in-One API"
  log "MODE=$mode_name"
  log "PROJECT_DIR=$PROJECT_DIR"
  log "CORE_DIR=$CORE_DIR"
  log "APP_LOG=$APP_LOG"

  cd "$CORE_DIR" || { log "ERROR: 无法切换到 $CORE_DIR"; exit 1; }
  export PYTHONPATH="$CORE_DIR${PYTHONPATH:+:$PYTHONPATH}"
  export ADSPWR_PROJECT_DIR="$PROJECT_DIR"
  export ADSPWR_LOG_DIR="$LOG_DIR"
  export ADSPWR_RUNTIME_DIR="$RUNTIME_DIR"
  export ADSPWR_RELOAD
  export PYTHONUNBUFFERED=1

  log "前台日志输出已开启，可同时查看终端与 $APP_LOG"
  python3 -u app.py > >(tee -a "$APP_LOG") 2> >(tee -a "$APP_LOG" >&2)
  local exit_code=$?
  clean_pid_file
  return $exit_code
}
