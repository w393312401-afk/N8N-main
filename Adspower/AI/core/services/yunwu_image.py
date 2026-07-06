# -*- coding: utf-8 -*-
"""
🖼️ 云雾 (Yunwu) - 图片生成服务
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
通过 Yunwu API (OpenAI 兼容接口) 进行文生图 / 图生图。
API 文档: https://yunwu.ai
"""

import os
import time
import base64
import requests

from config import OUTPUT_DIR
from models import YunwuTextToImageRequest, YunwuImageToImageRequest
from utils.logger import log

# ==============================================================================
# ⚙️ 云雾 API 配置
# ==============================================================================

YUNWU_BASE_URL = os.environ.get("YUNWU_BASE_URL", "https://yunwu.ai/v1").rstrip("/")
YUNWU_DEFAULT_API_KEY = os.environ.get("YUNWU_API_KEY", "")
YUNWU_DEFAULT_MODEL = os.environ.get("YUNWU_IMAGE_MODEL", "gpt-image-1")

# 图片尺寸映射 (aspect_ratio -> size 参数)
SIZE_MAP = {
    "1:1":  "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "4:3":  "1024x768",
    "3:4":  "768x1024",
}

# image_size 精度映射
QUALITY_MAP = {
    "1K": "standard",
    "2K": "hd",
    "4K": "hd",
}


def _get_headers(req) -> dict:
    """构建请求头，优先使用 bearer_token，其次 api_key，最后环境变量。"""
    token = req.bearer_token or req.api_key or YUNWU_DEFAULT_API_KEY
    if not token:
        raise ValueError("未提供 API 密钥: 请设置 api_key / bearer_token 参数或 YUNWU_API_KEY 环境变量")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _ensure_output_dir(output_path: str, subfolder: str = "yunwu") -> str:
    """确保输出目录存在，返回最终目录路径。"""
    target = output_path if output_path else os.path.join(OUTPUT_DIR, subfolder)
    os.makedirs(target, exist_ok=True)
    return target


def _save_image(image_data: str, output_dir: str, prefix: str, idx: int = 0) -> str:
    """将 base64 或 URL 的图片保存到本地。返回本地路径。"""
    filename = f"{prefix}_{int(time.time())}_{idx}.png"
    local_path = os.path.join(output_dir, filename)

    if image_data.startswith("http"):
        # URL 模式 -> 下载
        try:
            r = requests.get(image_data, stream=True, timeout=30)
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return local_path
        except Exception as e:
            log(f"⚠️ 图片 URL 下载失败: {e}", "Yunwu")
            return image_data  # 回退返回原始 URL
    else:
        # base64 模式 -> 解码
        try:
            img_bytes = base64.b64decode(image_data)
            with open(local_path, "wb") as f:
                f.write(img_bytes)
            return local_path
        except Exception as e:
            log(f"⚠️ 图片 base64 解码失败: {e}", "Yunwu")
            raise


# ==============================================================================
# 📤 文生图 (Text-to-Image)
# ==============================================================================

def generate_yunwu_text_to_image(req: YunwuTextToImageRequest) -> dict:
    """
    调用 Yunwu API 进行文生图。
    POST {base_url}/images/generations
    """
    result = {"status": "failed", "image_urls": [], "message": ""}

    log(f"🚀 云雾文生图请求: prompt={req.prompt[:50]}..., ratio={req.aspect_ratio}", "Yunwu")

    try:
        headers = _get_headers(req)
        size = SIZE_MAP.get(req.aspect_ratio, "1024x1024")
        quality = QUALITY_MAP.get(req.image_size, "standard")

        payload = {
            "model": YUNWU_DEFAULT_MODEL,
            "prompt": req.prompt,
            "n": 1,
            "size": size,
            "quality": quality,
            "response_format": "b64_json",
        }

        log(f"  📡 POST {YUNWU_BASE_URL}/images/generations (model={YUNWU_DEFAULT_MODEL}, size={size})", "Yunwu")

        resp = requests.post(
            f"{YUNWU_BASE_URL}/images/generations",
            headers=headers,
            json=payload,
            timeout=120,
        )

        if resp.status_code != 200:
            error_detail = resp.text[:500]
            raise Exception(f"API 返回 {resp.status_code}: {error_detail}")

        data = resp.json()
        images = data.get("data", [])

        if not images:
            raise Exception("API 返回空图片列表")

        # 保存图片
        output_dir = _ensure_output_dir(req.output_path)
        local_paths = []

        for idx, img_item in enumerate(images):
            img_data = img_item.get("b64_json") or img_item.get("url", "")
            if not img_data:
                log(f"⚠️ 第 {idx+1} 张图片数据为空", "Yunwu")
                continue

            path = _save_image(img_data, output_dir, req.filename_prefix, idx)
            local_paths.append(path)
            log(f"  ✅ 图片 {idx+1} 已保存: {path}", "Yunwu")

        result["status"] = "success"
        result["image_urls"] = local_paths
        result["message"] = f"成功生成 {len(local_paths)} 张图片"
        log(f"✅ 文生图完成: {len(local_paths)} 张", "Yunwu")

    except Exception as e:
        log(f"❌ 云雾文生图失败: {e}", "Yunwu")
        result["message"] = str(e)

    return result


# ==============================================================================
# 📤 图生图 (Image-to-Image)
# ==============================================================================

def generate_yunwu_image_to_image(req: YunwuImageToImageRequest) -> dict:
    """
    调用 Yunwu API 进行图生图 (编辑)。
    POST {base_url}/images/edits
    """
    result = {"status": "failed", "image_urls": [], "message": ""}

    log(f"🚀 云雾图生图请求: prompt={req.prompt[:50]}..., ratio={req.aspect_ratio}", "Yunwu")

    try:
        headers = _get_headers(req)
        # 图生图接口使用 multipart/form-data，需要去掉 Content-Type
        headers.pop("Content-Type", None)

        size = SIZE_MAP.get(req.aspect_ratio, "1024x1024")

        # 准备图片数据
        if req.image_base64:
            image_bytes = base64.b64decode(req.image_base64)
        elif req.image_path:
            if req.image_path.startswith("http"):
                log("  📥 从 URL 下载参考图...", "Yunwu")
                r = requests.get(req.image_path, timeout=30)
                r.raise_for_status()
                image_bytes = r.content
            else:
                with open(req.image_path, "rb") as f:
                    image_bytes = f.read()
        else:
            raise ValueError("未提供参考图: 需要 image_path 或 image_base64")

        # 确定文件扩展名
        ext = "png"
        if "jpeg" in req.mime_type or "jpg" in req.mime_type:
            ext = "jpg"
        elif "webp" in req.mime_type:
            ext = "webp"

        files = {
            "image": (f"input.{ext}", image_bytes, req.mime_type),
        }

        form_data = {
            "model": YUNWU_DEFAULT_MODEL,
            "prompt": req.prompt,
            "n": "1",
            "size": size,
            "response_format": "b64_json",
        }

        log(f"  📡 POST {YUNWU_BASE_URL}/images/edits (model={YUNWU_DEFAULT_MODEL}, size={size})", "Yunwu")

        resp = requests.post(
            f"{YUNWU_BASE_URL}/images/edits",
            headers=headers,
            data=form_data,
            files=files,
            timeout=120,
        )

        if resp.status_code != 200:
            error_detail = resp.text[:500]
            raise Exception(f"API 返回 {resp.status_code}: {error_detail}")

        data = resp.json()
        images = data.get("data", [])

        if not images:
            raise Exception("API 返回空图片列表")

        # 保存图片
        output_dir = _ensure_output_dir(req.output_path)
        local_paths = []

        for idx, img_item in enumerate(images):
            img_data = img_item.get("b64_json") or img_item.get("url", "")
            if not img_data:
                log(f"⚠️ 第 {idx+1} 张图片数据为空", "Yunwu")
                continue

            path = _save_image(img_data, output_dir, req.filename_prefix, idx)
            local_paths.append(path)
            log(f"  ✅ 图片 {idx+1} 已保存: {path}", "Yunwu")

        result["status"] = "success"
        result["image_urls"] = local_paths
        result["message"] = f"成功生成 {len(local_paths)} 张图片"
        log(f"✅ 图生图完成: {len(local_paths)} 张", "Yunwu")

    except Exception as e:
        log(f"❌ 云雾图生图失败: {e}", "Yunwu")
        result["message"] = str(e)

    return result
