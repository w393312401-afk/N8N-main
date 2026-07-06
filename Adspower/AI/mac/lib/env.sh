#!/bin/bash
# ==============================================================================
# 🔧 env.sh — 统一环境加载器
# 所有 Shell 脚本的配置入口：读取 .env + 推导路径
# ==============================================================================

# --- 路径推导 (相对于 lib/ 目录) ---
_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAC_DIR="$(cd "$_LIB_DIR/.." && pwd)"
PROJECT_DIR="$(cd "$MAC_DIR/.." && pwd)"
CORE_DIR="$PROJECT_DIR/core"
LOG_DIR="$PROJECT_DIR/logs"
RUNTIME_DIR="$PROJECT_DIR/runtime"
ENV_FILE="$PROJECT_DIR/.env"

# --- 读取 .env ---
if [ -f "$ENV_FILE" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    # 去除首尾空格
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    # 跳过注释和空行
    [[ -z "$line" || "$line" == \#* ]] && continue
    # 分离 key=value（只在第一个 = 处分割，保留值中的 =）
    key="${line%%=*}"
    value="${line#*=}"
    # 去除行内注释（仅匹配 " #" 或 "\t#" 形式，避免误删值中的 #）
    value="$(echo "$value" | sed 's/[[:space:]]#.*$//')"
    # 去除 key 首尾空格
    key="$(echo "$key" | xargs)"
    # 去除 value 首尾空格
    value="$(echo "$value" | xargs)"
    # 去除 value 外层引号 (双引号或单引号)
    if [[ "$value" =~ ^\"(.*)\"$ ]]; then
      value="${BASH_REMATCH[1]}"
    elif [[ "$value" =~ ^\'(.*)\'$ ]]; then
      value="${BASH_REMATCH[1]}"
    fi
    # 跳过无效 key
    [[ -z "$key" || "$key" =~ [^a-zA-Z0-9_] ]] && continue
    # 只在环境变量未设置时才赋值（允许命令行覆盖 .env）
    if [ -z "${!key+x}" ]; then
      export "$key"="$value"
    fi
  done < "$ENV_FILE"
else
  echo "⚠️ 未找到配置文件: $ENV_FILE，使用默认值"
fi

# --- 从 .env 中读取的值（带 fallback 默认值）---
HOST="${SERVER_HOST:-127.0.0.1}"
PORT="${SERVER_PORT:-8000}"
ADSPOWER_PORT="${ADSPOWER_PORT:-50325}"
ADSPWR_RELOAD="${ADSPWR_RELOAD:-0}"

# --- 衍生路径 ---
STARTUP_LOG="$LOG_DIR/startup.log"
APP_LOG="$LOG_DIR/server.log"
PID_FILE="$RUNTIME_DIR/server.pid"

# --- 确保目录存在 ---
mkdir -p "$LOG_DIR" "$RUNTIME_DIR"
