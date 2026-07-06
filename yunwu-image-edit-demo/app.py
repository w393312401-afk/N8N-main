from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CONFIG_PATH = BASE_DIR / ".launcher_config.json"
DEFAULT_SAVE_DIR = BASE_DIR / "outputs"

GPT_GENERATE_URL = "https://yunwu.ai/v1/images/generations"
GPT_EDIT_URL = "https://yunwu.ai/v1/images/edits"
GEMINI_URL_TEMPLATE = "https://yunwu.ai/v1beta/models/{model}:generateContent"
VIDEO_CREATE_URL = "https://yunwu.ai/v1/videos"
VIDEO_STATUS_URL_TEMPLATE = "https://yunwu.ai/v1/videos/{video_id}"
VIDEO_CONTENT_URL_TEMPLATE = "https://yunwu.ai/v1/videos/{video_id}/content"

REQUEST_TIMEOUT = (10, 180)
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
USE_SYSTEM_PROXY = os.getenv("YUNWU_USE_SYSTEM_PROXY", "").strip().lower() in TRUE_ENV_VALUES

GPT_MODEL = "gpt-image-2-all"
GEMINI_MODEL = "gemini-3.1-flash-image-preview"
SUPPORTED_MODELS = {GPT_MODEL, GEMINI_MODEL}
VIDEO_ALLOWED_MODELS = {"veo_3_1", "veo_3_1-fast"}
VIDEO_ALLOWED_SECONDS = {"4", "8", "12"}
VIDEO_ALLOWED_SIZES = {"16x9", "9x16", "1280x720", "720x1280"}
VIDEO_ALLOWED_WATERMARKS = {"true", "false"}
PROMPT_MAX_LENGTH = 2500

GPT_ALLOWED_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}
GPT_ALLOWED_ASPECT_RATIOS = {
    "1:1",
    "1:4",
    "4:1",
    "1:8",
    "8:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
}
GEMINI_ALLOWED_ASPECT_RATIOS = set(GPT_ALLOWED_ASPECT_RATIOS)
GPT_ASPECT_RATIO_TO_SIZE = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
}
GPT_SIZE_TO_ASPECT_RATIO = {size: aspect_ratio for aspect_ratio, size in GPT_ASPECT_RATIO_TO_SIZE.items()}
GPT_DEFAULT_ASPECT_RATIO = "9:16"
GEMINI_ALLOWED_IMAGE_SIZES = {"512", "1K", "2K", "4K"}

TERMINAL_STATUSES = {"completed", "failed"}
JOB_TTL_SECONDS = 3600
MAX_COMPLETED_JOBS = 100
HISTORY_PATH = BASE_DIR / ".history.json"
MAX_HISTORY_ITEMS = 240
CURRENT_PLATFORM_KEY = "macos" if sys.platform == "darwin" else "windows" if os.name == "nt" else "linux"
VIDEO_POLL_INTERVAL_SECONDS = 10
VIDEO_POLL_TIMEOUT_SECONDS = 1800
VIDEO_REMOTE_SUCCESS_STATUSES = {"completed", "succeeded"}
VIDEO_REMOTE_FAILURE_STATUSES = {"failed", "cancelled", "canceled", "expired"}


class GenerateRequest(BaseModel):
    model: str = GPT_MODEL
    prompt: str
    n: int = 1
    size: str = "auto"
    aspect_ratio: str = ""
    image_size: str = "512"


class ApiKeyUpdateRequest(BaseModel):
    api_key: str
    persist: bool = True


class SaveDirUpdateRequest(BaseModel):
    save_dir: str
    persist: bool = True


class JobRecord:
    def __init__(self, mode: str) -> None:
        now = time.time()
        self.id = uuid4().hex
        self.mode = mode
        self.status = "queued"
        self.phase = "accepted"
        self.message = "任务已受理，等待发送到上游接口。"
        self.created_at = now
        self.updated_at = now
        self.completed_at: float | None = None
        self.result: Any | None = None
        self.error: dict[str, Any] | None = None
        self.lock = Lock()

    def update(
        self,
        *,
        status: str | None = None,
        phase: str | None = None,
        message: str | None = None,
        result: Any | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        with self.lock:
            if status is not None:
                self.status = status
            if phase is not None:
                self.phase = phase
            if message is not None:
                self.message = message
            if result is not None:
                self.result = result
            if error is not None:
                self.error = error
            self.updated_at = time.time()
            if self.status in TERMINAL_STATUSES:
                self.completed_at = self.updated_at

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            now = time.time()
            reference = self.completed_at or now
            payload: dict[str, Any] = {
                "job_id": self.id,
                "mode": self.mode,
                "status": self.status,
                "phase": self.phase,
                "message": self.message,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "completed_at": self.completed_at,
                "elapsed_ms": int(max((reference - self.created_at) * 1000, 0)),
            }
            if self.result is not None:
                payload["result"] = self.result
            if self.error is not None:
                payload["error"] = self.error
            return payload


app = FastAPI(title="Yunwu Image Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

jobs: dict[str, JobRecord] = {}
jobs_lock = Lock()
history_lock = Lock()


def load_saved_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}

    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def should_use_system_proxy_for_url(url: str) -> bool:
    if not USE_SYSTEM_PROXY:
        return False

    host = (urlparse(url).hostname or "").strip().lower()
    return host not in LOOPBACK_HOSTS


def request_with_network_policy(method: str, url: str, **kwargs: Any) -> requests.Response:
    with requests.Session() as session:
        session.trust_env = should_use_system_proxy_for_url(url)
        return session.request(method, url, **kwargs)


def write_saved_config(payload: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def update_saved_config(*, updates: dict[str, Any] | None = None, removals: set[str] | None = None) -> None:
    payload = load_saved_config()

    if updates:
        payload.update(updates)
    if removals:
        for key in removals:
            payload.pop(key, None)

    if payload:
        write_saved_config(payload)
        return

    try:
        CONFIG_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def get_api_key() -> str:
    env_key = os.getenv("YUNWU_API_KEY", "").strip()
    if env_key:
        return env_key

    env_key = os.getenv("IMAGE_API_KEY", "").strip()
    if env_key:
        return env_key

    return str(load_saved_config().get("api_key", "")).strip()


def set_api_key(api_key: str, persist: bool) -> None:
    os.environ["IMAGE_API_KEY"] = api_key
    os.environ["YUNWU_API_KEY"] = api_key
    if persist:
        update_saved_config(updates={"api_key": api_key})
    else:
        update_saved_config(removals={"api_key"})


def resolve_save_dir_input(save_dir: str) -> Path:
    raw = save_dir.strip()
    if not raw:
        raise ValueError("save_dir 不能为空。")

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (BASE_DIR / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate.exists() and not candidate.is_dir():
        raise ValueError("save_dir 不能指向现有文件。")

    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def looks_like_windows_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value)) or value.startswith("\\\\")


def looks_like_posix_absolute_path(value: str) -> bool:
    return value.startswith("/")


def get_saved_save_dir_value() -> str:
    payload = load_saved_config()

    per_platform = payload.get("save_dir_by_platform")
    if isinstance(per_platform, dict):
        value = str(per_platform.get(CURRENT_PLATFORM_KEY, "")).strip()
        if value:
            return value

    legacy_value = str(payload.get("save_dir", "")).strip()
    if not legacy_value:
        return ""

    if CURRENT_PLATFORM_KEY != "windows" and looks_like_windows_path(legacy_value):
        return ""
    if CURRENT_PLATFORM_KEY == "windows" and looks_like_posix_absolute_path(legacy_value):
        return ""

    return legacy_value


def get_save_dir() -> Path:
    env_value = os.getenv("YUNWU_SAVE_DIR", "").strip()
    if env_value:
        try:
            return resolve_save_dir_input(env_value)
        except ValueError:
            pass

    saved_value = get_saved_save_dir_value()
    if saved_value:
        try:
            return resolve_save_dir_input(saved_value)
        except ValueError:
            pass

    return resolve_save_dir_input(str(DEFAULT_SAVE_DIR))


def set_save_dir(save_dir: str, persist: bool) -> Path:
    resolved = resolve_save_dir_input(save_dir)
    os.environ["YUNWU_SAVE_DIR"] = str(resolved)
    if persist:
        payload = load_saved_config()
        per_platform = payload.get("save_dir_by_platform")
        if not isinstance(per_platform, dict):
            per_platform = {}
        per_platform[CURRENT_PLATFORM_KEY] = str(resolved)
        payload["save_dir_by_platform"] = per_platform
        write_saved_config(payload)
    else:
        payload = load_saved_config()
        per_platform = payload.get("save_dir_by_platform")
        if isinstance(per_platform, dict):
            per_platform.pop(CURRENT_PLATFORM_KEY, None)
            if per_platform:
                payload["save_dir_by_platform"] = per_platform
            else:
                payload.pop("save_dir_by_platform", None)
            if payload:
                write_saved_config(payload)
            else:
                try:
                    CONFIG_PATH.unlink(missing_ok=True)
                except OSError:
                    pass
    return resolved


def load_history_entries() -> list[dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []

    try:
        payload = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    return [item for item in payload if isinstance(item, dict)]


def write_history_entries(entries: list[dict[str, Any]]) -> None:
    HISTORY_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def is_image_mime_type(mime_type: str) -> bool:
    return mime_type.lower().startswith("image/")


def is_video_mime_type(mime_type: str) -> bool:
    return mime_type.lower().startswith("video/")


def build_history_item_response(entry: dict[str, Any]) -> dict[str, Any]:
    mime_type = str(entry.get("mime_type", "")).strip()
    file_url = f"/api/history/{entry['id']}/file"
    return {
        **entry,
        "file_url": file_url,
        "preview_url": file_url if (is_image_mime_type(mime_type) or is_video_mime_type(mime_type)) else "",
        "is_image": is_image_mime_type(mime_type),
        "is_video": is_video_mime_type(mime_type),
    }


def append_history_entries(
    saved_files: list[dict[str, Any]],
    *,
    prompt: str,
    model: str,
    mode: str,
    elapsed_ms: int = 0,
) -> list[dict[str, Any]]:
    if not saved_files:
        return []

    created_at = int(time.time())
    batch_id = uuid4().hex
    new_entries: list[dict[str, Any]] = []
    for item in saved_files:
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        new_entries.append(
            {
                "id": uuid4().hex,
                "batch_id": batch_id,
                "created_at": created_at,
                "prompt": prompt.strip(),
                "model": model,
                "mode": mode,
                "path": path,
                "name": str(item.get("name", "")).strip(),
                "size": int(item.get("size", 0) or 0),
                "elapsed_ms": int(max(elapsed_ms, 0)),
                "mime_type": str(item.get("mime_type", "")).strip(),
                "source": str(item.get("source", "")).strip(),
            }
        )

    if not new_entries:
        return []

    with history_lock:
        entries = load_history_entries()
        merged = new_entries + entries
        write_history_entries(merged[:MAX_HISTORY_ITEMS])

    return new_entries


def list_history_entries(limit: int) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, MAX_HISTORY_ITEMS))
    with history_lock:
        entries = load_history_entries()
        kept_entries: list[dict[str, Any]] = []
        changed = False
        for entry in entries:
            path = Path(str(entry.get("path", "")))
            if not path.is_file():
                changed = True
                continue
            kept_entries.append(entry)

        if changed:
            write_history_entries(kept_entries[:MAX_HISTORY_ITEMS])

    return [build_history_item_response(entry) for entry in kept_entries[:safe_limit]]


def get_history_entry(item_id: str) -> dict[str, Any]:
    with history_lock:
        entries = load_history_entries()

    for entry in entries:
        if entry.get("id") == item_id:
            return entry

    raise HTTPException(status_code=404, detail="历史记录不存在。")


def delete_history_entry(item_id: str) -> dict[str, Any]:
    with history_lock:
        entries = load_history_entries()
        target_entry: dict[str, Any] | None = None
        remaining_entries: list[dict[str, Any]] = []

        for entry in entries:
            if entry.get("id") == item_id and target_entry is None:
                target_entry = entry
                continue
            remaining_entries.append(entry)

        if target_entry is None:
            raise HTTPException(status_code=404, detail="历史记录不存在。")

        write_history_entries(remaining_entries[:MAX_HISTORY_ITEMS])

    return target_entry


def error_payload(message: str, status: int, detail: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"message": message, "status": status}}
    if detail not in (None, ""):
        payload["error"]["detail"] = detail
    return payload


def extract_error_message(detail: Any) -> str | None:
    if isinstance(detail, dict):
        nested_error = detail.get("error")
        if isinstance(nested_error, dict):
            for key in ("message", "detail", "type", "code", "status"):
                value = nested_error.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        for key in ("message", "detail", "error_description", "status"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    if isinstance(detail, str) and detail.strip():
        return detail.strip()

    return None


def is_tls_eof_error_text(text: str) -> bool:
    lowered = text.lower()
    signals = (
        "ssleoferror",
        "unexpected eof while reading",
        "ssl_error_syscall",
        "eof occurred in violation of protocol",
    )
    return any(signal in lowered for signal in signals)


def explain_request_exception(target: str, exc: Exception) -> str:
    detail = str(exc)
    if is_tls_eof_error_text(detail):
        return f"连接{target}时 TLS 握手被中断。请先检查本机代理、DNS 或网络拦截。"
    return f"请求{target}失败。"


def explain_upstream_error(status_code: int, detail: Any, *, model: str | None = None, target: str = "上游接口") -> str:
    message = extract_error_message(detail)
    if isinstance(message, str) and "无可用渠道" in message:
        if model == GEMINI_MODEL:
            return f"当前 API Key / 分组没有 {model} 的可用渠道。请切换到 {GPT_MODEL}，或在云雾后台为当前分组开通该模型。"
        if model:
            return f"当前 API Key / 分组没有 {model} 的可用渠道。请在云雾后台检查 distributor / 渠道配置。"
    if message:
        return message
    return f"{target}返回错误（HTTP {status_code}）。"


def parse_http_header_block(header_text: str) -> tuple[int, str, dict[str, str]]:
    blocks = [block.strip() for block in re.split(r"\r?\n\r?\n", header_text) if block.strip()]
    status_block = ""
    for block in blocks:
        first_line = block.splitlines()[0] if block.splitlines() else ""
        if first_line.upper().startswith("HTTP/"):
            status_block = block

    if not status_block:
        raise OSError("curl 回退未返回有效 HTTP 响应头。")

    lines = status_block.splitlines()
    status_line = lines[0].strip()
    match = re.match(r"^HTTP/\d+(?:\.\d+)?\s+(\d{3})(?:\s+(.*))?$", status_line)
    if not match:
        raise OSError(f"无法解析 curl 回退状态行：{status_line}")

    status_code = int(match.group(1))
    reason = (match.group(2) or "").strip()
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip()] = value.strip()

    return status_code, reason, headers


def build_response_from_raw_http(
    *,
    method: str,
    url: str,
    status_code: int,
    reason: str,
    headers: dict[str, str],
    content: bytes,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.reason = reason
    response.url = url
    response.headers = requests.structures.CaseInsensitiveDict(headers)
    response._content = content
    response.encoding = requests.utils.get_encoding_from_headers(response.headers) or "utf-8"
    response.request = requests.Request(method, url, headers=headers).prepare()
    return response


def post_json_with_macos_curl_fallback(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> requests.Response:
    curl_bin = shutil.which("curl")
    if not curl_bin:
        raise OSError("macOS 系统 curl 回退不可用：未找到 curl。")

    prepared_url = requests.Request("POST", url, params=params).prepare().url or url
    header_path: Path | None = None
    body_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(prefix="yunwu-curl-head-", suffix=".txt", delete=False) as head_file:
            header_path = Path(head_file.name)
        with tempfile.NamedTemporaryFile(prefix="yunwu-curl-body-", suffix=".bin", delete=False) as body_file:
            body_path = Path(body_file.name)

        command = [
            curl_bin,
            "--http1.1",
            "--silent",
            "--show-error",
            "--location",
            "--connect-timeout",
            str(REQUEST_TIMEOUT[0]),
            "--max-time",
            str(REQUEST_TIMEOUT[1]),
            "-D",
            str(header_path),
            "-o",
            str(body_path),
            "-X",
            "POST",
            prepared_url,
        ]
        if not should_use_system_proxy_for_url(prepared_url):
            command.extend(["--proxy", ""])
        for key, value in headers.items():
            command.extend(["-H", f"{key}: {value}"])
        command.extend(["--data-binary", json.dumps(payload, ensure_ascii=False)])

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT[1] + 10,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown curl error"
            raise OSError(stderr)

        header_text = header_path.read_text(encoding="utf-8", errors="replace")
        content = body_path.read_bytes()
        status_code, reason, parsed_headers = parse_http_header_block(header_text)
        return build_response_from_raw_http(
            method="POST",
            url=prepared_url,
            status_code=status_code,
            reason=reason,
            headers=parsed_headers,
            content=content,
        )
    except subprocess.TimeoutExpired as exc:
        raise OSError("macOS 系统 curl 回退超时。") from exc
    finally:
        for path in (header_path, body_path):
            if path is None:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def post_json_with_local_tls_fallback(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> requests.Response:
    try:
        return request_with_network_policy(
            "POST",
            url,
            headers=headers,
            params=params,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        raise
    except requests.RequestException as exc:
        if sys.platform != "darwin" or not is_tls_eof_error_text(str(exc)):
            raise
        try:
            return post_json_with_macos_curl_fallback(url, headers=headers, payload=payload, params=params)
        except OSError as fallback_exc:
            raise OSError(f"requests 请求失败：{exc}; macOS 系统 curl 回退也失败：{fallback_exc}") from exc


def build_local_save_message(
    *,
    subject: str,
    saved_count: int,
    save_errors: list[str],
    empty_message: str,
) -> str:
    error_count = len(save_errors)
    if saved_count and error_count:
        return f"{subject}，已自动保存 {saved_count} 个文件，另有 {error_count} 个文件保存失败。"
    if saved_count:
        return f"{subject}，并已自动保存 {saved_count} 个文件。"
    if error_count:
        if all(is_tls_eof_error_text(item) for item in save_errors):
            return f"{subject}，但当前网络环境无法直连媒体 CDN，自动保存失败；页面预览和原始 URL 仍可用。"
        return f"{subject}，但自动保存失败。"
    return empty_message


def parse_json_response(response: requests.Response) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    try:
        return response.json(), None
    except ValueError:
        text = response.text.strip()
        if not text:
            return None, "响应体为空。"
        return None, text[:1000]


def read_upload_bytes(upload: UploadFile) -> tuple[str, bytes, str]:
    filename = upload.filename or "upload.bin"
    content_type = upload.content_type or "application/octet-stream"
    content = upload.file.read()
    return filename, content, content_type


def validate_model(model: str) -> str | None:
    if model not in SUPPORTED_MODELS:
        return "model 不支持。"
    return None


def validate_prompt(prompt: str, limit: int = PROMPT_MAX_LENGTH) -> str | None:
    prompt = prompt.strip()
    if not prompt:
        return "prompt 不能为空。"
    if len(prompt) > limit:
        return f"prompt 长度不能超过 {limit} 个字符。"
    return None


def validate_n(n: int) -> str | None:
    if n < 1 or n > 10:
        return "n 必须是 1 到 10 的整数。"
    return None


def validate_gpt_size(size: str) -> str | None:
    if size not in GPT_ALLOWED_SIZES:
        return "size 取值不合法。"
    return None


def validate_gpt_aspect_ratio(aspect_ratio: str) -> str | None:
    if aspect_ratio not in GPT_ALLOWED_ASPECT_RATIOS:
        return "aspect_ratio 取值不合法。"
    return None


def resolve_gpt_aspect_ratio(size: str, aspect_ratio: str) -> tuple[str | None, str | None, list[str] | None]:
    normalized_aspect_ratio = aspect_ratio.strip()
    if normalized_aspect_ratio:
        aspect_ratio_error = validate_gpt_aspect_ratio(normalized_aspect_ratio)
        if aspect_ratio_error is not None:
            return None, aspect_ratio_error, sorted(GPT_ALLOWED_ASPECT_RATIOS)
        return normalized_aspect_ratio, None, None

    normalized_size = size.strip()
    size_error = validate_gpt_size(normalized_size)
    if size_error is not None:
        return None, size_error, sorted(GPT_ALLOWED_SIZES)

    return GPT_SIZE_TO_ASPECT_RATIO.get(normalized_size, GPT_DEFAULT_ASPECT_RATIO), None, None


def gpt_size_for_aspect_ratio(aspect_ratio: str) -> str:
    return GPT_ASPECT_RATIO_TO_SIZE.get(aspect_ratio, "auto")


def validate_gemini_aspect_ratio(aspect_ratio: str) -> str | None:
    if aspect_ratio not in GEMINI_ALLOWED_ASPECT_RATIOS:
        return "aspect_ratio 取值不合法。"
    return None


def validate_gemini_image_size(image_size: str) -> str | None:
    if image_size not in GEMINI_ALLOWED_IMAGE_SIZES:
        return "image_size 取值不合法。"
    return None


def validate_video_model(model: str) -> str | None:
    if model not in VIDEO_ALLOWED_MODELS:
        return "视频模型不支持。"
    return None


def validate_video_seconds(seconds: str) -> str | None:
    if seconds not in VIDEO_ALLOWED_SECONDS:
        return "seconds 取值不合法。"
    return None


def validate_video_size(size: str) -> str | None:
    if size not in VIDEO_ALLOWED_SIZES:
        return "视频尺寸取值不合法。"
    return None


def validate_video_watermark(watermark: str) -> str | None:
    if watermark not in VIDEO_ALLOWED_WATERMARKS:
        return "watermark 取值不合法。"
    return None


def build_video_headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_video_model_candidates(model: str, reference_count: int) -> list[str]:
    candidates = [model]
    if reference_count >= 2 and not model.endswith("-fl"):
        candidates.append(f"{model}-fl")
    return dedupe_preserve_order(candidates)


def build_video_create_attempts(
    data: dict[str, str],
    reference_files: list[tuple[str, bytes, str]],
) -> list[dict[str, Any]]:
    reference_count = len(reference_files)
    attempts: list[dict[str, Any]] = []

    if reference_count == 0:
        attempts.append(
            {
                "label": "文生视频",
                "data": dict(data),
                "files": [],
                "field_name": "",
                "reference_count": 0,
                "submitted_model": data["model"],
            }
        )
        return attempts

    field_names = ["input_reference", "input_reference[]"]
    mode_label = "首尾帧模式" if reference_count >= 2 else "首帧 / 参考图模式"

    for model_candidate in build_video_model_candidates(data["model"], reference_count):
        for field_name in field_names:
            attempts.append(
                {
                    "label": f"{mode_label} · {model_candidate} · {field_name}",
                    "data": {**data, "model": model_candidate},
                    "files": [(field_name, file_tuple) for file_tuple in reference_files],
                    "field_name": field_name,
                    "reference_count": reference_count,
                    "submitted_model": model_candidate,
                }
            )

    return attempts


def should_retry_video_create_attempt(status_code: int, detail: Any) -> bool:
    if status_code in {400, 404, 409, 415, 422}:
        return True

    message = (extract_error_message(detail) or "").lower()
    if not message:
        return False

    signals = (
        "input_reference",
        "multipart",
        "form-data",
        "parameter",
        "field",
        "model",
        "unknown",
        "array",
        "file",
    )
    return any(signal in message for signal in signals)


def normalize_remote_video_status(status: Any) -> str:
    return str(status or "").strip().lower()


def build_video_status_message(payload: dict[str, Any], *, created: bool = False) -> str:
    remote_status = normalize_remote_video_status(payload.get("status")) or "queued"
    progress = payload.get("progress")

    parts = [f"远端状态 {remote_status}"]
    if isinstance(progress, (int, float)):
        parts.append(f"进度 {int(progress)}%")
    if isinstance(payload.get("seconds"), str) and payload["seconds"].strip():
        parts.append(f"时长 {payload['seconds'].strip()} 秒")
    if isinstance(payload.get("size"), str) and payload["size"].strip():
        parts.append(f"尺寸 {payload['size'].strip()}")

    prefix = "视频任务已创建" if created else "视频任务仍在处理中"
    return f"{prefix}，{'，'.join(parts)}。"


def create_job(mode: str) -> JobRecord:
    job = JobRecord(mode)
    with jobs_lock:
        jobs[job.id] = job
        cleanup_jobs_locked()
    return job


def get_job(job_id: str) -> JobRecord:
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在。")
    return job


def cleanup_jobs_locked() -> None:
    now = time.time()
    expired_ids = [
        job_id
        for job_id, job in jobs.items()
        if job.completed_at is not None and now - job.completed_at > JOB_TTL_SECONDS
    ]
    for job_id in expired_ids:
        jobs.pop(job_id, None)

    completed_ids = [job_id for job_id, job in jobs.items() if job.completed_at is not None]
    if len(completed_ids) <= MAX_COMPLETED_JOBS:
        return

    completed_ids.sort(key=lambda item: jobs[item].completed_at or 0)
    overflow = len(completed_ids) - MAX_COMPLETED_JOBS
    for job_id in completed_ids[:overflow]:
        jobs.pop(job_id, None)


def slugify_filename_component(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-._")
    return cleaned[:48] or "output"


def unique_output_path(save_dir: Path, filename: str) -> Path:
    target = save_dir / filename
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    counter = 2
    while True:
        candidate = save_dir / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def guess_extension(*, url: str | None = None, mime_type: str | None = None, default: str = ".bin") -> str:
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if mime:
        guessed = mimetypes.guess_extension(mime)
        if guessed:
            if guessed == ".jpe":
                return ".jpg"
            return guessed

    if url:
        path = urlparse(url).path
        suffix = Path(path).suffix.lower()
        if suffix:
            return suffix

    return default


def download_remote_asset_with_macos_urlsession(url: str) -> tuple[bytes, str | None]:
    swift_bin = shutil.which("swift")
    if not swift_bin:
        raise OSError("macOS 系统下载回退不可用：未找到 swift。")

    swift_script = r"""
import Foundation

func fail(_ message: String, code: Int32) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    Foundation.exit(code)
}

let urlString = CommandLine.arguments[1]
let outputPath = CommandLine.arguments[2]

guard let url = URL(string: urlString) else {
    fail("invalid-url", code: 2)
}

func writeResult(data: Data, mimeType: String?) {
    do {
        try data.write(to: URL(fileURLWithPath: outputPath))
        FileHandle.standardOutput.write(Data(((mimeType ?? "") + "\n").utf8))
    } catch {
        fail("write-failed: \(error)", code: 7)
    }
}

if url.isFileURL {
    do {
        let data = try Data(contentsOf: url)
        writeResult(data: data, mimeType: nil)
        Foundation.exit(0)
    } catch {
        fail("file-read-failed: \(error)", code: 3)
    }
}

let config = URLSessionConfiguration.ephemeral
config.timeoutIntervalForRequest = 180
config.timeoutIntervalForResource = 195

let semaphore = DispatchSemaphore(value: 0)
var resultData: Data?
var resultMimeType: String?
var resultError: Error?

let session = URLSession(configuration: config)
let task = session.dataTask(with: url) { data, response, error in
    resultData = data
    resultMimeType = response?.mimeType
    resultError = error
    semaphore.signal()
}

task.resume()

if semaphore.wait(timeout: .now() + 195) == .timedOut {
    task.cancel()
    fail("timeout", code: 4)
}

if let error = resultError {
    fail("request-failed: \(error)", code: 5)
}

guard let data = resultData else {
    fail("empty-response-body", code: 6)
}

writeResult(data: data, mimeType: resultMimeType)
"""

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="yunwu-remote-", suffix=".bin", delete=False) as handle:
            temp_path = Path(handle.name)

        completed = subprocess.run(
            [swift_bin, "-e", swift_script, url, str(temp_path)],
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT[1] + 20,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown swift download error"
            raise OSError(stderr)

        content = temp_path.read_bytes()
        if not content:
            raise OSError("macOS 系统下载回退返回空文件。")

        mime_type = completed.stdout.strip().splitlines()[-1].strip() if completed.stdout.strip() else ""
        return content, mime_type or None
    except subprocess.TimeoutExpired as exc:
        raise OSError("macOS 系统下载回退超时。") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def download_remote_asset(url: str) -> tuple[bytes, str | None]:
    try:
        response = request_with_network_policy("GET", url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        mime_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip() or None
        return response.content, mime_type
    except requests.RequestException as exc:
        if sys.platform != "darwin":
            raise

        try:
            return download_remote_asset_with_macos_urlsession(url)
        except OSError as fallback_exc:
            raise OSError(f"requests 下载失败：{exc}; macOS 系统下载回退也失败：{fallback_exc}") from exc


def extract_media_candidates(payload: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_blobs: set[tuple[str, str]] = set()

    def add_url(url: str, label: str) -> None:
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        candidates.append({"kind": "url", "url": url, "label": label})

    def add_base64(data: str, mime_type: str, label: str) -> None:
        if not data:
            return
        key = (mime_type, data)
        if key in seen_blobs:
            return
        seen_blobs.add(key)
        candidates.append({"kind": "base64", "data": data, "mime_type": mime_type, "label": label})

    def walk(value: Any, depth: int = 0) -> None:
        if value is None or depth > 8:
            return

        if isinstance(value, list):
            for item in value:
                walk(item, depth + 1)
            return

        if not isinstance(value, dict):
            return

        if isinstance(value.get("url"), str):
            add_url(value["url"], "url")
        if isinstance(value.get("image_url"), str):
            add_url(value["image_url"], "image_url")
        if isinstance(value.get("video_url"), str):
            add_url(value["video_url"], "video_url")
        if isinstance(value.get("file_url"), str):
            add_url(value["file_url"], "file_url")

        if isinstance(value.get("b64_json"), str):
            add_base64(value["b64_json"], "image/png", "b64_json")
        if isinstance(value.get("b64"), str):
            add_base64(value["b64"], "image/png", "b64")

        inline_data = value.get("inlineData")
        if isinstance(inline_data, dict) and isinstance(inline_data.get("data"), str):
            add_base64(
                inline_data["data"],
                str(inline_data.get("mimeType", "application/octet-stream")),
                "inlineData",
            )

        inline_data = value.get("inline_data")
        if isinstance(inline_data, dict) and isinstance(inline_data.get("data"), str):
            add_base64(
                inline_data["data"],
                str(inline_data.get("mime_type", "application/octet-stream")),
                "inline_data",
            )

        for item in value.values():
            walk(item, depth + 1)

    walk(payload)
    return candidates


def save_media_outputs(result: Any, *, prompt: str, model: str, mode: str) -> tuple[list[dict[str, Any]], list[str], str]:
    save_dir = get_save_dir()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    prompt_slug = slugify_filename_component(prompt)
    model_slug = slugify_filename_component(model)
    mode_slug = slugify_filename_component(mode)

    saved_files: list[dict[str, Any]] = []
    errors: list[str] = []

    for index, candidate in enumerate(extract_media_candidates(result), start=1):
        try:
            if candidate["kind"] == "url":
                content, mime_type = download_remote_asset(candidate["url"])
                extension = guess_extension(url=candidate["url"], mime_type=mime_type)
            else:
                content = base64.b64decode(candidate["data"], validate=True)
                mime_type = candidate.get("mime_type")
                extension = guess_extension(mime_type=mime_type, default=".png")

            filename = f"{timestamp}-{model_slug}-{mode_slug}-{prompt_slug}-{index:02d}{extension}"
            target_path = unique_output_path(save_dir, filename)
            target_path.write_bytes(content)
            saved_files.append(
                {
                    "path": str(target_path),
                    "name": target_path.name,
                    "size": len(content),
                    "mime_type": mime_type or "",
                    "source": candidate["label"],
                }
            )
        except (OSError, requests.RequestException, binascii.Error, ValueError) as exc:
            source = candidate.get("url") or candidate.get("label", "asset")
            errors.append(f"{source}: {exc}")

    return saved_files, errors, str(save_dir)


def download_video_content(video_id: str, api_key: str) -> tuple[bytes, str | None]:
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    response = request_with_network_policy(
        "GET",
        VIDEO_CONTENT_URL_TEMPLATE.format(video_id=video_id),
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    mime_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip() or None
    return response.content, mime_type


def save_video_outputs(
    result: Any,
    *,
    video_id: str,
    prompt: str,
    model: str,
    mode: str,
    api_key: str,
) -> tuple[list[dict[str, Any]], list[str], str]:
    save_dir = get_save_dir()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    prompt_slug = slugify_filename_component(prompt)
    model_slug = slugify_filename_component(model)
    mode_slug = slugify_filename_component(mode)

    saved_files: list[dict[str, Any]] = []
    errors: list[str] = []

    if video_id:
        try:
            last_error: Exception | None = None
            content = b""
            mime_type: str | None = None
            for attempt in range(3):
                try:
                    content, mime_type = download_video_content(video_id, api_key)
                    last_error = None
                    break
                except (requests.RequestException, ValueError) as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(2)
            if last_error is not None:
                raise last_error
            extension = guess_extension(mime_type=mime_type, default=".mp4")
            filename = f"{timestamp}-{model_slug}-{mode_slug}-{prompt_slug}-{video_id}{extension}"
            target_path = unique_output_path(save_dir, filename)
            target_path.write_bytes(content)
            saved_files.append(
                {
                    "path": str(target_path),
                    "name": target_path.name,
                    "size": len(content),
                    "mime_type": mime_type or "video/mp4",
                    "source": "video_content",
                }
            )
        except (OSError, requests.RequestException, ValueError) as exc:
            errors.append(f"download_content({video_id}): {exc}")

    if saved_files:
        return saved_files, errors, str(save_dir)

    fallback_files, fallback_errors, fallback_dir = save_media_outputs(
        result,
        prompt=prompt,
        model=model,
        mode=mode,
    )
    errors.extend(fallback_errors)
    return fallback_files, errors, fallback_dir


def enrich_result_with_local_saves(
    result: Any,
    *,
    prompt: str,
    model: str,
    mode: str,
    elapsed_ms: int = 0,
) -> tuple[Any, str]:
    if isinstance(result, dict):
        enriched: dict[str, Any] = dict(result)
    else:
        enriched = {"upstream_result": result}

    saved_files, save_errors, save_dir = save_media_outputs(result, prompt=prompt, model=model, mode=mode)
    history_items = append_history_entries(
        saved_files,
        prompt=prompt,
        model=model,
        mode=mode,
        elapsed_ms=elapsed_ms,
    )
    if saved_files:
        enriched["_local_saves"] = saved_files
        enriched["_save_dir"] = save_dir
    if history_items:
        enriched["_history_items"] = [build_history_item_response(item) for item in history_items]
    if save_errors:
        enriched["_local_save_errors"] = save_errors

    message = build_local_save_message(
        subject="上游结果已返回",
        saved_count=len(saved_files),
        save_errors=save_errors,
        empty_message="上游结果已返回，但没有解析到可自动保存的媒体文件。",
    )

    return enriched, message


def enrich_video_result_with_local_saves(
    result: Any,
    *,
    prompt: str,
    model: str,
    mode: str,
    api_key: str,
    elapsed_ms: int = 0,
) -> tuple[Any, str]:
    if isinstance(result, dict):
        enriched: dict[str, Any] = dict(result)
    else:
        enriched = {"upstream_result": result}

    video_id = str(enriched.get("id", "")).strip()
    saved_files, save_errors, save_dir = save_video_outputs(
        result,
        video_id=video_id,
        prompt=prompt,
        model=model,
        mode=mode,
        api_key=api_key,
    )
    history_items = append_history_entries(
        saved_files,
        prompt=prompt,
        model=model,
        mode=mode,
        elapsed_ms=elapsed_ms,
    )
    if saved_files:
        enriched["_local_saves"] = saved_files
        enriched["_save_dir"] = save_dir
    if history_items:
        enriched["_history_items"] = [build_history_item_response(item) for item in history_items]
    if save_errors:
        enriched["_local_save_errors"] = save_errors

    message = build_local_save_message(
        subject="视频任务已完成",
        saved_count=len(saved_files),
        save_errors=save_errors,
        empty_message="视频任务已完成，但没有拿到可保存的视频文件。",
    )

    return enriched, message


def finalize_job_success(job: JobRecord, result: Any, message: str) -> None:
    job.update(status="completed", phase="completed", message=message, result=result)


def finalize_job_error(job: JobRecord, status: int, message: str, detail: Any | None = None) -> None:
    job.update(
        status="failed",
        phase="failed",
        message=message,
        error=error_payload(message, status, detail)["error"],
    )


def execute_gpt_generate_job(job: JobRecord, data: dict[str, Any], api_key: str) -> None:
    job.update(status="running", phase="calling_upstream", message="已发送到上游，等待 gpt-image 文生图结果。")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        upstream = post_json_with_local_tls_fallback(
            GPT_GENERATE_URL,
            headers=headers,
            payload=data,
        )
    except requests.Timeout:
        finalize_job_error(job, 504, "请求上游接口超时。")
        return
    except (requests.RequestException, OSError) as exc:
        finalize_job_error(job, 502, explain_request_exception("上游接口", exc), str(exc))
        return

    job.update(phase="processing_response", message="上游已返回响应，正在整理结果。")
    payload_data, parse_error = parse_json_response(upstream)
    if parse_error is not None:
        finalize_job_error(job, 502, "上游接口返回了非 JSON 响应。", parse_error)
        return

    if upstream.ok:
        enriched, message = enrich_result_with_local_saves(
            payload_data,
            prompt=str(data.get("prompt", "")),
            model=GPT_MODEL,
            mode="generate",
            elapsed_ms=job.snapshot()["elapsed_ms"],
        )
        finalize_job_success(job, enriched, message)
        return

    detail = payload_data
    message = explain_upstream_error(upstream.status_code, detail, model=GPT_MODEL)
    finalize_job_error(job, upstream.status_code, message, detail)


def execute_gpt_edit_job(
    job: JobRecord,
    data: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    api_key: str,
) -> None:
    job.update(status="running", phase="calling_upstream", message="已发送到上游，等待 gpt-image 图生图结果。")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        upstream = request_with_network_policy(
            "POST",
            GPT_EDIT_URL,
            headers=headers,
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        finalize_job_error(job, 504, "请求上游接口超时。")
        return
    except requests.RequestException as exc:
        finalize_job_error(job, 502, explain_request_exception("上游接口", exc), str(exc))
        return

    job.update(phase="processing_response", message="上游已返回响应，正在整理结果。")
    payload_data, parse_error = parse_json_response(upstream)
    if parse_error is not None:
        finalize_job_error(job, 502, "上游接口返回了非 JSON 响应。", parse_error)
        return

    if upstream.ok:
        enriched, message = enrich_result_with_local_saves(
            payload_data,
            prompt=str(data.get("prompt", "")),
            model=GPT_MODEL,
            mode="edit",
            elapsed_ms=job.snapshot()["elapsed_ms"],
        )
        finalize_job_success(job, enriched, message)
        return

    detail = payload_data
    message = explain_upstream_error(upstream.status_code, detail, model=GPT_MODEL)
    finalize_job_error(job, upstream.status_code, message, detail)


def execute_gemini_job(
    job: JobRecord,
    model: str,
    payload: dict[str, Any],
    api_key: str,
    upstream_message: str,
    mode: str,
) -> None:
    job.update(status="running", phase="calling_upstream", message=upstream_message)
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    url = GEMINI_URL_TEMPLATE.format(model=model)

    try:
        upstream = post_json_with_local_tls_fallback(
            url,
            params={"key": api_key},
            headers=headers,
            payload=payload,
        )
    except requests.Timeout:
        finalize_job_error(job, 504, "请求上游接口超时。")
        return
    except (requests.RequestException, OSError) as exc:
        finalize_job_error(job, 502, explain_request_exception("上游接口", exc), str(exc))
        return

    job.update(phase="processing_response", message="上游已返回响应，正在整理结果。")
    payload_data, parse_error = parse_json_response(upstream)
    if parse_error is not None:
        finalize_job_error(job, 502, "上游接口返回了非 JSON 响应。", parse_error)
        return

    if upstream.ok:
        prompt = ""
        contents = payload.get("contents")
        if isinstance(contents, list) and contents:
            parts = contents[0].get("parts") if isinstance(contents[0], dict) else None
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        prompt = part["text"]
                        break

        enriched, message = enrich_result_with_local_saves(
            payload_data,
            prompt=prompt,
            model=model,
            mode=mode,
            elapsed_ms=job.snapshot()["elapsed_ms"],
        )
        finalize_job_success(job, enriched, message)
        return

    detail = payload_data
    message = explain_upstream_error(upstream.status_code, detail, model=model)
    finalize_job_error(job, upstream.status_code, message, detail)


def execute_video_job(
    job: JobRecord,
    data: dict[str, str],
    reference_files: list[tuple[str, bytes, str]],
    api_key: str,
) -> None:
    attempts = build_video_create_attempts(data, reference_files)
    job.update(status="running", phase="calling_upstream", message="已发送到上游，正在创建视频任务。")
    headers = build_video_headers(api_key)
    payload_data: dict[str, Any] | None = None
    used_attempt: dict[str, Any] | None = None

    for index, attempt in enumerate(attempts, start=1):
        job.update(
            status="running",
            phase="calling_upstream",
            message=f"正在创建视频任务，尝试 {index}/{len(attempts)}：{attempt['label']}。",
        )
        try:
            upstream = request_with_network_policy(
                "POST",
                VIDEO_CREATE_URL,
                headers=headers,
                data=attempt["data"],
                files=attempt["files"],
                timeout=REQUEST_TIMEOUT,
            )
        except requests.Timeout:
            finalize_job_error(job, 504, "请求上游视频接口超时。")
            return
        except requests.RequestException as exc:
            finalize_job_error(job, 502, explain_request_exception("上游视频接口", exc), str(exc))
            return

        raw_payload, parse_error = parse_json_response(upstream)
        detail = raw_payload if parse_error is None else parse_error

        if upstream.ok:
            if parse_error is not None:
                finalize_job_error(job, 502, "上游视频接口返回了非 JSON 响应。", parse_error)
                return
            if not isinstance(raw_payload, dict):
                finalize_job_error(job, 502, "上游视频接口返回了无法识别的响应结构。", raw_payload)
                return
            payload_data = raw_payload
            used_attempt = attempt
            break

        if index < len(attempts) and should_retry_video_create_attempt(upstream.status_code, detail):
            continue

        message = explain_upstream_error(
            upstream.status_code,
            detail,
            model=str(attempt["submitted_model"]),
            target="上游视频接口",
        )
        finalize_job_error(job, upstream.status_code, message, detail)
        return

    if payload_data is None or used_attempt is None:
        finalize_job_error(job, 502, "视频任务创建失败，兼容形态回退后仍未成功。")
        return

    video_id = str(payload_data.get("id", "")).strip()
    remote_status = normalize_remote_video_status(payload_data.get("status"))
    prompt = str(data.get("prompt", "")).strip()
    model = str(payload_data.get("model") or used_attempt["submitted_model"]).strip()

    if used_attempt["submitted_model"] != data.get("model") or used_attempt["field_name"]:
        payload_data = {
            **payload_data,
            "_request_inference": {
                "submitted_model": used_attempt["submitted_model"],
                "field_name": used_attempt["field_name"],
                "reference_count": used_attempt["reference_count"],
            },
        }

    if remote_status in VIDEO_REMOTE_FAILURE_STATUSES:
        detail = payload_data.get("error") or payload_data
        message = extract_error_message(detail) or "视频任务创建失败。"
        finalize_job_error(job, 502, message, detail)
        return

    if remote_status in VIDEO_REMOTE_SUCCESS_STATUSES:
        enriched, message = enrich_video_result_with_local_saves(
            payload_data,
            prompt=prompt,
            model=model,
            mode="video",
            api_key=api_key,
            elapsed_ms=job.snapshot()["elapsed_ms"],
        )
        finalize_job_success(job, enriched, message)
        return

    if not video_id:
        finalize_job_error(job, 502, "视频任务已创建，但上游没有返回任务 ID，无法继续查询。", payload_data)
        return

    job.update(
        status="running",
        phase="calling_upstream",
        message=build_video_status_message(payload_data, created=True),
        result=payload_data,
    )

    deadline = time.monotonic() + VIDEO_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(VIDEO_POLL_INTERVAL_SECONDS)

        try:
            upstream = request_with_network_policy(
                "GET",
                VIDEO_STATUS_URL_TEMPLATE.format(video_id=video_id),
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.Timeout:
            finalize_job_error(job, 504, "轮询上游视频任务超时。")
            return
        except requests.RequestException as exc:
            finalize_job_error(job, 502, explain_request_exception("上游视频任务", exc), str(exc))
            return

        payload_data, parse_error = parse_json_response(upstream)
        if parse_error is not None:
            finalize_job_error(job, 502, "上游视频查询接口返回了非 JSON 响应。", parse_error)
            return

        if not upstream.ok:
            detail = payload_data
            message = explain_upstream_error(upstream.status_code, detail, model=model, target="上游视频任务")
            finalize_job_error(job, upstream.status_code, message, detail)
            return

        if not isinstance(payload_data, dict):
            finalize_job_error(job, 502, "上游视频查询接口返回了无法识别的响应结构。", payload_data)
            return

        remote_status = normalize_remote_video_status(payload_data.get("status"))
        if remote_status in VIDEO_REMOTE_SUCCESS_STATUSES:
            job.update(phase="processing_response", message="视频任务已完成，正在下载成片。", result=payload_data)
            enriched, message = enrich_video_result_with_local_saves(
                payload_data,
                prompt=prompt,
                model=model,
                mode="video",
                api_key=api_key,
                elapsed_ms=job.snapshot()["elapsed_ms"],
            )
            finalize_job_success(job, enriched, message)
            return

        if remote_status in VIDEO_REMOTE_FAILURE_STATUSES:
            detail = payload_data.get("error") or payload_data
            message = extract_error_message(detail) or "视频任务执行失败。"
            finalize_job_error(job, 502, message, detail)
            return

        job.update(
            status="running",
            phase="calling_upstream",
            message=build_video_status_message(payload_data),
            result=payload_data,
        )

    finalize_job_error(job, 504, "视频任务轮询超时，请稍后重新查询。", {"id": video_id})


def build_gemini_inline_part(file_tuple: tuple[str, bytes, str]) -> dict[str, Any]:
    _, content, content_type = file_tuple
    return {
        "inline_data": {
            "mime_type": content_type,
            "data": base64.b64encode(content).decode("ascii"),
        }
    }


def build_gemini_payload(
    prompt: str,
    aspect_ratio: str,
    image_size: str,
    inline_parts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [{"text": prompt.strip()}]
    if inline_parts:
        parts.extend(inline_parts)

    return {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": aspect_ratio,
                "imageSize": image_size,
            },
        },
    }


def spawn_job(target: Any, *args: Any) -> None:
    Thread(target=target, args=args, daemon=True).start()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "apiKeyConfigured": bool(get_api_key()),
        "supportsApiKeyUpdate": True,
        "supportsSaveDirUpdate": True,
        "saveDir": str(get_save_dir()),
    }


@app.post("/api/settings/api-key")
def update_api_key(payload: ApiKeyUpdateRequest) -> JSONResponse:
    api_key = payload.api_key.strip()
    if not api_key:
        return JSONResponse(status_code=422, content=error_payload("api_key 不能为空。", 422))

    try:
        set_api_key(api_key, payload.persist)
    except OSError as exc:
        return JSONResponse(
            status_code=500,
            content=error_payload("密钥已更新到当前服务，但写入本地配置失败。", 500, str(exc)),
        )

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "message": "API Key 已更新，你可以直接重新提交请求。",
            "persisted": payload.persist,
        },
    )


@app.post("/api/settings/save-dir")
def update_save_dir(payload: SaveDirUpdateRequest) -> JSONResponse:
    try:
        save_dir = set_save_dir(payload.save_dir, payload.persist)
    except ValueError as exc:
        return JSONResponse(status_code=422, content=error_payload(str(exc), 422))
    except OSError as exc:
        return JSONResponse(
            status_code=500,
            content=error_payload("保存路径已更新到当前服务，但写入本地配置失败。", 500, str(exc)),
        )

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "message": "保存路径已更新，后续生成文件会自动保存到该目录。",
            "saveDir": str(save_dir),
            "persisted": payload.persist,
        },
    )


@app.get("/api/history")
def history_list(limit: int = 24) -> dict[str, Any]:
    return {
        "ok": True,
        "items": list_history_entries(limit),
    }


@app.get("/api/history/{item_id}/file")
def history_file(item_id: str) -> FileResponse:
    entry = get_history_entry(item_id)
    path = Path(str(entry.get("path", "")))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="历史文件不存在。")

    mime_type = str(entry.get("mime_type", "")).strip() or None
    filename = str(entry.get("name", "")).strip() or path.name
    return FileResponse(path, media_type=mime_type, filename=filename)


@app.delete("/api/history/{item_id}")
def history_delete(item_id: str) -> JSONResponse:
    try:
        entry = delete_history_entry(item_id)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=error_payload(str(exc.detail), exc.status_code))
    except OSError as exc:
        return JSONResponse(status_code=500, content=error_payload("删除历史记录失败。", 500, str(exc)))

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "message": "历史记录已删除，本地文件保留。",
            "name": str(entry.get("name", "")).strip(),
        },
    )


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    return get_job(job_id).snapshot()


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str) -> StreamingResponse:
    job = get_job(job_id)

    def event_stream() -> Any:
        while True:
            snapshot = job.snapshot()
            yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
            if snapshot["status"] in TERMINAL_STATUSES:
                break
            time.sleep(1)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@app.post("/api/video-create")
def video_create(
    model: str = Form("veo_3_1"),
    prompt: str = Form(...),
    seconds: str = Form("8"),
    input_reference: Optional[UploadFile] = File(None),
    input_reference_end: Optional[UploadFile] = File(None),
    size: str = Form("16x9"),
    watermark: str = Form("false"),
) -> JSONResponse:
    api_key = get_api_key()
    if not api_key:
        return JSONResponse(status_code=503, content=error_payload("未配置 API Key。", 503))

    prompt_error = validate_prompt(prompt, PROMPT_MAX_LENGTH)
    if prompt_error is not None:
        return JSONResponse(status_code=422, content=error_payload(prompt_error, 422))

    model_error = validate_video_model(model)
    if model_error is not None:
        return JSONResponse(status_code=422, content=error_payload(model_error, 422, sorted(VIDEO_ALLOWED_MODELS)))

    seconds_error = validate_video_seconds(seconds)
    if seconds_error is not None:
        return JSONResponse(status_code=422, content=error_payload(seconds_error, 422, sorted(VIDEO_ALLOWED_SECONDS)))

    size_error = validate_video_size(size)
    if size_error is not None:
        return JSONResponse(status_code=422, content=error_payload(size_error, 422, sorted(VIDEO_ALLOWED_SIZES)))

    watermark_error = validate_video_watermark(watermark)
    if watermark_error is not None:
        return JSONResponse(
            status_code=422,
            content=error_payload(watermark_error, 422, sorted(VIDEO_ALLOWED_WATERMARKS)),
        )

    reference_file: tuple[str, bytes, str] | None = None
    reference_end_file: tuple[str, bytes, str] | None = None
    if input_reference is not None and input_reference.filename:
        reference_file = read_upload_bytes(input_reference)
    if input_reference_end is not None and input_reference_end.filename:
        reference_end_file = read_upload_bytes(input_reference_end)
    if input_reference is not None:
        input_reference.file.close()
    if input_reference_end is not None:
        input_reference_end.file.close()

    if reference_file is None and reference_end_file is not None:
        return JSONResponse(status_code=422, content=error_payload("尾帧不能单独上传，至少先提供首帧。", 422))

    reference_files: list[tuple[str, bytes, str]] = []
    if reference_file is not None:
        reference_files.append(reference_file)
    if reference_end_file is not None:
        reference_files.append(reference_end_file)

    data = {
        "model": model,
        "prompt": prompt.strip(),
        "seconds": seconds,
        "size": size,
        "watermark": watermark,
    }
    job = create_job("video")
    spawn_job(execute_video_job, job, data, reference_files, api_key)
    return JSONResponse(status_code=202, content=job.snapshot())


@app.post("/api/image-generate")
def image_generate(payload: GenerateRequest) -> JSONResponse:
    api_key = get_api_key()
    if not api_key:
        return JSONResponse(status_code=503, content=error_payload("未配置 API Key。", 503))

    model_error = validate_model(payload.model)
    if model_error is not None:
        return JSONResponse(status_code=422, content=error_payload(model_error, 422, sorted(SUPPORTED_MODELS)))

    prompt_error = validate_prompt(payload.prompt, PROMPT_MAX_LENGTH)
    if prompt_error is not None:
        return JSONResponse(status_code=422, content=error_payload(prompt_error, 422))

    if payload.model == GPT_MODEL:
        n_error = validate_n(payload.n)
        if n_error is not None:
            return JSONResponse(status_code=422, content=error_payload(n_error, 422))

        gpt_aspect_ratio, gpt_geometry_error, gpt_allowed_values = resolve_gpt_aspect_ratio(
            payload.size,
            payload.aspect_ratio,
        )
        if gpt_geometry_error is not None:
            return JSONResponse(status_code=422, content=error_payload(gpt_geometry_error, 422, gpt_allowed_values))

        data = {
            "prompt": payload.prompt.strip(),
            "n": payload.n,
            "size": gpt_size_for_aspect_ratio(gpt_aspect_ratio or GPT_DEFAULT_ASPECT_RATIO),
            "aspect_ratio": gpt_aspect_ratio or GPT_DEFAULT_ASPECT_RATIO,
            "model": GPT_MODEL,
        }
        job = create_job("generate")
        spawn_job(execute_gpt_generate_job, job, data, api_key)
        return JSONResponse(status_code=202, content=job.snapshot())

    if payload.n not in (0, 1):
        return JSONResponse(
            status_code=422,
            content=error_payload("Gemini 3.1 当前接口不支持一次返回多张图。", 422),
        )

    aspect_ratio_error = validate_gemini_aspect_ratio(payload.aspect_ratio)
    if aspect_ratio_error is not None:
        return JSONResponse(
            status_code=422,
            content=error_payload(aspect_ratio_error, 422, sorted(GEMINI_ALLOWED_ASPECT_RATIOS)),
        )

    image_size_error = validate_gemini_image_size(payload.image_size)
    if image_size_error is not None:
        return JSONResponse(
            status_code=422,
            content=error_payload(image_size_error, 422, sorted(GEMINI_ALLOWED_IMAGE_SIZES)),
        )

    gemini_payload = build_gemini_payload(
        prompt=payload.prompt,
        aspect_ratio=payload.aspect_ratio,
        image_size=payload.image_size,
    )
    job = create_job("generate")
    spawn_job(
        execute_gemini_job,
        job,
        GEMINI_MODEL,
        gemini_payload,
        api_key,
        "已发送到上游，等待 Gemini 3.1 文生图结果。",
        "generate",
    )
    return JSONResponse(status_code=202, content=job.snapshot())


@app.post("/api/image-edit")
def image_edit(
    model: str = Form(GPT_MODEL),
    image: Optional[UploadFile] = File(None),
    prompt: str = Form(...),
    mask: Optional[UploadFile] = File(None),
    n: int = Form(1),
    size: str = Form("auto"),
    aspect_ratio: str = Form(""),
    image_size: str = Form("512"),
) -> JSONResponse:
    api_key = get_api_key()
    if not api_key:
        return JSONResponse(status_code=503, content=error_payload("未配置 API Key。", 503))

    model_error = validate_model(model)
    if model_error is not None:
        return JSONResponse(status_code=422, content=error_payload(model_error, 422, sorted(SUPPORTED_MODELS)))

    prompt_error = validate_prompt(prompt, PROMPT_MAX_LENGTH)
    if prompt_error is not None:
        return JSONResponse(status_code=422, content=error_payload(prompt_error, 422))

    image_file: tuple[str, bytes, str] | None = None
    mask_file: tuple[str, bytes, str] | None = None
    if image is not None and image.filename:
        image_file = read_upload_bytes(image)
    if mask is not None and mask.filename:
        mask_file = read_upload_bytes(mask)

    if image is not None:
        image.file.close()
    if mask is not None:
        mask.file.close()

    if model == GPT_MODEL:
        if image_file is None:
            return JSONResponse(status_code=422, content=error_payload("图生图模式必须上传参考图。", 422))

        n_error = validate_n(n)
        if n_error is not None:
            return JSONResponse(status_code=422, content=error_payload(n_error, 422))

        gpt_aspect_ratio, gpt_geometry_error, gpt_allowed_values = resolve_gpt_aspect_ratio(size, aspect_ratio)
        if gpt_geometry_error is not None:
            return JSONResponse(status_code=422, content=error_payload(gpt_geometry_error, 422, gpt_allowed_values))

        files = {"image": image_file}
        if mask_file is not None:
            files["mask"] = mask_file

        data = {
            "prompt": prompt.strip(),
            "n": str(n),
            "size": gpt_size_for_aspect_ratio(gpt_aspect_ratio or GPT_DEFAULT_ASPECT_RATIO),
            "aspect_ratio": gpt_aspect_ratio or GPT_DEFAULT_ASPECT_RATIO,
            "model": GPT_MODEL,
        }
        job = create_job("edit")
        spawn_job(execute_gpt_edit_job, job, data, files, api_key)
        return JSONResponse(status_code=202, content=job.snapshot())

    if n not in (0, 1):
        return JSONResponse(
            status_code=422,
            content=error_payload("Gemini 3.1 当前接口不支持一次返回多张图。", 422),
        )

    if image_file is None:
        return JSONResponse(status_code=422, content=error_payload("图生图模式必须上传参考图。", 422))

    aspect_ratio_error = validate_gemini_aspect_ratio(aspect_ratio)
    if aspect_ratio_error is not None:
        return JSONResponse(
            status_code=422,
            content=error_payload(aspect_ratio_error, 422, sorted(GEMINI_ALLOWED_ASPECT_RATIOS)),
        )

    image_size_error = validate_gemini_image_size(image_size)
    if image_size_error is not None:
        return JSONResponse(
            status_code=422,
            content=error_payload(image_size_error, 422, sorted(GEMINI_ALLOWED_IMAGE_SIZES)),
        )

    gemini_payload = build_gemini_payload(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        inline_parts=[build_gemini_inline_part(image_file)],
    )
    job = create_job("edit")
    spawn_job(
        execute_gemini_job,
        job,
        GEMINI_MODEL,
        gemini_payload,
        api_key,
        "已发送到上游，等待 Gemini 3.1 图生图结果。",
        "edit",
    )
    return JSONResponse(status_code=202, content=job.snapshot())
