# -*- coding: utf-8 -*-
"""
🔁 兼容入口 (向后兼容)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
原始的 ads_all_in_one.py 已拆分为模块化结构。
此文件保留以确保旧的启动脚本和引用仍然有效。

新的入口文件: app.py
"""

# 从 app.py 导入 FastAPI 实例 (供 uvicorn 使用)
from app import app

import uvicorn
from config import SERVER_HOST, SERVER_PORT
from utils.logger import log

if __name__ == "__main__":
    log(f"服务启动中: http://{SERVER_HOST}:{SERVER_PORT}", "主程序")
    log("💡 提示: 新的入口文件为 app.py，此文件为兼容入口。", "主程序")
    uvicorn.run("app:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
