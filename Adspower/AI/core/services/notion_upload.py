# -*- coding: utf-8 -*-
"""
🚀 Notion 真实文件上传与属性更新服务
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
提供视频文件的 Notion 直传，并在上传完成后更新指定的 Notion 页面属性。
"""

import os
import math
import requests
from fastapi import HTTPException
from config import NOTION_TOKEN
from utils.logger import log

def upload_video_to_notion(page_id: str, video_path: str, status: str = "完成"):
    """
    将本地视频文件直传至 Notion 存储，并绑定到 page_id 的 “文件和媒体” 属性中，同时更新状态。
    """
    if not os.path.exists(video_path):
        log(f"❌ 视频文件不存在: {video_path}", "Notion上传")
        raise HTTPException(status_code=404, detail=f"Video file not found at: {video_path}")

    file_size = os.path.getsize(video_path)
    filename = os.path.basename(video_path)
    log(f"🎬 开始直传 Notion 视频: {filename} ({file_size / (1024*1024):.2f} MB)", "Notion上传")

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2026-03-11",
        "Content-Type": "application/json"
    }

    # Notion 限制：文件大小 > 20MB 时必须分片上传 (multi_part)
    PART_SIZE = 10 * 1024 * 1024  # 每片 10MB
    is_multipart = file_size > 20 * 1024 * 1024

    upload_id = None
    try:
        if not is_multipart:
            log("⚡ 使用单文件直接上传模式...", "Notion上传")
            # 1. 初始化上传会话
            init_url = "https://api.notion.com/v1/file_uploads"
            init_payload = {
                "mode": "single_part",
                "filename": filename,
                "content_type": "video/mp4"
            }
            init_resp = requests.post(init_url, headers=headers, json=init_payload)
            if init_resp.status_code != 200:
                log(f"❌ 初始化上传失败: {init_resp.text}", "Notion上传")
                raise HTTPException(status_code=500, detail=f"Failed to initiate upload: {init_resp.text}")
            
            init_data = init_resp.json()
            upload_id = init_data["id"]
            upload_url = init_data["upload_url"]

            # 2. 上传文件二进制内容
            with open(video_path, "rb") as f:
                files = {"file": (filename, f, "video/mp4")}
                upload_headers = {
                    "Authorization": f"Bearer {NOTION_TOKEN}",
                    "Notion-Version": "2026-03-11"
                }
                upload_resp = requests.post(upload_url, headers=upload_headers, files=files)
                if upload_resp.status_code != 200:
                    log(f"❌ 上传文件二进制内容失败: {upload_resp.text}", "Notion上传")
                    raise HTTPException(status_code=500, detail=f"Failed to upload binary content: {upload_resp.text}")

        else:
            num_parts = math.ceil(file_size / PART_SIZE)
            log(f"📦 文件较大，使用分片上传模式 ({num_parts} 片)...", "Notion上传")
            
            # 1. 初始化分片上传会话
            init_url = "https://api.notion.com/v1/file_uploads"
            init_payload = {
                "mode": "multi_part",
                "filename": filename,
                "content_type": "video/mp4",
                "number_of_parts": num_parts
            }
            init_resp = requests.post(init_url, headers=headers, json=init_payload)
            if init_resp.status_code != 200:
                log(f"❌ 初始化分片上传失败: {init_resp.text}", "Notion上传")
                raise HTTPException(status_code=500, detail=f"Failed to initiate multipart upload: {init_resp.text}")

            init_data = init_resp.json()
            upload_id = init_data["id"]
            upload_url = init_data["upload_url"]
            complete_url = f"https://api.notion.com/v1/file_uploads/{upload_id}/complete"

            # 2. 逐片读取并上传
            with open(video_path, "rb") as f:
                for i in range(num_parts):
                    part_num = i + 1
                    log(f"⬆️ 正在上传分片 {part_num}/{num_parts}...", "Notion上传")
                    chunk = f.read(PART_SIZE)
                    
                    files = {"file": (f"{filename}.part{part_num}", chunk, "video/mp4")}
                    data = {"part_number": part_num}
                    upload_headers = {
                        "Authorization": f"Bearer {NOTION_TOKEN}",
                        "Notion-Version": "2026-03-11"
                    }
                    part_resp = requests.post(upload_url, headers=upload_headers, files=files, data=data)
                    if part_resp.status_code != 200:
                        log(f"❌ 上传分片 {part_num} 失败: {part_resp.text}", "Notion上传")
                        raise HTTPException(status_code=500, detail=f"Failed to upload part {part_num}: {part_resp.text}")

            # 3. 完成分片上传，通知 Notion 拼合
            log("🔗 完成分片上传，请求 Notion 合并分片...", "Notion上传")
            complete_resp = requests.post(complete_url, headers=headers)
            if complete_resp.status_code != 200:
                log(f"❌ 合并分片失败: {complete_resp.text}", "Notion上传")
                raise HTTPException(status_code=500, detail=f"Failed to complete multipart upload: {complete_resp.text}")

        log(f"✅ 文件成功上传至 Notion。ID: {upload_id}，准备关联至页面 {page_id}...", "Notion上传")

        # 3. 更新 Notion 数据库页面属性
        page_url = f"https://api.notion.com/v1/pages/{page_id}"
        page_payload = {
            "properties": {
                "文件和媒体": {
                    "files": [
                        {
                            "name": filename,
                            "type": "file_upload",
                            "file_upload": {
                                "id": upload_id
                            }
                        }
                    ]
                },
                "状态": {
                    "status": {
                        "name": status
                    }
                }
            }
        }
        
        page_resp = requests.patch(page_url, headers=headers, json=page_payload)
        if page_resp.status_code != 200:
            log(f"❌ 绑定文件至 Notion 页面失败: {page_resp.text}", "Notion上传")
            raise HTTPException(status_code=500, detail=f"Failed to update Notion page properties: {page_resp.text}")

        log(f"🎉 Notion 页面属性更新成功！任务状态: {status}", "Notion上传")
        return {
            "status": "success",
            "file_id": upload_id,
            "filename": filename,
            "page_id": page_id,
            "notion_status": status
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        log(f"💥 Notion 文件上传及更新遇到未预期的异常: {str(e)}", "Notion上传")
        raise HTTPException(status_code=500, detail=f"Internal Notion upload error: {str(e)}")
