# -*- coding: utf-8 -*-
"""
🛠️ 浏览器通用工具函数
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AdsPower 连接、Playwright 页面管理、下载、粘贴等通用功能。
"""

import os
import time
import random
import base64
import requests
import socket
from urllib.parse import urlparse
from pathlib import Path

from config import (
    PAGE_LOAD_TIMEOUT,
    DEFAULT_USER_ID,
    DEFAULT_PORT,
    OUTPUT_DIR,
    get_runtime_default_user_id,
    get_runtime_default_port,
)
from utils.logger import log


def random_sleep(min_s=1.0, max_s=3.0):
    time.sleep(random.uniform(min_s, max_s))


def clean_path(path_str):
    """🛠️ 路径兼容性处理，必要时按 basename 在输出目录内自动纠偏。"""
    if not path_str:
        return ""
    path_str = path_str.strip().strip('"').strip("'")
    normalized = os.path.normpath(os.path.expanduser(path_str))

    if os.path.exists(normalized):
        return normalized

    basename = os.path.basename(normalized)
    if not basename:
        return normalized

    try:
        search_root = Path(OUTPUT_DIR)
        if search_root.exists():
            matches = [str(p) for p in search_root.rglob(basename) if p.is_file()]
            if len(matches) == 1:
                log(f"⚠️ 路径不存在，已按文件名自动纠偏: '{normalized}' -> '{matches[0]}'", "路径修复")
                return matches[0]
            if len(matches) > 1:
                preferred = [m for m in matches if normalized.endswith(os.sep + os.path.basename(os.path.dirname(m)) + os.sep + basename)]
                picked = preferred[0] if preferred else matches[0]
                log(f"⚠️ 路径不存在，发现 {len(matches)} 个同名文件，已选用: '{picked}'", "路径修复")
                return picked
    except Exception as e:
        log(f"⚠️ 路径自动纠偏失败: {e}", "路径修复")

    return normalized


def fast_paste(page, selector, text):
    """ ⚡ 极速粘贴函数 (模拟物理粘贴效果) """
    try:
        page.wait_for_selector(selector, state="visible", timeout=10000)
        
        # 核心逻辑：直接通过 JS 注入内容并触发必要的 input/change/paste 事件
        page.evaluate("""({selector, text}) => {
            const el = document.querySelector(selector);
            if (el) {
                el.focus();
                
                // 1. 设置内容
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                    el.value = text;
                } else {
                    el.innerText = text;
                }
                
                // 2. 模拟物理粘贴事件 (解决某些站点的监听问题)
                const dataTransfer = new DataTransfer();
                dataTransfer.setData('text/plain', text);
                const pasteEvent = new ClipboardEvent('paste', {
                    clipboardData: dataTransfer,
                    bubbles: true,
                    cancelable: true
                });
                el.dispatchEvent(pasteEvent);

                // 3. 触发常规输入事件
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                
                // 4. 针对内容可编辑区域的特殊处理
                if (el.getAttribute('contenteditable') === 'true') {
                    const range = document.createRange();
                    const sel = window.getSelection();
                    range.selectNodeContents(el);
                    range.collapse(false);
                    sel.removeAllRanges();
                    sel.addRange(range);
                }
            }
        }""", {"selector": selector, "text": text})
        
        # 即使 JS 成功，也补一个 Playwright 的 fill 确保状态机完全同步
        try: page.fill(selector, text, timeout=2000)
        except: pass
        
        # ⚡ 状态唤醒：针对某些前端框架 (React/Angular) 无法捕捉瞬间变更的问题
        # 增加一个物理按键动作（空格 + 退格），强制唤醒 UI 的数据绑定
        random_sleep(0.5, 1.0)
        try:
            target = page.locator(selector).first
            target.focus()
            target.press("Space")
            random_sleep(0.1, 0.3)
            target.press("Backspace")
            random_sleep(1, 2)
        except:
            pass
        
        log(f"⚡ 物理粘贴及UI唤醒成功: {len(text)} 个字符", "输入优化")
        
    except Exception as e:
        log(f"❌ Input Error: {e}", "Error")
        try: page.fill(selector, text)
        except: pass


def _is_ws_port_open(ws_url: str) -> bool:
    """🛠️ 检测 WebSocket URL 对应的端口是否已启用并且可以建立 TCP 连接。"""
    try:
        parsed = urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port
        if not port:
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect((host, port))
            return True
    except Exception:
        return False


def get_ads_ws_url(user_id=None, port=None, auto_rotate_proxy=True):
    """🔌 连接 AdsPower 并返回 WebSocket URL (替代 4 处重复代码)

    新增 auto_rotate_proxy: True 时，在启动浏览器前自动更换 Miya IP 代理。
    设为 False 可跳过轮换（如已刚轮换过，避免重复操作）。
    """
    if user_id is None:
        user_id = get_runtime_default_user_id() or DEFAULT_USER_ID
    if port is None:
        port = get_runtime_default_port() or DEFAULT_PORT

    # ── 代理轮换钩子 ──
    if auto_rotate_proxy:
        try:
            from utils.proxy_rotator import ProxyRotator
            rotator = ProxyRotator()
            if rotator.is_configured and rotator.auto_rotate:
                rotator.rotate_proxy(user_id=user_id, port=port)
        except Exception as e:
            log(f"⚠️ 代理轮换异常（不阻塞主流程）: {type(e).__name__}: {e}", "代理轮换")

    launch_args = '%5B%22--disable-features%3DHardwareMediaKeyHandling%22%2C%22--mute-audio%22%5D'
    api_start_url = f"http://127.0.0.1:{port}/api/v1/browser/start?user_id={user_id}&launch_args={launch_args}"
    api_stop_url = f"http://127.0.0.1:{port}/api/v1/browser/stop?user_id={user_id}"

    max_start_attempts = 3
    for attempt in range(1, max_start_attempts + 1):
        try:
            resp = requests.get(api_start_url, timeout=45).json()
            if resp["code"] != 0:
                raise Exception(resp.get("msg", "未知错误"))
            
            ws_url = resp["data"]["ws"]["puppeteer"]
            
            # 校验端口是否可用
            if _is_ws_port_open(ws_url):
                if attempt > 1:
                    log(f"✅ 第 {attempt} 次尝试成功启动浏览器，端口已启用: {ws_url}", "浏览器启动")
                return ws_url
            
            log(f"⚠️ AdsPower 返回的 WebSocket 端口未启用 (尝试 {attempt}/{max_start_attempts}): {ws_url}，尝试强制关闭并重启...", "浏览器启动")
        except Exception as start_err:
            log(f"⚠️ 启动浏览器失败 (尝试 {attempt}/{max_start_attempts}): {start_err}", "浏览器启动")
            if attempt == max_start_attempts:
                raise Exception(
                    f"AdsPower 启动失败 (已尝试 {max_start_attempts} 次): {start_err} (user_id={user_id}, port={port})"
                )
        
        # 强制关闭并等待
        try:
            requests.get(api_stop_url, timeout=10)
        except Exception:
            pass
        time.sleep(2)
        
    raise Exception(
        f"AdsPower 启动失败: 无法获取有效的 WebSocket 调试端口 (user_id={user_id}, port={port})"
    )


def find_or_create_page(context, url_pattern, fallback_url=None):
    """🔍 查找匹配的标签页，找不到则新建 (替代 3 处重复代码)"""
    for pg in reversed(context.pages):
        if url_pattern in pg.url:
            return pg
    page = context.new_page()
    if fallback_url:
        page.goto(fallback_url, timeout=PAGE_LOAD_TIMEOUT)
        random_sleep(1, 2)
    return page


def download_video_via_browser(page, video_url, output_dir, prefix="video"):
    """🎬 通过浏览器 fetch + base64 下载视频 (替代 2 处重复代码)"""
    log(f"🎬 同步下载视频到本地...", prefix)
    b64_data = page.evaluate("""async (url) => {
        const response = await fetch(url);
        const blob = await response.blob();
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result.split(',')[1]);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }""", video_url)
    video_bytes = base64.b64decode(b64_data)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    filename = f"{prefix}_{int(time.time())}.mp4"
    local_path = os.path.join(output_dir, filename)
    with open(local_path, "wb") as f:
        f.write(video_bytes)
    log(f"✅ 视频已保存至: {local_path}", "下载")
    return local_path


def stop_ads_browser(user_id=None, port=None):
    """🛑 关闭 AdsPower 浏览器并释放 profile 锁"""
    if user_id is None:
        user_id = get_runtime_default_user_id() or DEFAULT_USER_ID
    if port is None:
        port = get_runtime_default_port() or DEFAULT_PORT
    url = f"http://127.0.0.1:{port}/api/v1/browser/stop?user_id={user_id}"
    log(f"🛑 正在关闭 AdsPower 浏览器: user_id={user_id}, port={port}", "浏览器关闭")
    try:
        resp = requests.get(url, timeout=10)
        log(f"🛑 浏览器关闭 API 返回: {resp.text}", "浏览器关闭")
        return True
    except Exception as e:
        log(f"🛑 关闭浏览器失败: {str(e)}", "浏览器关闭")
        return False

