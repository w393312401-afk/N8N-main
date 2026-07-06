from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import webbrowser
from getpass import getpass
from pathlib import Path

import requests

try:
    from tkinter import Tk, messagebox, simpledialog

    HAS_TK = True
except Exception:
    Tk = None
    messagebox = None
    simpledialog = None
    HAS_TK = False

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / ".launcher_config.json"
HOST = "127.0.0.1"
PORT = 8000
APP_URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{APP_URL}/api/health"
STARTUP_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 0.5
MIN_PYTHON = (3, 10)
LOOPBACK_BYPASS_HOSTS = ("127.0.0.1", "localhost", "::1")


def create_hidden_root() -> Tk | None:
    if not HAS_TK or Tk is None:
        return None
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def show_message(kind: str, title: str, message: str) -> None:
    if not HAS_TK or messagebox is None:
        print(f"[{title}] {message}")
        return

    root = create_hidden_root()
    try:
        if kind == "error":
            messagebox.showerror(title, message, parent=root)
        elif kind == "warning":
            messagebox.showwarning(title, message, parent=root)
        else:
            messagebox.showinfo(title, message, parent=root)
    finally:
        root.destroy()


def format_python_version(version_info: tuple[int, int, int] | None = None) -> str:
    info = version_info or sys.version_info[:3]
    return ".".join(str(part) for part in info)


def ensure_supported_python() -> str | None:
    current = sys.version_info[:3]
    if current >= MIN_PYTHON:
        return None
    return (
        f"当前 Python 版本是 {format_python_version(current)}，不满足运行要求。\n"
        f"请改用 Python {format_python_version((*MIN_PYTHON, 0))}+ 启动。"
    )


def load_saved_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}

    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def write_saved_config(payload: dict) -> None:
    if payload:
        CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    try:
        CONFIG_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def load_saved_api_key() -> str:
    return str(load_saved_config().get("api_key", "")).strip()


def save_api_key(api_key: str) -> None:
    payload = load_saved_config()
    payload["api_key"] = api_key.strip()
    write_saved_config(payload)


def prompt_for_api_key() -> str | None:
    if not HAS_TK or simpledialog is None or messagebox is None:
        while True:
            try:
                api_key = getpass("首次启动需要 Yunwu API Key，请输入当前要使用的密钥: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return None

            if api_key:
                try:
                    remember = input("是否保存到本地配置供下次直接启动？[Y/n]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    remember = "n"
                if remember in ("", "y", "yes"):
                    save_api_key(api_key)
                return api_key

            print("API Key 不能为空。")

    root = create_hidden_root()
    try:
        while True:
            api_key = simpledialog.askstring(
                "Yunwu API Key",
                "首次启动需要 Yunwu API Key。\n请输入当前要使用的密钥：",
                parent=root,
                show="*",
            )

            if api_key is None:
                return None

            api_key = api_key.strip()
            if api_key:
                remember = messagebox.askyesno(
                    "记住 API Key",
                    "是否将这把 API Key 保存到本地，供下次双击直接启动？",
                    parent=root,
                )
                if remember:
                    save_api_key(api_key)
                return api_key

            messagebox.showwarning("API Key 为空", "API Key 不能为空。", parent=root)
    finally:
        root.destroy()


def ensure_loopback_bypass_env() -> None:
    for env_name in ("NO_PROXY", "no_proxy"):
        current = os.getenv(env_name, "")
        items = [item.strip() for item in current.split(",") if item.strip()]
        changed = False
        for host in LOOPBACK_BYPASS_HOSTS:
            if host not in items:
                items.append(host)
                changed = True
        if changed:
            os.environ[env_name] = ",".join(items)


def direct_request(method: str, url: str, **kwargs):
    with requests.Session() as session:
        session.trust_env = False
        return session.request(method, url, **kwargs)


def check_running_service() -> dict | None:
    try:
        response = direct_request("GET", HEALTH_URL, timeout=1.2)
        if response.ok:
            return response.json()
    except ValueError:
        return None
    except requests.RequestException:
        return None
    return None


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def open_browser_when_ready() -> None:
    deadline = time.time() + STARTUP_TIMEOUT_SECONDS

    while time.time() < deadline:
        try:
            response = direct_request("GET", HEALTH_URL, timeout=1.2)
            if response.ok:
                webbrowser.open(APP_URL)
                return
        except requests.RequestException:
            pass
        time.sleep(POLL_INTERVAL_SECONDS)

    print("服务启动超时：浏览器未自动打开。你可以稍后手动访问", APP_URL)


def resolve_api_key() -> str | None:
    env_key = os.getenv("YUNWU_API_KEY", "").strip()
    if env_key:
        return env_key

    env_key = os.getenv("IMAGE_API_KEY", "").strip()
    if env_key:
        return env_key

    saved_key = load_saved_api_key()
    if saved_key:
        return saved_key

    return prompt_for_api_key()


def main() -> int:
    version_error = ensure_supported_python()
    if version_error:
        print(version_error)
        return 1

    ensure_loopback_bypass_env()

    try:
        import app as demo_app
    except Exception as exc:
        show_message(
            "error",
            "应用加载失败",
            "启动器已运行，但应用模块加载失败。\n"
            f"{type(exc).__name__}: {exc}",
        )
        return 1

    import uvicorn

    running = check_running_service()
    if running:
        webbrowser.open(APP_URL)
        if not running.get("apiKeyConfigured"):
            show_message(
                "warning",
                "服务已运行但未配置密钥",
                "检测到本地服务已经在运行，但当前实例没有配置 API Key。\n"
                "如果你要使用这次启动器里的密钥，先关闭现有服务，再重新双击启动。",
            )
        return 0

    if is_port_in_use(HOST, PORT):
        show_message(
            "error",
            "端口被占用",
            f"{HOST}:{PORT} 已被其他程序占用，当前不能启动图像工具。",
        )
        return 1

    api_key = resolve_api_key()
    if not api_key:
        show_message("warning", "已取消启动", "没有提供 API Key，本次不会启动服务。")
        return 1

    os.environ["IMAGE_API_KEY"] = api_key
    os.environ["YUNWU_API_KEY"] = api_key
    threading.Thread(target=open_browser_when_ready, daemon=True).start()

    print("正在启动 Yunwu 图像工具...")
    print("服务地址：", APP_URL)
    print("关闭当前窗口即可停止服务。")

    uvicorn.run(demo_app.app, host=HOST, port=PORT, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
