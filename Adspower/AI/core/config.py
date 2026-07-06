# -*- coding: utf-8 -*-
"""
⚙️ 全局配置区域
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
集中管理所有超时时间、路径和默认参数。
所有可变配置统一读取自项目根目录的 .env 文件。
"""

import os
import sys
import threading
import warnings
import urllib3
from pathlib import Path

# 禁用 requests 的 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

warnings.simplefilter("ignore")

# 🖥️ 跨平台编码兼容性处理
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# ==============================================================================
# 📄 加载 .env (唯一配置源)
# ==============================================================================

import platform

# 🖥️ 平台检测
PLATFORM = platform.system()  # "Darwin" (Mac) / "Windows" / "Linux"
IS_WINDOWS = PLATFORM == "Windows"
IS_MAC = PLATFORM == "Darwin"

CORE_DIR = Path(__file__).resolve().parent
AI_DIR = CORE_DIR.parent
DEFAULT_PROJECT_ROOT = AI_DIR.parent.parent
ENV_FILE = AI_DIR / ".env"

# 尝试加载 python-dotenv；包不存在时也能正常 fallback
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=False)  # 不覆盖已有环境变量
except ImportError:
    # python-dotenv 未安装时手动解析 .env 文件
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    # 不覆盖已有环境变量
                    if k and k not in os.environ:
                        os.environ[k] = v

# ==============================================================================
# ⚙️ 全局配置常量 (全部从环境变量读取，带 fallback)
# ==============================================================================


def _env_or_default(env_name: str, fallback: str) -> str:
    value = os.environ.get(env_name, "").strip()
    return value if value else fallback


def _read_env_file_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values

    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue

            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[key] = value

    return values


def runtime_env_or_default(env_name: str, fallback: str) -> str:
    if env_name in os.environ and os.environ[env_name].strip():
        return os.environ[env_name].strip()
    file_values = _read_env_file_values()
    if env_name in file_values and file_values[env_name].strip():
        return file_values[env_name].strip()
    return _env_or_default(env_name, fallback)


# 💡 服务端口
SERVER_HOST = _env_or_default("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(_env_or_default("SERVER_PORT", "8000"))

# 💡 AdsPower 配置
DEFAULT_PORT = _env_or_default("ADSPOWER_PORT", "50325")
DEFAULT_USER_ID = _env_or_default("ADSPOWER_DEFAULT_USER_ID", "k1a01try")

# 💡 路径
# 默认输出根目录 → 项目目录下的 AI_video（与现有文件结构一致）
_ai_video_dir = str(DEFAULT_PROJECT_ROOT / "AI_video")

if IS_WINDOWS:
    _desktop = Path.home() / "Desktop"
    _default_output_dir = str(_desktop / "AI生成")
else:
    _default_output_dir = _ai_video_dir  # Mac: N8N-main/AI_video

PROJECT_ROOT = _env_or_default("ADSPWR_PROJECT_ROOT", str(DEFAULT_PROJECT_ROOT))
OUTPUT_DIR = _env_or_default("ADSPWR_OUTPUT_DIR", _default_output_dir)

# 💡 生成任务的最大等待时间（秒）
MAX_WAIT_SECONDS = int(_env_or_default("GOOGLE_FX_MAX_WAIT_SECONDS", "120"))

# 💡 页面加载超时（毫秒）
PAGE_LOAD_TIMEOUT = 60000

# 💡 默认 AI 模型配置
DEFAULT_GOOGLE_FX_VIDEO_MODEL = _env_or_default("GOOGLE_FX_VIDEO_MODEL", "Veo 3.1 - Fast")
DEFAULT_GOOGLE_FX_IMAGE_MODEL = _env_or_default("GOOGLE_FX_IMAGE_MODEL", "Nano Banana 2")
NOTION_TOKEN = _env_or_default("NOTION_TOKEN", "")




def get_runtime_default_port() -> str:
    return runtime_env_or_default("ADSPOWER_PORT", DEFAULT_PORT)


def get_runtime_default_user_id() -> str:
    return runtime_env_or_default("ADSPOWER_DEFAULT_USER_ID", DEFAULT_USER_ID)


def get_runtime_google_fx_video_model() -> str:
    return runtime_env_or_default("GOOGLE_FX_VIDEO_MODEL", DEFAULT_GOOGLE_FX_VIDEO_MODEL)


def get_runtime_google_fx_image_model() -> str:
    return runtime_env_or_default("GOOGLE_FX_IMAGE_MODEL", DEFAULT_GOOGLE_FX_IMAGE_MODEL)


# ==============================================================================
# 🌐 Miya IP 动态住宅代理配置
# ==============================================================================

MIYA_PROXY_HOST = _env_or_default("MIYA_PROXY_HOST", "")
MIYA_PROXY_PORT = _env_or_default("MIYA_PROXY_PORT", "")
MIYA_PROXY_USER = _env_or_default("MIYA_PROXY_USER", "")
MIYA_PROXY_PASSWORD = _env_or_default("MIYA_PROXY_PASSWORD", "")
MIYA_PROXY_TYPE = _env_or_default("MIYA_PROXY_TYPE", "http")
MIYA_PROXY_ROTATE_MODE = _env_or_default("MIYA_PROXY_ROTATE_MODE", "session")
MIYA_PROXY_COUNTRY = _env_or_default("MIYA_PROXY_COUNTRY", "us")
MIYA_PROXY_API_URL = _env_or_default("MIYA_PROXY_API_URL", "")
MIYA_SESSION_PREFIX = _env_or_default("MIYA_SESSION_PREFIX", "session")
MIYA_AUTO_ROTATE = _env_or_default("MIYA_AUTO_ROTATE", "1") == "1"

