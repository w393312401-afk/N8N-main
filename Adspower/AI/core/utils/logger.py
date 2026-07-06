# -*- coding: utf-8 -*-
"""
🌟 精致化日志输出
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
带颜色和图标的日志函数，同时写入控制台和文件。
"""

import os
import time


def log(msg, prefix="System"):
    """ 🌟 精致化日志输出 """
    # 颜色代码
    COLORS = {
        "GoogleFX": "\033[94m", # 蓝色
        "VideoGen": "\033[96m", # 青色
        "System": "\033[90m",   # 灰色
        "Error": "\033[91m",    # 红色
        "Success": "\033[92m",  # 绿色
        "Warning": "\033[93m",  # 黄色
        "RESET": "\033[0m"
    }
    
    # 图标映射
    ICONS = {
        "GoogleFX": "🎨", 
        "VideoGen": "🎬",
        "System": "⚙️ ",
        "Error": "❌",
        "Success": "✅",
        "Warning": "⚠️ ",
        "Input": "⌨️ ",
        "Audit": "🛡️ "
    }

    # 1. 确定颜色和图标
    color = COLORS.get(prefix, COLORS["System"])
    icon = ICONS.get(prefix, "📝")
    if "错误" in prefix or "Error" in prefix: icon = "❌"; color = COLORS["Error"]
    if "成功" in prefix or "Success" in prefix: icon = "✅"; color = COLORS["Success"]
    
    # 2. 格式化组件名称 (固定宽度 10)
    module_name = prefix[:10].center(10)
    
    # 3. 组装日志
    current_time = time.strftime("%H:%M:%S", time.localtime())
    
    # 控制台输出 (带颜色)
    console_line = f"{color}[{current_time}] │ {icon} │ {module_name} │ {msg}{COLORS['RESET']}"
    print(console_line, flush=True)
    
    # 文件输出 (去除颜色代码)
    file_line = f"[{current_time}] │ {icon} │ {module_name} │ {msg}"
    try:
        log_dir = os.environ.get("ADSPWR_LOG_DIR", "").strip()
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "server.log")
        else:
            # 兜底：始终写到项目根目录的 logs/，避免日志散落到 core/
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            log_dir = os.path.join(project_root, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "server.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(file_line + "\n")
    except Exception:
        pass
