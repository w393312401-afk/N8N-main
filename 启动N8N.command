#!/bin/bash
# N8N 后台进程管理器

# 设置 UTF-8 编码，防止终端中文乱码
export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_SH="$SCRIPT_DIR/scripts/start_n8n_stack.sh"

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

show_menu() {
  clear
  echo -e "${BLUE}===================================================${NC}"
  echo -e "${BOLD}${CYAN}              N8N 24小时后台管理工具              ${NC}"
  echo -e "${BLUE}===================================================${NC}"
  echo -e " 1) 🚀 ${GREEN}启动 N8N 24小时后台服务${NC}"
  echo -e " 2) 🔍 ${YELLOW}查看当前运行状态${NC}"
  echo -e " 3) 🧹 ${RED}清理/关闭所有相关进程${NC}"
  echo -e " 4) 🚪 ${PURPLE}退出${NC}"
  echo -e "${BLUE}===================================================${NC}"
  echo -n "请选择操作 [1-4]: "
}

while true; do
  show_menu
  read -r choice
  case "$choice" in
    1)
      echo -e "\n${GREEN}正在启动 N8N 后台服务...${NC}"
      "$STACK_SH" start
      echo -e "\n按任意键返回主菜单..."
      read -n 1 -s
      ;;
    2)
      echo -e "\n${YELLOW}当前运行状态如下:${NC}"
      "$STACK_SH" status
      echo -e "\n按任意键返回主菜单..."
      read -n 1 -s
      ;;
    3)
      echo -e "\n${RED}正在停止 N8N 后台服务...${NC}"
      "$STACK_SH" stop
      echo -e "\n按任意键返回主菜单..."
      read -n 1 -s
      ;;
    4)
      echo -e "\n${PURPLE}感谢使用，再见！${NC}"
      exit 0
      ;;
    *)
      echo -e "\n${RED}无效的选择，请重新输入。${NC}"
      sleep 1.5
      ;;
  esac
done
