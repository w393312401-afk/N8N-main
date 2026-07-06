# -*- coding: utf-8 -*-
"""
n8n-friendly Google FX task wrapper.

2026-05-16: 禁用所有自动重试。任何失败都直接返回 retryable=false。
"""

from models import GoogleFxRunRequest, ImageBatchRequest, VideoRequest, VideoBatchRequest, VideoBatchItem
from config import get_runtime_google_fx_image_model, get_runtime_google_fx_video_model
from services.google_fx import _generate_images_batch_google_fx, _generate_video_google_fx, _generate_videos_batch_google_fx


MANUAL_REQUIRED_PATTERNS = {
    "captcha": "captcha_required",
    "recaptcha": "captcha_required",
    "not a robot": "captcha_required",
    "robot": "captcha_required",
    "human": "verification_required",
    "verify": "verification_required",
    "verification": "verification_required",
    "人机验证": "captcha_required",
    "机器人": "captcha_required",
    "真人": "verification_required",
    "sign in": "login_required",
    "login": "login_required",
    "登录": "login_required",
    "二次验证": "verification_required",
    "安全": "security_check",
    "security": "security_check",
    "forbidden": "forbidden",
    "403": "forbidden",
    "429": "rate_limited",
    "rate limit": "rate_limited",
    "too many requests": "rate_limited",
    "unusual traffic": "security_check",
    "unusual activity": "security_check",
}

def _classify_error(message: str) -> tuple[str, str, bool]:
    text = (message or "").strip()
    lower_text = text.lower()
    if "manual_required:" in lower_text:
        parts = text.split(":", 2)
        code = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "manual_required"
        return "manual_required", code, False
    for pattern, code in MANUAL_REQUIRED_PATTERNS.items():
        if pattern in lower_text:
            return "manual_required", code, False
    if not text:
        return "failed", "unknown_error", False
    return "failed", "generation_failed", False


def _success_response(req: GoogleFxRunRequest, kind: str, raw: dict) -> dict:
    result_paths = raw.get("image_urls") if kind == "image" else [raw.get("video_url")]
    # 批量视频模式返回 video_urls 列表
    if kind == "videos":
        result_paths = [p for p in (raw.get("video_urls") or []) if p]
    result_paths = [path for path in (result_paths or []) if path]
    return {
        "ok": True,
        "status": "success",
        "task_id": req.task_id,
        "kind": kind,
        "result_path": result_paths[0] if result_paths else "",
        "result_paths": result_paths,
        "error_code": "",
        "error_message": "",
        "retryable": False,
        "raw": raw,
    }


def _failure_response(req: GoogleFxRunRequest, kind: str, raw: dict) -> dict:
    message = str((raw or {}).get("message") or "")
    status, error_code, retryable = _classify_error(message)
    return {
        "ok": False,
        "status": status,
        "task_id": req.task_id,
        "kind": kind,
        "result_path": "",
        "result_paths": [],
        "error_code": error_code,
        "error_message": message,
        "retryable": retryable,
        "raw": raw or {},
    }


def _run_google_fx_task_inner(req: GoogleFxRunRequest) -> dict:
    """单次执行逻辑（原 run_google_fx_task 内容）。"""
    kind = (req.kind or "image").strip().lower()

    if kind in {"image", "images"}:
        prompts = req.prompts or ([req.prompt] if req.prompt else [])
        if not prompts:
            return _failure_response(req, "image", {"message": "No prompts provided"})
        raw = _generate_images_batch_google_fx(ImageBatchRequest(
            prompts=prompts,
            images=req.images,
            ratio=req.ratio,
            model=req.model or get_runtime_google_fx_image_model(),
            output_path=req.output_path,
        ))
        return _success_response(req, "image", raw) if raw.get("status") == "success" else _failure_response(req, "image", raw)

    if kind == "video":
        if not req.prompt:
            return _failure_response(req, "video", {"message": "No prompt provided"})
        raw = _generate_video_google_fx(VideoRequest(
            prompt=req.prompt,
            image=req.image,
            end_image=req.end_image,
            ratio=req.ratio,
            model=req.model or get_runtime_google_fx_video_model(),
            output_path=req.output_path,
        ))
        return _success_response(req, "video", raw) if raw.get("status") == "success" else _failure_response(req, "video", raw)

    return _failure_response(req, kind, {"message": f"Unsupported Google FX kind: {req.kind}"})


def run_google_fx_task(req: GoogleFxRunRequest) -> dict:
    """外层入口：只执行一次，任何失败都不自动重试。"""
    return _run_google_fx_task_inner(req)
