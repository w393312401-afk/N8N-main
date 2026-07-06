#!/bin/bash
# ==============================================================================
# 🎛️ AdsPower AI 服务管理 (TUI 菜单)
# 配置统一读取自: Adspower/AI/.env
# ==============================================================================

SOURCE_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"

# 加载统一环境 + 模块
source "$SCRIPT_DIR/lib/env.sh"
source "$SCRIPT_DIR/lib/deps.sh"
source "$SCRIPT_DIR/lib/server.sh"

# --- 文件锁：防止多实例并发 ---
LOCK_FILE="$RUNTIME_DIR/service_mgr.lock"

acquire_lock() {
  if ! mkdir "$LOCK_FILE" 2>/dev/null; then
    echo "⚠️ 另一个服务管理实例正在运行，如确认无其他实例，请删除: $LOCK_FILE"
    exit 1
  fi
}

release_lock() {
  rm -rf "$LOCK_FILE" 2>/dev/null
}

# --- 信号捕获 ---
cleanup() {
  release_lock
  tput cnorm 2>/dev/null  # 恢复光标
  echo ""
  echo "👋 已退出服务管理"
  exit 0
}
trap cleanup INT TERM EXIT

acquire_lock

# --- 主菜单 ---
while true; do
  clear
  echo -e "${BOLD}AdsPower AI 服务管理${NC}"
  echo "──────────────────────────"
  print_status
  echo ""
  echo -e "${DIM}💡 第一次使用？按 h 查看快速上手指南${NC}"
  echo -e "${DIM}📡 API 文档: http://${HOST}:${PORT}/docs${NC}"
  echo ""
  echo -e "  ${GREEN}1)${NC} 启动服务（稳定模式）"
  echo -e "  ${GREEN}2)${NC} 启动服务（开发热重载）"
  echo -e "  ${YELLOW}3)${NC} 停止当前服务"
  echo -e "  ${RED}4)${NC} 强制中断服务"
  echo -e "  ${CYAN}5)${NC} 查看日志路径"
  echo -e "  ${CYAN}6)${NC} 实时查看服务日志"
  echo -e "  ${CYAN}7)${NC} 健康检查"
  echo -e "  ${DIM}8)${NC} 刷新状态"
  echo -e "  ${DIM}h)${NC} 打开快速上手指南"
  echo -e "  ${DIM}q)${NC} 退出"
  echo ""
  printf "请选择: "
  read -r choice

  case "$choice" in
    1)
      ADSPWR_RELOAD=0 start_server "stable"
      read -r -p "按回车继续..."
      ;;
    2)
      ADSPWR_RELOAD=1 start_server "dev"
      read -r -p "按回车继续..."
      ;;
    3)
      stop_service
      read -r -p "按回车继续..."
      ;;
    4)
      printf "此操作会强制 kill 服务相关进程，确认继续? [y/N]: "
      read -r confirm
      if [[ "$confirm" =~ ^[Yy]$ ]]; then
        force_interrupt_service
      else
        echo "已取消"
      fi
      read -r -p "按回车继续..."
      ;;
    5)
      echo ""
      echo -e "启动日志: ${CYAN}$STARTUP_LOG${NC}"
      echo -e "服务日志: ${CYAN}$APP_LOG${NC}"
      echo -e "PID 文件: ${CYAN}$PID_FILE${NC}"
      echo -e "运行时目录: ${CYAN}$RUNTIME_DIR${NC}"
      read -r -p "按回车继续..."
      ;;
    6)
      tail_log "$APP_LOG"
      read -r -p "按回车继续..."
      ;;
    7)
      health_check
      read -r -p "按回车继续..."
      ;;
    8)
      ;;
    h|H)
      open "$PROJECT_DIR/快速开始.md" 2>/dev/null || \
        less "$PROJECT_DIR/快速开始.md"
      ;;
    q|Q)
      exit 0
      ;;
    *)
      echo "无效选项"
      read -r -p "按回车继续..."
      ;;
  esac
done
