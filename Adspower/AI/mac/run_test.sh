#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/lib/env.sh"

TOOLS_DIR="$PROJECT_DIR/tools"
RESULT_LOG="$LOG_DIR/test_api_result.log"

printf '== 静态检查 ==\n' | tee "$RESULT_LOG"
(
  cd "$CORE_DIR"
  PYTHONPATH=. python3 -c "from app import app; print('IMPORT_OK', app.title); print('ROUTES', sorted([r.path for r in app.routes]))"
) | tee -a "$RESULT_LOG"

printf '\n== 运行中服务检查 ==\n' | tee -a "$RESULT_LOG"
if curl -fsS --max-time 3 "http://${HOST}:${PORT}/" >/dev/null 2>&1; then
  python3 "$TOOLS_DIR/test_api.py" | tee -a "$RESULT_LOG"
else
  printf 'SKIP: 服务未运行，已跳过在线 API 集成测试。\n' | tee -a "$RESULT_LOG"
fi
