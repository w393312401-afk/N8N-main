# -*- coding: utf-8 -*-
"""
🚀 AdsPower All-in-One API 入口
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FastAPI 应用创建、中间件注册、路由注册。
"""

import os
import time
import json
import traceback
from importlib import import_module
from typing import Optional, Callable

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response
from fastapi.routing import APIRoute
import builtins
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import requests
import shutil
import asyncio
import anyio

from config import (
    OUTPUT_DIR,
    PROJECT_ROOT,
    SERVER_HOST,
    SERVER_PORT,
    DEFAULT_PORT,
    get_runtime_default_port,
)
from models import (
    GoogleFxRunRequest,
    ImageBatchRequest,

    MergeRequest,
    VideoBatchRequest,
    VideoRequest,
    UploadNotionVideoRequest,
)
from utils.logger import log


# ==============================================================================
# 🚀 FastAPI 应用
# ==============================================================================

class UnifiedLoggingRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()
        
        async def custom_route_handler(request: Request) -> Response:
            start_time = time.time()
            client_host = request.client.host if request.client else "unknown"
            print(f"🔌 [强制日志] 收到连接: {client_host} -> {request.method} {request.url.path}", flush=True)
            log(f"🔌 收到连接: {client_host} -> {request.method} {request.url.path}", "审计")
            
            try:
                body = await request.body()
                if body:
                    try:
                        payload = json.loads(body)
                        log(f"📥 请求体 (JSON): {json.dumps(payload, ensure_ascii=False)}", "审计")
                    except:
                        log(f"📥 请求体 (原始): {body.decode('utf-8', errors='ignore')}", "审计")
                else:
                    log(f"📥 请求体: <空>", "审计")
            except Exception:
                log(f"📥 请求体: <读取/解析错误>", "审计")
                
            try:
                response = await original_route_handler(request)
                process_time = (time.time() - start_time) * 1000
                log(f"✅ 处理完成: 状态码 {response.status_code} (耗时 {process_time:.2f}ms)", "审计")
                return response
            except Exception as e:
                process_time = (time.time() - start_time) * 1000
                log(f"💥 异常崩溃: {str(e)} \n{traceback.format_exc()}", "系统错误")
                raise e
                
        return custom_route_handler


app = FastAPI(title="AdsPower All-in-One API (Google FX)")
app.router.route_class = UnifiedLoggingRoute

# 允许跨域 (CORS) 方便开发与外部集成
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态资源：前端控制台仪表盘
_current_dir = os.path.dirname(os.path.abspath(__file__))
dashboard_dir = os.path.join(_current_dir, "dashboard")
os.makedirs(dashboard_dir, exist_ok=True)
app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

# 挂载生成媒体目录，方便前端播放预览
if os.path.exists(OUTPUT_DIR):
    app.mount("/media", StaticFiles(directory=OUTPUT_DIR), name="media")


@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    """上传参考图片，保存到 OUTPUT_DIR 下的 temp_uploads，并返回绝对路径"""
    temp_dir = os.path.join(OUTPUT_DIR, "temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"status": "success", "file_path": os.path.abspath(file_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# UnifiedLoggingRoute replaces log_requests middleware to avoid breaking request.is_disconnected()


# ==============================================================================
# 🎬 视频生成路由
# ==============================================================================

async def monitor_disconnect(request: Request):
    """Monitor client disconnect to close AdsPower browser immediately."""
    try:
        while True:
            if await request.is_disconnected():
                print("🔌 [强制日志] 检测到客户端已断开，正在紧急关闭 AdsPower 浏览器...", flush=True)
                log("🔌 检测到客户端已断开，正在紧急关闭 AdsPower 浏览器...", "监控")
                from utils import cancel_flag
                cancel_flag.is_cancelled = True
                from utils.browser import stop_ads_browser
                stop_ads_browser()
                break
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass


def _check_and_raise(result):
    if isinstance(result, dict) and result.get("status") == "failed":
        raise HTTPException(status_code=500, detail=result.get("message", "Generation failed"))
    return result


def _load_service_attr(module_name: str, attr_name: str):
    """
    按需导入重服务模块，降低启动耦合。
    这样健康检查/环境查询不会因为某个生成模块导入失败而整体不可用。
    """
    module = import_module(module_name)
    return getattr(module, attr_name)


@app.post("/generate_video")
async def generate_video_unified(request: Request, req: VideoRequest):
    import builtins
    builtins.google_fx_cancelled = False
    from utils import cancel_flag
    cancel_flag.init_context()
    cancel_flag.is_cancelled = False
    handler = _load_service_attr("services.google_fx", "_generate_video_google_fx")
    monitor_task = asyncio.create_task(monitor_disconnect(request))
    try:
        result = await anyio.to_thread.run_sync(handler, req)
        return _check_and_raise(result)
    except Exception as e:
        from utils.browser import stop_ads_browser
        stop_ads_browser()
        raise e
    finally:
        monitor_task.cancel()


@app.post("/generate_video_veo")
async def generate_video_veo_legacy(request: Request, req: VideoRequest):
    import builtins
    builtins.google_fx_cancelled = False
    from utils import cancel_flag
    cancel_flag.init_context()
    cancel_flag.is_cancelled = False
    handler = _load_service_attr("services.google_fx", "_generate_video_google_fx")
    monitor_task = asyncio.create_task(monitor_disconnect(request))
    try:
        result = await anyio.to_thread.run_sync(handler, req)
        return _check_and_raise(result)
    except Exception as e:
        from utils.browser import stop_ads_browser
        stop_ads_browser()
        raise e
    finally:
        monitor_task.cancel()


@app.post("/generate_videos_batch")
async def generate_videos_batch_endpoint(request: Request, req: VideoBatchRequest):
    """批量视频并发生成 (默认并发模式)

    请求例:
    {
      "items": [
        {"prompt": "...", "image": "/path/to/start.jpg", "end_image": "/path/to/end.jpg"},
        {"prompt": "...", "image": "/path/to/start2.jpg", "end_image": "/path/to/end2.jpg"}
      ],
      "ratio": "9:16",
      "model": "Veo 3.1 - Fast",
      "output_path": "/path/to/output",
      "concurrent": true,
      "max_concurrent": 3
    }
    """
    import builtins
    builtins.google_fx_cancelled = False
    from utils import cancel_flag
    cancel_flag.init_context()
    cancel_flag.is_cancelled = False
    handler = _load_service_attr("services.google_fx", "_generate_videos_batch_google_fx")
    monitor_task = asyncio.create_task(monitor_disconnect(request))
    try:
        result = await anyio.to_thread.run_sync(handler, req)
        return _check_and_raise(result)
    except Exception as e:
        from utils.browser import stop_ads_browser
        stop_ads_browser()
        raise e
    finally:
        monitor_task.cancel()


# ==============================================================================
# 🖼️ 图片批量生成路由
# ==============================================================================

@app.post("/generate_images_batch")
async def generate_images_batch_endpoint(request: Request, req: ImageBatchRequest):
    import builtins
    builtins.google_fx_cancelled = False
    from utils import cancel_flag
    cancel_flag.init_context()
    cancel_flag.is_cancelled = False
    handler = _load_service_attr("services.google_fx", "_generate_images_batch_google_fx")
    monitor_task = asyncio.create_task(monitor_disconnect(request))
    try:
        result = await anyio.to_thread.run_sync(handler, req)
        return _check_and_raise(result)
    except Exception as e:
        from utils.browser import stop_ads_browser
        stop_ads_browser()
        raise e
    finally:
        monitor_task.cancel()


@app.post("/google_fx/run")
async def run_google_fx_for_n8n(request: Request, req: GoogleFxRunRequest):
    import builtins
    builtins.google_fx_cancelled = False
    from utils import cancel_flag
    cancel_flag.init_context()
    cancel_flag.is_cancelled = False
    handler = _load_service_attr("services.google_fx_task", "run_google_fx_task")
    monitor_task = asyncio.create_task(monitor_disconnect(request))
    try:
        result = await anyio.to_thread.run_sync(handler, req)
        return result
    except Exception as e:
        from utils.browser import stop_ads_browser
        stop_ads_browser()
        raise e
    finally:
        monitor_task.cancel()


# ==============================================================================
# 🧩 视频合并路由
# ==============================================================================

@app.post("/merge_videos")
async def merge_videos_endpoint(request: MergeRequest):
    handler = _load_service_attr("services.ffmpeg", "merge_videos_logic")
    return await handler(request)


@app.post("/upload_notion_video")
async def upload_notion_video_endpoint(req: UploadNotionVideoRequest):
    handler = _load_service_attr("services.notion_upload", "upload_video_to_notion")
    try:
        result = await anyio.to_thread.run_sync(handler, req.page_id, req.video_path, req.status)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/task_manifest")
def task_manifest(output_dir: str):
    if not output_dir:
        raise HTTPException(status_code=400, detail="output_dir is required")
    handler = _load_service_attr("services.manifest", "build_manifest_response")
    return handler(output_dir)


@app.post("/cancel_task")
@app.get("/cancel_task")
def cancel_task():
    from utils import cancel_flag
    cancel_flag.is_cancelled = True
    from utils.browser import stop_ads_browser
    log("🛑 收到取消任务请求，已设置取消标志，并尝试关闭 AdsPower 浏览器", "主程序")
    stop_ads_browser()
    return {"status": "success", "message": "Task cancellation flag set and browser stop requested"}


@app.post("/close_browser")
@app.get("/close_browser")
def close_browser():
    from utils.browser import stop_ads_browser
    log("🔌 收到关闭浏览器请求，正在关闭 AdsPower 浏览器...", "主程序")
    stop_ads_browser()
    return {"status": "success", "message": "Browser stop requested"}


# ==============================================================================
# 🌐 环境管理和健康检查
# ==============================================================================

@app.get("/environments")
def list_environments(port: Optional[str] = None):
    """列出所有 AdsPower 浏览器环境"""
    try:
        port = port or get_runtime_default_port() or DEFAULT_PORT
        resp = requests.get(
            f"http://127.0.0.1:{port}/api/v1/user/list?page=1&page_size=100",
            timeout=10
        ).json()
        if resp.get("code") != 0:
            raise HTTPException(status_code=502, detail=f"AdsPower API Error: {resp.get('msg')}")
        profiles = resp.get("data", {}).get("list", [])
        return {
            "total": len(profiles),
            "environments": [
                {
                    "user_id": p.get("user_id", ""),
                    "serial_number": p.get("serial_number", ""),
                    "name": p.get("name", ""),
                    "group_name": p.get("group_name", ""),
                    "domain_name": p.get("domain_name", ""),
                }
                for p in profiles
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询环境列表失败: {str(e)}")


@app.get("/api/logs")
def get_logs(lines: int = 100):
    """获取最后 N 行执行日志，供前端实时控制台展示"""
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_service.log")
    if not os.path.exists(log_path):
        return {"logs": []}
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.readlines()
            return {"logs": [line.strip() for line in content[-lines:]]}
    except Exception as e:
        return {"error": str(e), "logs": []}


@app.post("/rotate_proxy")
def rotate_proxy_endpoint():
    """手动/强制触发代理 IP 轮换"""
    try:
        from utils.proxy_rotator import ProxyRotator
        from config import get_runtime_default_user_id, get_runtime_default_port
        rotator = ProxyRotator()
        user_id = get_runtime_default_user_id()
        port = get_runtime_default_port()
        if rotator.is_configured:
            rotator.rotate_proxy(user_id=user_id, port=port, force=True)
            return {"status": "success", "message": "Proxy rotated successfully"}
        else:
            return {"status": "skipped", "message": "Proxy rotator is not configured or disabled"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/")
def health_check():
    return {
        "status": "All-in-One API is running",
        "project_root": PROJECT_ROOT,
        "output_dir": OUTPUT_DIR,
        "ads_power_api_reachable": _is_adspower_reachable(),
    }


def _is_adspower_reachable(port: Optional[str] = None) -> bool:
    try:
        port = port or get_runtime_default_port() or DEFAULT_PORT
        response = requests.get(f"http://127.0.0.1:{port}/status", timeout=2)
        return response.ok
    except Exception:
        return False


if __name__ == "__main__":
    reload_enabled = os.getenv("ADSPWR_RELOAD", "").strip().lower() in {"1", "true", "yes", "on"}
    log(f"服务启动中: http://{SERVER_HOST}:{SERVER_PORT} | reload={'on' if reload_enabled else 'off'}", "主程序")
    uvicorn.run("app:app", host=SERVER_HOST, port=SERVER_PORT, reload=reload_enabled)
