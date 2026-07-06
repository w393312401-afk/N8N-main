#!/bin/bash
SOURCE_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
RUNTIME_DIR="$PROJECT_DIR/runtime"
APP_SUPPORT_DIR="$HOME/Library/Application Support/AdsPowerAIService"
SERVICE_ROOT="$APP_SUPPORT_DIR/current"
SERVICE_PROJECT_DIR="$SERVICE_ROOT/Adspower/AI"
SERVICE_START_SCRIPT="$SERVICE_PROJECT_DIR/mac/start_server.sh"
SERVICE_LOG_DIR="$SERVICE_PROJECT_DIR/logs"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/com.fly.adspower.ai.api.plist"
LABEL="com.fly.adspower.ai.api"
START_SCRIPT="$SCRIPT_DIR/start_server.sh"
STARTUP_LOG="$LOG_DIR/startup.log"
APP_LOG="$LOG_DIR/server.log"
SERVICE_LOG="$SERVICE_LOG_DIR/launchd.log"
ERROR_LOG="$SERVICE_LOG_DIR/launchd.error.log"
PORT="8000"

mkdir -p "$LOG_DIR" "$RUNTIME_DIR" "$LAUNCH_AGENTS_DIR" "$APP_SUPPORT_DIR"

CYAN='\033[96m'
GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
BOLD='\033[1m'
RESET='\033[0m'

service_pid() {
  lsof -tiTCP:$PORT -sTCP:LISTEN 2>/dev/null | head -n 1
}

service_running() {
  [ -n "$(service_pid)" ]
}

health_status() {
  curl -fsS --max-time 2 "http://127.0.0.1:$PORT/" >/dev/null 2>&1
}

print_status() {
  local pid="$(service_pid)"
  local launchd_state="未安装"
  if [ -f "$PLIST_PATH" ]; then
    launchd_state="已安装"
  fi
  if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
    launchd_state="已加载"
  fi

  if [ -n "$pid" ]; then
    echo -e "  服务状态: ${GREEN}● 运行中${RESET} (PID: $pid)"
  else
    echo -e "  服务状态: ${RED}● 未运行${RESET}"
  fi
  if health_status; then
    echo -e "  健康检查: ${GREEN}● 正常${RESET}"
  else
    echo -e "  健康检查: ${YELLOW}● 未通过${RESET}"
  fi
  echo -e "  launchd 状态: ${CYAN}$launchd_state${RESET}"
  echo -e "  调试日志: ${BOLD}$LOG_DIR${RESET}"
  echo -e "  常驻日志: ${BOLD}$SERVICE_LOG_DIR${RESET}"
}

prepare_runtime_bundle() {
  mkdir -p "$SERVICE_ROOT"
  mkdir -p "$(dirname "$SERVICE_PROJECT_DIR")"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude 'logs' \
      --exclude 'runtime' \
      "$PROJECT_DIR/" "$SERVICE_PROJECT_DIR/" || return 1
  else
    rm -rf "$SERVICE_PROJECT_DIR"
    mkdir -p "$(dirname "$SERVICE_PROJECT_DIR")"
    ditto "$PROJECT_DIR" "$SERVICE_PROJECT_DIR" || return 1
    rm -rf "$SERVICE_PROJECT_DIR/logs" "$SERVICE_PROJECT_DIR/runtime"
  fi
  mkdir -p "$SERVICE_LOG_DIR" "$SERVICE_PROJECT_DIR/runtime"
}

write_plist() {
  cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$SERVICE_START_SCRIPT</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$SERVICE_PROJECT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$SERVICE_LOG</string>
  <key>StandardErrorPath</key>
  <string>$ERROR_LOG</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
    <key>ADSPWR_PROJECT_ROOT</key>
    <string>$SERVICE_ROOT</string>
    <key>ADSPWR_OUTPUT_DIR</key>
    <string>$SERVICE_ROOT/output</string>
  </dict>
</dict>
</plist>
PLIST
}

install_service() {
  prepare_runtime_bundle || return 1
  write_plist
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH" || return 1
  launchctl enable "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
}

start_service() {
  prepare_runtime_bundle || return 1
  if [ ! -f "$PLIST_PATH" ]; then
    install_service || return 1
  fi
  if ! launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
    launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH" || return 1
  fi
  launchctl kickstart -k "gui/$(id -u)/$LABEL"
}

stop_service() {
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
}

uninstall_service() {
  stop_service
  rm -f "$PLIST_PATH"
}

show_logs() {
  clear
  echo "最近 80 行日志："
  echo "----------------------------------------"
  tail -n 80 "$SERVICE_LOG" "$ERROR_LOG" "$STARTUP_LOG" "$APP_LOG" "$SERVICE_LOG_DIR/startup.log" "$SERVICE_LOG_DIR/server.log" 2>/dev/null || echo "暂无日志"
  echo ""
  read -r -p "按回车返回菜单..."
}

run_foreground_debug() {
  clear
  echo -e "${GREEN}前台调试启动${RESET}"
  echo "关闭窗口或按 Ctrl+C 会停止当前调试进程。"
  echo "----------------------------------------"
  /bin/bash "$START_SCRIPT"
}

show_menu() {
  clear
  echo ""
  echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════╗${RESET}"
  echo -e "${CYAN}${BOLD}║   AdsPower 24 小时运行服务管理 (macOS)   ║${RESET}"
  echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════╝${RESET}"
  echo ""
  print_status
  echo ""
  echo -e "  ${BOLD}1)${RESET} 安装并加载 launchd 服务"
  echo -e "  ${BOLD}2)${RESET} 启动/重启服务"
  echo -e "  ${BOLD}3)${RESET} 停止服务"
  echo -e "  ${BOLD}4)${RESET} 卸载服务"
  echo -e "  ${BOLD}5)${RESET} 查看日志"
  echo -e "  ${BOLD}6)${RESET} 前台调试启动"
  echo ""
  echo -e "  ${BOLD}q)${RESET} 退出"
  echo ""
  echo -n "  请选择 [1/2/3/4/5/6/q]: "
}

main() {
  while true; do
    show_menu
    read -r choice
    case "$choice" in
      1)
        echo ""
        if install_service; then
          echo -e "${GREEN}服务已安装并加载${RESET}"
        else
          echo -e "${RED}服务安装失败，请查看 launchd 日志${RESET}"
        fi
        sleep 2
        ;;
      2)
        echo ""
        if start_service; then
          echo -e "${GREEN}服务已启动/重启${RESET}"
        else
          echo -e "${RED}服务启动失败，请查看日志${RESET}"
        fi
        sleep 2
        ;;
      3)
        echo ""
        stop_service
        echo -e "${GREEN}服务已停止${RESET}"
        sleep 2
        ;;
      4)
        echo ""
        uninstall_service
        echo -e "${GREEN}服务已卸载${RESET}"
        sleep 2
        ;;
      5) show_logs ;;
      6) run_foreground_debug; break ;;
      q|Q) echo ""; echo "再见"; sleep 1; break ;;
      *) echo -e "${RED}无效选项${RESET}"; sleep 1 ;;
    esac
  done
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main
fi
