#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 任务文件夹监听器 (File-based IPC Tracker)
用途: 绕过沙盒网络限制，监听 AI_Tasks 文件夹中的新 .json 任务，并转发到本地 127.0.0.1 API。
"""

import os
import time
import json
import urllib.request
import traceback

WATCH_DIR = "/Users/fly/Desktop/Agent Skill/AI延时视频分镜脚本制作skill/output/AI_Tasks"
API_URL = "http://127.0.0.1:8000/generate"

def process_file(filepath):
    print(f"\n🔄 发现新任务: {os.path.basename(filepath)}")
    try:
        # 尝试读取文件内容
        with open(filepath, 'r', encoding='utf-8') as f:
            data = f.read()
            
        # 发送请求至本地服务 (无沙盒限制)
        req = urllib.request.Request(API_URL, data=data.encode('utf-8'), headers={'Content-Type': 'application/json'})
        print(f"🚀 正在发送至本地 AdsPower 服务 (127.0.0.1:8000)...")
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result.get("status") == "success":
                print(f"✅ 生成成功！图片路径: {result.get('url')}")
            else:
                print(f"⚠️ 生成结束，返回信息: {result.get('msg')}")
            
    except Exception as e:
        print(f"❌ 任务执行失败: {e}")
    finally:
        # 处理完毕后删除，防止死循环重复执行
        try:
            os.remove(filepath)
            print(f"🗑️ 已清理任务文件: {os.path.basename(filepath)}")
        except Exception as e:
            print(f"⚠️ 清理文件失败: {e}")

def main():
    os.makedirs(WATCH_DIR, exist_ok=True)
    print(f"============================================================")
    print(f"👀 启动 AI 本地跨沙盒监听器 (IPC Watcher) ")
    print(f"📁 监听目录: {WATCH_DIR}")
    print(f"🎯 投递目标: {API_URL}")
    print(f"🕒 等待 AI 助手投递任务... (按 Ctrl+C 退出)")
    print(f"============================================================")
    
    while True:
        try:
            for filename in os.listdir(WATCH_DIR):
                if filename.endswith(".json"):
                    filepath = os.path.join(WATCH_DIR, filename)
                    # 延迟 1 秒确保沙盒进程完全写完文件
                    time.sleep(1)
                    process_file(filepath)
        except KeyboardInterrupt:
            print("\n👋 监听终止。")
            break
        except Exception as e:
            print(f"⚠️ 监听循环扫描出错: {e}")
            time.sleep(2)
            
        time.sleep(1) # 每秒扫描一次

if __name__ == "__main__":
    main()
