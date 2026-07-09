# -*- coding: utf-8 -*-
"""
🎨 Google FX 服务 (Veo 视频生成 + Imagen/Nano Banana 图片批量生成)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
包含 FX 底部工具栏配置、视频生成、图片批量生成的全部逻辑。

🔒 LOCKED 2026-03-25 — 此文件已由用户锁定，禁止在未获明确指示前修改。
   锁定范围: find_fx_config_button / check_fx_config / fix_fx_config
"""

import os
import re
import time
import random
import base64
import threading
import copy
import hashlib
import json
from collections import deque
import requests
from playwright.sync_api import sync_playwright

from config import MAX_WAIT_SECONDS, OUTPUT_DIR
from models import VideoRequest, ImageBatchRequest
from utils.logger import log
from utils.browser import (
    random_sleep,
    clean_path,
    get_ads_ws_url,
    find_or_create_page,
    download_video_via_browser,
)
from utils.ui_helpers import inject_batch_image_observer  # 视频生成仍在使用
from ui_selectors import UI_SELECTORS, ORIENT_ICON_MAP, RATIO_MAP
from utils import cancel_flag

# Import Playwright/JS canvas UI helpers
from services.google_fx_helpers import (
    _extract_flow_image_uuid,
    _resolve_flow_tile_info,
    _hover_flow_tile_for_toolbar,
    _click_flow_more_menu,
    _click_flow_add_to_prompt,
    _wait_for_prompt_reference_change,
    _wait_for_fx_toolbar,
    _click_new_project_button,
    _resolve_open_flow_menu_id
)




def _check_cancelled():
    if cancel_flag.is_cancelled:
        log("🛑 任务已取消，终止执行", "GoogleFX")
        raise RuntimeError("任务已取消")


def _make_response_handler(captured_data, mode="video"):
    """创建网络响应拦截回调 (视频/图片模式)，捕获的 URL 追加到 captured_data。"""
    def handler(response):
        try:
            url = response.url
            ct = (response.headers.get("content-type", "") or "").lower()
            cl = int(response.headers.get("content-length", 0) or 0)
            lower_url = url.lower()
            if mode == "video":
                if ("video" in ct or ".mp4" in lower_url) and cl > 50000:
                    captured_data.append((time.time(), url))
                    log(f"📡 捕获视频资源: {url[:80]}", "GoogleFX")
                elif "mediaUrlRedirect" in url or "media.get" in url:
                    log(f"📡 捕获视频API响应: {url[:100]}", "GoogleFX")
            elif mode == "image":
                if "video" in ct or "/video/" in lower_url or ".mp4" in lower_url:
                    return
                # 路径1: 重定向跟随 (Playwright 自动 307)
                redir = response.request.redirected_from
                if redir:
                    orig = redir.url
                    if "getMediaUrlRedirect" in orig or "MediaUrlRedirect" in orig:
                        captured_data.append((time.time(), url))
                        log(f"📡 捕获图片重定向: {url[:100]}", "GoogleFX")
                        return
                # 路径2: 直接匹配 redirect 请求
                if "getMediaUrlRedirect" in url or "MediaUrlRedirect" in url:
                    captured_data.append((time.time(), url))
                    return
                # 路径3: GCS 图片资源
                if "storage.googleapis.com" in url and ("ai-sandbox" in url or "videofx" in url):
                    if "image/" in ct or cl > 10000 or re.search(r"\.(png|jpe?g|webp)(\?|$)", url, re.I):
                        captured_data.append((time.time(), url))
                        log(f"📡 捕获GCS图片: {url[:100]}", "GoogleFX")
                        return
                # 路径4: Google 域名图片
                if any(k in url for k in ["googleusercontent.com", "gstatic.com", "ggpht.com"]):
                    if ("image/" in ct and cl > 10000) or re.search(r"\.(png|jpe?g|webp)(\?|$)", url, re.I):
                        captured_data.append((time.time(), url))
                        return
                # 路径5: 兜底大图
                if "image/" in ct and cl > 50000 and "labs.google" not in url:
                    captured_data.append((time.time(), url))
                    log(f"📡 捕获大图片: {url[:80]} ({cl}B)", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ handle_response 异常: {type(e).__name__}", "GoogleFX")
    return handler


def _click_first_visible(root, selectors, timeout=2000, force=False, log_prefix=""):
    """遍历选择器列表，点击第一个可见元素。返回 (locator, sel_index) 或 (None, -1)。"""
    for idx, sel in enumerate(selectors):
        try:
            el = root.locator(sel).first
            if el.is_visible(timeout=timeout):
                el.click(force=force)
                return el, idx
        except Exception:
            pass
    return None, -1


def _find_first_visible(root, selectors, timeout=2000):
    """遍历选择器列表，返回第一个可见元素 Locator 或 None（不点击）。"""
    for sel in selectors:
        try:
            el = root.locator(sel).first
            if el.is_visible(timeout=timeout):
                return el
        except Exception:
            pass
    return None


def _normalize_ratio_value(ratio):
    """将用户传入的 ratio 规范化：去空格 + 小写 (以便 RATIO_MAP 查表)。"""
    value = (ratio or "").strip()
    if not value:
        return None
    return value.lower()


# ── 已知有效模型名 (2026-05-05) ──────────────────────────────────────────────
_VALID_IMAGE_MODELS = ["Nano Banana Pro", "Nano Banana 2", "Imagen 4"]
_VALID_VIDEO_MODELS = [
    "Veo 3.1 - Lite",
    "Veo 3.1 - Fast",
    "Veo 3.1 - Quality",
    "Omni Flash",
    "Veo 3.1 - Lite [Lower Priority]",
]

# ── 模型名简写 → 真实模型名 ────────────────────────────────────────────────
_MODEL_ALIAS = {
    # 通用名 (兼容 N8N 历史写法)
    "google fx":      "Nano Banana 2",
    "google_fx":      "Nano Banana 2",
    "fx":             "Nano Banana 2",
    "flow":           "Nano Banana 2",
    # 图片模型简写
    "nano banana":    "Nano Banana 2",
    "nano":           "Nano Banana 2",
    "banana":         "Nano Banana 2",
    "imagen":         "Nano Banana 2",
    "imagen 3":       "Nano Banana 2",
    "imagen3":        "Nano Banana 2",
    # 视频模型简写
    "veo":            "Veo 3.1 - Fast",
    "veo3":           "Veo 3.1 - Fast",
    "veo 3":          "Veo 3.1 - Fast",
    "veo 3.1":        "Veo 3.1 - Fast",
    "veo3.1":         "Veo 3.1 - Fast",
    "veo lite":       "Veo 3.1 - Lite",
    "veo fast":       "Veo 3.1 - Fast",
    "veo quality":    "Veo 3.1 - Quality",
    "veo lite lp":    "Veo 3.1 - Lite [Lower Priority]",
    "omni":           "Omni Flash",
    "omni flash":     "Omni Flash",
    "omniflash":      "Omni Flash",
}


# ── aria-controls 结尾值 → 比例 Tab (Radix UI 固定业务值, 2026-05-05) ────────────
# ⚠️ 绝对不能用 id="radix-:rXX:" (每次刷新都变)，aria-controls 尾值由开发者定义不变
_ARIA_CONTROLS_RATIO_MAP = {
    # 按宽高比文字
    "9:16":          "PORTRAIT",
    "16:9":          "LANDSCAPE",
    "1:1":           "SQUARE",
    "3:4":           "PORTRAIT_3_4",
    "4:3":           "LANDSCAPE_4_3",
    # 按方向关键词 (orientation string)
    "portrait":      "PORTRAIT",
    "landscape":     "LANDSCAPE",
    "square":        "SQUARE",
    "portrait_3_4":  "PORTRAIT_3_4",
    "landscape_4_3": "LANDSCAPE_4_3",
}

# ── 视频子模式 aria-controls 尾值 (2026-05-05 新增) ────────────────────────────
# 面板中 VIDEO 模式下的子 tab: 帧 (VIDEO_FRAMES) / 素材 (VIDEO_REFERENCES)
_ARIA_CONTROLS_VIDEO_SUBMODE_MAP = {
    "frames":          "VIDEO_FRAMES",
    "帧":              "VIDEO_FRAMES",
    "video_frames":    "VIDEO_FRAMES",
    "references":      "VIDEO_REFERENCES",
    "素材":            "VIDEO_REFERENCES",
    "video_references":"VIDEO_REFERENCES",
}

# ── 视频时长 aria-controls 尾值 (2026-05-05 新增) ────────────────────────────
# 面板中 VIDEO 模式下的时长选项: 4s / 6s / 8s
_VALID_VIDEO_DURATIONS = ["4", "6", "8"]


def _normalize_video_duration_label(duration):
    """Return Google FX duration labels like 6s from values such as 6, "6", or "6s"."""
    if duration is None:
        return ""
    text = str(duration).strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*s?", text)
    if not match:
        return ""
    number = match.group(1)
    if number.endswith(".0"):
        number = number[:-2]
    return f"{number}s"


def _click_video_duration_tab(page, panel_scope, duration_label):
    """Click a video duration tab such as 4s, 6s, or 8s."""
    try:
        _dur_btn = panel_scope.locator("button[role='tab']").filter(
            has_text=re.compile(f"^{re.escape(duration_label)}$", re.I)
        ).first
        if _dur_btn.is_visible(timeout=2000):
            _dur_btn.click(force=True)
            random_sleep(0.4, 0.8)
            return "role=tab + 精确匹配"
    except Exception:
        pass

    if _click_fx_tab(page, duration_label, scope=panel_scope):
        return "tab fallback"
    return ""


def _switch_video_submode(page, target_suffix, scope=None):
    """切换视频子模式 tab: VIDEO_FRAMES (帧/首尾帧) 或 VIDEO_REFERENCES (素材)。

    使用 aria-controls 尾值匹配 (Radix UI 固定业务值，最稳定)。
    target_suffix: 'VIDEO_FRAMES' | 'VIDEO_REFERENCES'
    返回 True 表示成功点击。
    """
    root = scope or page

    # ── 优先级 0: aria-controls 尾值精确匹配 (最稳定) ──
    for _sel in [
        f"[aria-controls$='-{target_suffix}']",
        f"[aria-controls*='-{target_suffix}']",
        f"button[role='tab'][aria-controls$='-{target_suffix}']",
    ]:
        try:
            _btn = root.locator(_sel).first
            if _btn.is_visible(timeout=2000):
                # 检查是否已经选中
                if _btn.get_attribute("data-state") == "active" or _btn.get_attribute("aria-selected") == "true":
                    log(f"  ✅ 视频子模式已是 {target_suffix}，无需切换", "GoogleFX")
                    return True
                _btn.click(force=True)
                random_sleep(0.5, 0.8)
                log(f"  ✅ 视频子模式切换成功 (sel={_sel!r})", "GoogleFX")
                return True
        except Exception as _e:
            log(f"  ⚠️ _switch_video_submode sel={_sel!r}: {type(_e).__name__}", "GoogleFX")

    # ── 优先级 1: 文字标签匹配 ──
    _label_map = {
        "VIDEO_FRAMES": ["帧", "Frames", "frames"],
        "VIDEO_REFERENCES": ["素材", "References", "references"],
    }
    for _lbl in _label_map.get(target_suffix, []):
        try:
            _tab = root.locator("button[role='tab']").filter(
                has_text=re.compile(f"^.*{re.escape(_lbl)}.*$", re.I)
            ).first
            if _tab.is_visible(timeout=1500):
                if _tab.get_attribute("data-state") == "active":
                    log(f"  ✅ 视频子模式已是 {_lbl}，无需切换", "GoogleFX")
                    return True
                _tab.click(force=True)
                random_sleep(0.5, 0.8)
                log(f"  ✅ 视频子模式切换成功 (label={_lbl!r})", "GoogleFX")
                return True
        except Exception:
            pass

    # ── 优先级 2: JS 兜底 ──
    try:
        clicked = page.evaluate("""(suffix) => {
            const tabs = Array.from(document.querySelectorAll("[role='tab'], button"));
            const target = tabs.find(t => {
                const ac = t.getAttribute('aria-controls') || '';
                return ac.endsWith('-' + suffix) || ac.includes('-' + suffix);
            });
            if (!target || target.offsetParent === null) return false;
            if (target.getAttribute('data-state') === 'active') return 'already';
            target.click();
            return true;
        }""", target_suffix)
        if clicked == "already":
            log(f"  ✅ 视频子模式已是 {target_suffix} (JS)", "GoogleFX")
            return True
        if clicked:
            random_sleep(0.5, 0.8)
            log(f"  ✅ 视频子模式切换成功 (JS fallback)", "GoogleFX")
            return True
    except Exception as _e:
        log(f"  ⚠️ _switch_video_submode JS fallback: {type(_e).__name__}", "GoogleFX")

    return False


def _normalize_model_name(model: str, is_video: bool = False) -> str:
    """
    将任意模型名规范化为已知有效值。
    - 已知有效名直接返回
    - 别名/旧名映射到真实名
    - 完全未知的名称使用对应模式的默认值
    """
    if not model:
        default = _VALID_VIDEO_MODELS[0] if is_video else _VALID_IMAGE_MODELS[0]
        log(f"  ⚠️ model 为空，使用默认值 '{default}'", "GoogleFX")
        return default

    model = model.strip()
    valid_pool = _VALID_VIDEO_MODELS if is_video else _VALID_IMAGE_MODELS

    # 已是有效名
    if model in valid_pool:
        return model

    # 别名查表 (不区分大小写)
    lower = model.lower()
    if lower in _MODEL_ALIAS:
        mapped = _MODEL_ALIAS[lower]
        if mapped in valid_pool:
            log(f"  ⚠️ 模型名 '{model}' → 映射为 '{mapped}'", "GoogleFX")
            return mapped
        else:
            log(f"  ⚠️ 模型名 '{model}' 别名映射 '{mapped}' 不属于当前模式，忽略并继续匹配", "GoogleFX")

    # 部分包含匹配 (如 'Veo 3.1 - Lite [Lower Priority]' 被缩写)
    for valid in valid_pool:
        if lower in valid.lower() or valid.lower() in lower:
            log(f"  ⚠️ 模型名 '{model}' → 部分匹配为 '{valid}'", "GoogleFX")
            return valid

    # 完全未知 → 使用默认值
    default = valid_pool[0]
    log(f"  ⚠️ 未知模型名 '{model}'，使用默认值 '{default}'", "GoogleFX")
    return default


def _raise_if_config_invalid(status_text, checks, context_label):
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise RuntimeError(
            f"{context_label}配置未选对，停止生成。当前状态: {status_text or '<空>'}；未通过项: {', '.join(failed)}"
        )


def _verify_and_fix_fx_config(page, model, ratio, want_video, context_label, mode_label="", duration=None, video_submode=None):
    """统一的配置校验→面板修复确认流程 (三个生成函数共用)。
    video_submode: 'VIDEO_FRAMES' | 'VIDEO_REFERENCES' | None (仅 want_video 时生效)
    """
    selected_ratio = _normalize_ratio_value(ratio)
    vid_ratio = RATIO_MAP.get(selected_ratio, selected_ratio) if selected_ratio else None
    cfg_btn, status_text = find_fx_config_button(page)
    if not cfg_btn:
        # 🔁 底部配置按钮找不到，最常见的原因是页面刚导航/浏览器刚重连（典型场景：换 IP 后
        # 重新连接浏览器，紧接着就要切到 Image 模式上传图片），底部工具栏还没渲染完成——
        # 之前这里第一次没找到就直接 raise，是"换 IP 后紧接着的批次必挂"的确诊根因之一
        # （2026-07-01 server.log 实测复现：换 IP 重连浏览器 8 秒后即报此错，整个批次直接
        # 中止）。改为短暂轮询等待，而不是一次没找到就致命报错。
        for _retry in range(10):
            time.sleep(1)
            cfg_btn, status_text = find_fx_config_button(page)
            if cfg_btn:
                log(f"  ✅ {context_label}: 第 {_retry + 1} 次重试后找到底部配置按钮", "GoogleFX")
                break
    if not cfg_btn:
        raise RuntimeError(f"{context_label}未找到底部配置按钮，无法确认配置，已停止生成")
    checks = check_fx_config(status_text, model=model, orientation=vid_ratio, count="1x", duration=duration, want_video=want_video)
    # video_submode 不在底部摘要中显示，始终标记为需要修复
    if want_video and video_submode:
        checks["video_submode"] = False
    if all(checks.values()):
        log("✅ 所有配置正确", "GoogleFX")
        return selected_ratio
    fix_info = fix_fx_config(page, cfg_btn, checks, model=model,
                             orientation=vid_ratio, count="1x", duration=duration, want_video=want_video,
                             mode_label=mode_label, video_submode=video_submode)
    initially_failed = [k for k, v in checks.items() if not v]
    fixed_keys = set((fix_info or {}).get("clicked_keys") or []) | set((fix_info or {}).get("resolved_keys") or [])
    unconfirmed = [key for key in initially_failed if key not in fixed_keys]
    if unconfirmed:
        raise RuntimeError(
            f"{context_label}配置未完成，停止生成。当前状态: {status_text or '<空>'}；"
            f"面板未确认项: {', '.join(unconfirmed)}"
        )
    log(f"  ✅ 配置项已通过 UI 点击/面板状态确认: {', '.join(initially_failed)}；已跳过底部摘要二次确认", "GoogleFX")
    return selected_ratio


def _trigger_emergency_proxy_rotation():
    """检测到生成报错时，强制执行紧急/强制代理 IP 轮换"""
    try:
        from utils.proxy_rotator import ProxyRotator
        from config import get_runtime_default_user_id, get_runtime_default_port
        rotator = ProxyRotator()
        if rotator.is_configured and rotator.auto_rotate:
            log("🚨 检测到生成报错/卡片异常，正在执行紧急/强制代理 IP 轮换...", "GoogleFX")
            user_id = get_runtime_default_user_id()
            port = get_runtime_default_port()
            rotator.rotate_proxy(user_id=user_id, port=port, force=True)
            log("✅ 紧急/强制代理 IP 轮换完成", "GoogleFX")
        else:
            log("ℹ️ 紧急代理轮换跳过 (Miya 代理未配置或自动轮换关闭)", "GoogleFX")
    except Exception as e:
        log(f"⚠️ 紧急代理 IP 轮换失败: {type(e).__name__}: {e}", "GoogleFX")


def _connect_over_cdp_with_retry(playwright_ctx, ws_url, max_attempts=10, delay_secs=2.0):
    """CDP 连接包装器：如果遇到 Web Socket 连接被拒绝 (ECONNREFUSED) 则重试，最多重试 10 次。"""
    last_err = None
    time.sleep(1.0)  # 首次连接前先等待 1 秒，给 Chromium 端口绑定留出缓冲时间
    for attempt in range(1, max_attempts + 1):
        try:
            return playwright_ctx.chromium.connect_over_cdp(ws_url)
        except Exception as e:
            last_err = e
            log(f"  ⚠️ connect_over_cdp 失败 (尝试 {attempt}/{max_attempts}): {type(e).__name__}: {e}", "GoogleFX")
            if attempt < max_attempts:
                time.sleep(delay_secs)
    raise last_err


def _connect_fx_page(playwright_ctx):
    """连接 Adspower 浏览器并导航到 Google FX 页面。返回 (browser, page)。

    增强: 
    1. 如果连接 CDP 失败 (比如代理 IP 不通导致调试端口未开启)，自动执行紧急代理 IP 轮换并重启重试，最多重试 3 次。
    2. 检测到 Google 安全拦截 (unusual activity / security check) 时，
       自动关闭浏览器 → 换 IP → 重启浏览器 → 重试导航，最多重试 1 次。
    """
    max_conn_attempts = 3
    browser = None
    
    for attempt in range(1, max_conn_attempts + 1):
        try:
            ws_url = get_ads_ws_url()
            browser = _connect_over_cdp_with_retry(playwright_ctx, ws_url)
            break
        except Exception as e:
            log(f"⚠️ 连接 AdsPower/CDP 失败 (尝试 {attempt}/{max_conn_attempts}): {type(e).__name__}: {e}", "GoogleFX")
            if attempt >= max_conn_attempts:
                log("❌ 已达到最大连接重试次数，放弃连接", "GoogleFX")
                raise e
            
            # 关闭可能处于残留状态的浏览器
            try:
                from config import get_runtime_default_user_id, get_runtime_default_port, DEFAULT_USER_ID, DEFAULT_PORT
                user_id = get_runtime_default_user_id() or DEFAULT_USER_ID
                port = get_runtime_default_port() or DEFAULT_PORT
                url = f"http://127.0.0.1:{port}/api/v1/browser/stop?user_id={user_id}"
                requests.get(url, timeout=10)
            except Exception:
                pass
                
            log("🚨 检测到连接失败，可能代理 IP 失效，正在执行紧急代理 IP 轮换...", "GoogleFX")
            try:
                from utils.proxy_rotator import ProxyRotator
                rotator = ProxyRotator()
                if rotator.is_configured:
                    rotator.rotate_proxy(force=True)
                    log("✅ 已完成紧急代理 IP 轮换，准备下一次连接尝试...", "GoogleFX")
                else:
                    log("⚠️ Miya 代理未配置，无法换 IP", "GoogleFX")
            except Exception as rotate_err:
                log(f"⚠️ 紧急换 IP 失败: {type(rotate_err).__name__}: {rotate_err}", "GoogleFX")
            
            time.sleep(2)

    context = browser.contexts[0]
    page = find_or_create_page(context, "labs.google")
    page.bring_to_front()
    if "labs.google" not in page.url:
        page.goto("https://labs.google/fx/tools/flow", timeout=60000)
        random_sleep(1, 2)

    try:
        _raise_if_manual_intervention_required(page, context_label="Google FX 页面初始化")
    except RuntimeError as e:
        err_msg = str(e).lower()
        if "security_check" in err_msg or "unusual" in err_msg or "captcha" in err_msg:
            log("⚠️ 检测到 Google 安全拦截，尝试换 IP 后重试...", "GoogleFX")
            # 关闭当前浏览器
            try:
                browser.close()
            except Exception:
                pass
            # 强制再次换 IP
            try:
                from utils.proxy_rotator import ProxyRotator
                rotator = ProxyRotator()
                if rotator.is_configured:
                    rotator.rotate_proxy(force=True)
                    log("✅ 已完成紧急换 IP，重新启动浏览器...", "GoogleFX")
                else:
                    log("⚠️ Miya 代理未配置，无法换 IP，将直接重试", "GoogleFX")
            except Exception as rotate_err:
                log(f"⚠️ 紧急换 IP 失败: {type(rotate_err).__name__}: {rotate_err}", "GoogleFX")
            # 重新启动浏览器（跳过代理轮换，因为刚刚已经换过）
            ws_url = get_ads_ws_url(auto_rotate_proxy=False)
            browser = _connect_over_cdp_with_retry(playwright_ctx, ws_url)
            context = browser.contexts[0]
            page = find_or_create_page(context, "labs.google")
            page.bring_to_front()
            page.goto("https://labs.google/fx/tools/flow", timeout=60000)
            random_sleep(2, 4)
            # 再次检测，如果仍然被拦截则抛出异常
            _raise_if_manual_intervention_required(page, context_label="Google FX 换 IP 后重试")
        else:
            raise

    return browser, page


def _raise_if_manual_intervention_required(page, context_label="Google FX"):
    """Detect login, captcha, or security gates and stop for manual handling."""
    try:
        state = page.evaluate("""() => {
            const text = (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').trim();
            const lower = text.toLowerCase();
            const hasRecaptchaFrame = Array.from(document.querySelectorAll('iframe[src]')).some((frame) => {
                const src = (frame.getAttribute('src') || '').toLowerCase();
                if (src.includes('size=invisible')) return false;
                return src.includes('recaptcha') || src.includes('captcha') || src.includes('/anchor');
            });
            const patterns = [
                ['captcha_required', ['captcha', 'recaptcha', 'not a robot', '机器人', '人机验证']],
                ['login_required', ['sign in', 'log in', 'login', '登录', 'signin']],
                ['security_check', ['unusual traffic', 'unusual activity', 'suspicious', '安全检查', '验证身份']],
                ['verification_required', ['verify it is you', 'verify your identity', 'verification', '二次验证', '真人']]
            ];
            if (hasRecaptchaFrame) return {code: 'captcha_required', reason: 'recaptcha iframe detected'};
            for (const [code, needles] of patterns) {
                for (const needle of needles) {
                    if (lower.includes(needle.toLowerCase())) {
                        return {code, reason: needle, sample: text.slice(0, 500)};
                    }
                }
            }
            return null;
        }""")
        if state:
            raise RuntimeError(
                f"MANUAL_REQUIRED:{state.get('code')}:"
                f"{context_label}需要人工处理 ({state.get('reason')})"
            )
    except RuntimeError:
        raise
    except Exception as e:
        log(f"⚠️ 人工接管状态检测失败: {type(e).__name__}", "GoogleFX")


def _prepare_fx_canvas(page, has_refs, delete_failed_cards=True):
    """清理画布：删除失败卡片 + 条件性打开最新历史项目/新建项目 + 等待工具栏。"""
    if delete_failed_cards:
        _delete_failed_cards(page)

    # 如果当前没有打开任何项目（即输入框/工具栏不存在），优先尝试打开最新历史项目，找不到再新建项目
    toolbar_exists = _find_fx_prompt_input(page, announce=False) is not None
    if not toolbar_exists:
        log("📍 未检测到活跃项目输入框，优先尝试打开最新历史项目...", "GoogleFX")
        project_clicked = False
        try:
            project_clicked = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a'));
                // 查找 href 包含 /project/ 或 /tools/flow/project/ 的链接
                const projectLink = links.find(a => {
                    const href = a.getAttribute('href') || '';
                    return href.includes('/project/') || href.includes('/tools/flow/project/');
                });
                if (projectLink && projectLink.offsetParent !== null) {
                    projectLink.click();
                    return true;
                }
                return false;
            }""")
            if project_clicked:
                log("✅ 成功点击最新历史项目卡片，等待加载...", "GoogleFX")
                random_sleep(3, 5)
        except Exception as e:
            log(f"⚠️ 尝试打开历史项目异常: {e}", "GoogleFX")

        if not project_clicked:
            log("📍 未能打开历史项目，尝试新建项目...", "GoogleFX")
            try:
                if not _click_new_project_button(page):
                    log("⚠️ 未能通过标准按钮新建项目，尝试直接导航到 Flow URL 刷新并新建项目", "GoogleFX")
                    page.goto("https://labs.google/fx/tools/flow", timeout=60000)
                    random_sleep(2, 4)
                    project_clicked_retry = page.evaluate("""() => {
                        const links = Array.from(document.querySelectorAll('a'));
                        const projectLink = links.find(a => {
                            const href = a.getAttribute('href') || '';
                            return href.includes('/project/') || href.includes('/tools/flow/project/');
                        });
                        if (projectLink && projectLink.offsetParent !== null) {
                            projectLink.click();
                            return true;
                        }
                        return false;
                    }""")
                    if project_clicked_retry:
                        log("✅ 刷新后成功点击最新历史项目卡片，等待加载...", "GoogleFX")
                        random_sleep(3, 5)
                    else:
                        _click_new_project_button(page)
            except Exception as e:
                log(f"⚠️ 强制新建项目失败: {e}", "GoogleFX")

    if has_refs:
        # 如果有参考图，且是在项目内，等待画布卡片加载完毕
        try:
            log("⏳ 等待画布图片卡片加载...", "GoogleFX")
            page.locator("div[data-tile-id]").first.wait_for(state="visible", timeout=10000)
            log("✅ 画布图片卡片已加载", "GoogleFX")
        except Exception:
            log("⚠️ 等待画布图片卡片超时，可能画布为空，将继续后续流程", "GoogleFX")
    _wait_for_fx_toolbar(page, timeout=MAX_WAIT_SECONDS)


_CAPTURED_DATA_MAXLEN = 200
_SLATE_EDITOR_SELECTOR = "[data-slate-editor='true']"


# ==============================================================================
# 🔧 提取的模块级辅助函数 (原内部闭包，已提到模块级以支持独立测试/复用)
# ==============================================================================







def _get_panel_uuids(page):
    """纯 DOM 扫描页面中现有图片缓存，不主动打开/关闭 add_2 面板。"""
    uuids = set()
    try:
        srcs = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img[src*="getMediaUrlRedirect"]'))
                .map(img => img.getAttribute('src') || '');
        }""")
        for src in srcs:
            m = re.search(r'name=([0-9a-f\-]{30,})', src)
            if m:
                uuids.add(m.group(1))
    except Exception as e:
        log(f"  ⚠️ _get_panel_uuids 失败: {e}", "GoogleFX")
    return uuids


def _count_error_cards(page):
    """用 JS 数唯一 Failed 卡片 DOM 元素，避免多选择器重复计数。
    🔧 2026-05-16: 只计 warning/error icon 确认的失败卡片，不触发自动重试。
    """
    try:
        return page.evaluate("""() => {
            const seen = new Set();
            const tiles = Array.from(document.querySelectorAll('div[data-tile-id]'));
            for (const tile of tiles) {
                const tileId = tile.getAttribute('data-tile-id');
                if (!tileId || seen.has(tileId)) continue;
                const t = (tile.innerText || '').toLowerCase();
                const hasFailText = t.includes('failed') || t.includes('something went wrong') || t.includes('unusual activity') || t.includes('help center') || t.includes('失败') || t.includes('出错了') || t.includes('生成失败');
                if (!hasFailText) continue;
                // 额外校验: 必须有 warning/error icon 且可见
                const isVisible = (el) => {
                    let cur = el;
                    while (cur) {
                        const style = window.getComputedStyle(cur);
                        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
                            return false;
                        }
                        cur = cur.parentElement;
                    }
                    return true;
                };
                const icons = Array.from(tile.querySelectorAll('i'));
                const hasWarningIcon = icons.some(i => {
                    const txt = (i.innerText || i.textContent || '').trim().toLowerCase();
                    const isWarning = txt === 'warning' || txt === 'error' || txt === 'error_outline';
                    return isWarning && isVisible(i);
                });
                if (hasWarningIcon) seen.add(tileId);
            }
            return seen.size;
        }""")
    except Exception as e:
        log(f"  ⚠️ _count_error_cards JS 失败: {type(e).__name__}", "GoogleFX")
        return 0


def _delete_failed_cards(page):
    """批量删除页面中可见的 Failed 卡片，避免旧失败结果干扰当前轮次。
    🔧 2026-05-16: 只删除 warning/error icon 确认的失败卡片，不触发自动重试。
    """
    try:
        deleted = page.evaluate("""() => {
            const cards = Array.from(document.querySelectorAll('div[data-tile-id]'));
            let count = 0;

            function isVisible(el) {
                let cur = el;
                while (cur) {
                    const style = window.getComputedStyle(cur);
                    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
                        return false;
                    }
                    cur = cur.parentElement;
                }
                return true;
            }

            for (const card of cards) {
                const text = (card.innerText || '').toLowerCase();
                if (!text.includes('failed') && !text.includes('something went wrong') && !text.includes('unusual activity') && !text.includes('help center') && !text.includes('失败') && !text.includes('出错了') && !text.includes('生成失败')) continue;

                // 额外校验: 必须有 warning/error icon 才认定为真正失败
                const icons = Array.from(card.querySelectorAll('i'));
                const hasWarningIcon = icons.some(i => {
                    const t = (i.innerText || i.textContent || '').trim().toLowerCase();
                    const isWarning = t === 'warning' || t === 'error' || t === 'error_outline';
                    return isWarning && isVisible(i);
                });
                const btns = Array.from(card.querySelectorAll('button'));
                if (!hasWarningIcon) continue;

                const deleteBtn = btns.find((btn) => {
                    const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                    const btnText = (btn.innerText || '').toLowerCase();
                    const icon = (btn.querySelector('i')?.innerText || '').trim().toLowerCase();
                    return label.includes('delete') || btnText.includes('delete_forever') || icon === 'delete_forever';
                });

                if (deleteBtn) {
                    deleteBtn.click();
                    count += 1;
                }
            }

            return count;
        }""")
        if deleted:
            log(f"🧹 删除 {deleted} 个失败卡片", "GoogleFX")
            random_sleep(0.6, 1.0)
        return deleted
    except Exception as e:
        log(f"  ⚠️ _delete_failed_cards 失败: {type(e).__name__}", "GoogleFX")
        return 0


def _mount_uuid_as_ref(page, uuid):
    """
    将刚上传到画廸的图片挂载到输入框参考区。
    步骤: 关闭 add_2 面板 → 等待画布卡片 → more_vert → Add to Prompt
    """
    try:
        _safe_press_escape(page, "_mount_uuid_as_ref 关闭资产面板")
        random_sleep(0.5, 0.8)
        try:
            page.locator(f"[data-tile-id] img[src*='{uuid}']").first.wait_for(
                state="visible", timeout=10000
            )
        except Exception:
            pass  # 没有 data-tile-id 也继续尝试
        ok = _add_flow_image_to_prompt(page, uuid)
        if ok:
            log(f"  ✅ 参考图已挂载: {uuid[:16]}...", "GoogleFX")
        else:
            log(f"  ⚠️ _add_flow_image_to_prompt 返回 False: {uuid[:16]}...", "GoogleFX")
        return ok
    except Exception as e:
        log(f"  ⚠️ 挂载参考图失败: {e}", "GoogleFX")
        _safe_press_escape(page, "挂载参考图失败后关闭弹层")
        return False


def _safe_press_escape(page, context_label, sleep_range=None):
    """按 Escape 关闭当前弹层；失败时记录异常类型，避免静默吞掉。"""
    try:
        page.keyboard.press("Escape")
        if sleep_range:
            random_sleep(*sleep_range)
        return True
    except Exception as e:
        log(f"⚠️ {context_label}: keyboard.press('Escape') 失败: {type(e).__name__}", "GoogleFX")
        return False


def _find_fx_prompt_input(page, announce=False):
    """定位 Google FX 底部输入框，优先 Slate.js 编辑器。"""
    selectors = [_SLATE_EDITOR_SELECTOR] + UI_SELECTORS["google_fx"].get("prompt_input", [])
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible():
                if announce and sel == _SLATE_EDITOR_SELECTOR:
                    log("📝 检测到 Slate.js 编辑器", "GoogleFX")
                return el
        except Exception:
            pass
    return None


def _wait_for_flow_reference_ready(page, timeout_seconds=30, settle_range=None):
    """
    等待图生图参考图在 Flow 输入区真正挂载完成。
    返回 (ready: bool, matched_selector: str)。
    检测到就绪信号后仅做一次短暂随机稳定等待，避免每轮都硬等 10s。
    ✅ 2026-04-05 更新: 增加基于实测 DOM 的稳定选择器
    """
    ready_selectors = [
        # ✅ 实测最稳定: 底部输入框内出现图片缩略图
        "div[contenteditable='true'] img",
        "div[data-slate-editor='true'] img",
        # ✅ 实测: 相同机位第二张片内图片写入框
        "div[data-slate-editor] img",
        # ✅ 2026-04-11 实测: 视频模式 Add to Prompt 会把图片挂到输入框左侧素材槽
        "button[data-card-open] img[alt*='present in your collection']",
        "button[data-card-open] i:text-is('cancel')",
        # 备用: Remove 按钮 / ingredient 提示
        "[aria-label*='Remove']:visible",
        "span:has-text('This is your ingredient')",
        # 备用: 集合图片
        "img[alt*='present in your collection']",
    ]

    deadline = time.time() + max(timeout_seconds, 1)
    while time.time() < deadline:
        try:
            # 尝试传统 Selector
            for sel in ready_selectors:
                if page.locator(sel).first.is_visible(timeout=100):
                    if settle_range:
                        lo, hi = settle_range
                        random_sleep(lo, hi)
                    return True, sel
                    
            # 增加大范围兜底 JS 探测：视频模式下，底部输入区左侧素材槽也算成功挂载
            js_found = page.evaluate("""() => {
                const editor = document.querySelector("div[role='textbox'][contenteditable='true'], textarea");
                if (!editor) return false;
                let container = editor;
                for (let i = 0; i < 6; i++) {
                    if (container.parentElement) container = container.parentElement;
                }
                const promptImgs = Array.from(container.querySelectorAll("img")).filter((img) => {
                    const rect = img.getBoundingClientRect();
                    return rect.top > window.innerHeight - 360 && ((img.offsetHeight || 0) > 20 || (img.offsetWidth || 0) > 20);
                });
                const hasPromptMedia = promptImgs.some((img) => {
                    const alt = (img.getAttribute("alt") || "").toLowerCase();
                    return alt.includes("present in your collection") || alt.includes("generated image");
                });
                const hasCancelChip = Array.from(container.querySelectorAll("button i")).some((icon) => {
                    const rect = icon.getBoundingClientRect();
                    const text = (icon.textContent || "").trim().toLowerCase();
                    return rect.top > window.innerHeight - 360 && text === "cancel";
                });
                return hasPromptMedia || hasCancelChip;
            }""")
            
            if js_found:
                if settle_range:
                    lo, hi = settle_range
                    random_sleep(lo, hi)
                return True, "js_dom_sniffer"
                
        except Exception:
            pass
            
        time.sleep(1)
    return False, ""


























def _get_prompt_reference_uuids(page, limit=4):
    """读取提示词输入区中已挂入的参考图顺序，按视觉顺序返回 UUID 列表。"""
    try:
        rows = page.evaluate("""() => {
            const uuidRegex = /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i;
            const imgs = Array.from(document.querySelectorAll(
                "button[data-card-open] img, div[data-slate-editor='true'] img, div[contenteditable='true'] img, img[alt*='present in your collection']"
            ));
            const seen = new Set();
            const rows = [];
            for (const img of imgs) {
                if (!img || img.offsetParent === null) continue;
                const rect = img.getBoundingClientRect();
                if ((rect.width || 0) < 20 || (rect.height || 0) < 20) continue;
                if (rect.top < window.innerHeight - 420) continue;
                const src = img.currentSrc || img.src || '';
                const match = src.match(uuidRegex);
                if (!match) continue;
                const uuid = match[1];
                if (seen.has(uuid)) continue;
                seen.add(uuid);
                rows.push({ uuid, top: rect.top || 0, left: rect.left || 0 });
            }
            rows.sort((a, b) => {
                if (a.top !== b.top) return a.top - b.top;
                return a.left - b.left;
            });
            return rows.map((row) => row.uuid);
        }""")
    except Exception as e:
        log(f"⚠️ 读取 Prompt 参考图顺序失败: {type(e).__name__}", "GoogleFX")
        return []
    return rows[:max(limit, 1)]








def _ensure_output_dir(req, default_subdir):
    """解析并创建输出目录，保持现有默认规则不变。"""
    output_dir = req.output_path if (hasattr(req, "output_path") and req.output_path) else os.path.join(OUTPUT_DIR, default_subdir)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


# ==============================================================================
# 🔧 Google FX 底部工具栏配置工具函数 (适配 UI 大改版)
# ==============================================================================

def find_fx_config_button(page):
    """
    找到底部工具栏的配置状态按钮。
    真实状态按钮永远同时包含「模型名」和「数量 (x1-x4 或 1x-4x)」，
    而面板内的模型下拉按钮只含 arrow_drop_down。
    务必区分这两种按钮。
    """
    model_kws = ["Banana", "Nano", "Imagen", "Video", "Veo", "Pro", "视频", "图片"]
    count_kws = ["x1", "x2", "x3", "x4", "1x", "2x", "3x", "4x"]

    def _clean_btn_text(text):
        clean = re.sub(r"\s+", " ", (text or "")).strip()
        for noise in ["arrow_drop_down", "arrow_forward", "arrow_back", "▾", "▴"]:
            clean = clean.replace(noise, "").strip()
        return re.sub(r"\s+", " ", clean).strip()

    def _search():
        # 策略1: 同时含「模型关键词」和「数量」——这才是真实状态按钮
        for mkw in model_kws:
            for ckw in count_kws:
                try:
                    btn = page.locator("button").filter(has_text=mkw).filter(has_text=ckw)
                    if btn.count():
                        for i in range(btn.count()):
                            candidate = btn.nth(i)
                            if not candidate.is_visible():
                                continue
                            txt = _clean_btn_text(candidate.inner_text())
                            if ckw in txt and any(kw in txt for kw in model_kws):
                                log(f"  找到配置按钮 ('{mkw}'+'{ckw}'): '{txt}'", "GoogleFX")
                                return candidate, txt
                except: pass

        # 策略2: 只含数量，但同时授含模型关键词（避免单独 x1 误匹配选项按钮）
        for ckw in count_kws:
            try:
                btns = page.locator("button").filter(has_text=ckw)
                for i in range(btns.count()):
                    b = btns.nth(i)
                    if not b.is_visible(): continue
                    txt = _clean_btn_text(b.inner_text())
                    if ckw in txt and any(kw in txt for kw in model_kws):
                        log(f"  找到配置按钮 (count='{ckw}'): '{txt}'", "GoogleFX")
                        return b, txt
            except: pass

        # 策略3: 兼容备用——只接受真正像状态摘要 of 按钮
        for pattern in model_kws:
            try:
                btns = page.locator("button").filter(has_text=pattern)
                for i in range(btns.count()):
                    btn = btns.nth(i)
                    if not btn.is_visible():
                        continue
                    txt = _clean_btn_text(btn.inner_text())
                    has_count = any(ckw in txt for ckw in count_kws)
                    has_ratio = any(token in txt for token in ["crop_", "16:9", "9:16", "4:3", "3:4", "1:1"])
                    is_video_summary = txt.startswith("Video ") or txt.startswith("Video") or txt.startswith("视频") or "veo" in txt.lower()
                    if has_count or has_ratio or is_video_summary:
                        log(f"  找到配置按钮 (fallback '{pattern}'): '{txt}'", "GoogleFX")
                        return btn, txt
            except: pass
        return None, ""

    res_btn, res_txt = _search()
    if res_btn:
        return res_btn, res_txt

    # 如果没有找到，检查“智能体”按钮是否处于高亮（激活）状态
    try:
        agent_btn = page.locator("button").filter(has_text="智能体").first
        if agent_btn.count() > 0 and agent_btn.is_visible():
            pressed = agent_btn.get_attribute("aria-pressed")
            if pressed == "true":
                log("  ⚠️ 未找到配置按钮，且发现“智能体”处于激活状态。点击“智能体”取消激活以恢复显示配置按钮...", "GoogleFX")
                agent_btn.click(force=True)
                random_sleep(1.0, 1.5)
                # 重新搜索
                res_btn, res_txt = _search()
                if res_btn:
                    return res_btn, res_txt
    except Exception as e:
        log(f"  ⚠️ 尝试点击“智能体”取消激活时异常: {e}", "GoogleFX")

    return None, ""


def _orientation_tokens(orientation):
    tokens = ORIENT_ICON_MAP.get(orientation, orientation)
    if isinstance(tokens, str):
        tokens = [tokens]
    return [t for t in tokens if t]


def _normalize_fx_status_text(text):
    """归一化状态栏/菜单文本，降低换行、图标、emoji 对匹配的干扰。"""
    clean = text or ""
    for noise in ["arrow_drop_down", "arrow_forward", "arrow_back", "▾", "▴"]:
        clean = clean.replace(noise, " ")
    clean = re.sub(r"[^\w\s:\-\.\[\]/]", " ", clean, flags=re.UNICODE)
    clean = re.sub(r"\s+", " ", clean).strip().lower()
    return clean


def _matches_model_status(text, model):
    if not model:
        return True
    clean = _normalize_fx_status_text(text)
    target = _normalize_fx_status_text(model)
    if not target:
        return True
    if "omni" in model.lower():
        return "omni" in clean or (("video" in clean or "视频" in clean) and "veo" not in clean)
    if model.lower().startswith("veo"):
        aliases = {target}
        if "lite" in target:
            # 兼容 Pro 等不同套餐下 Lite 模型文字的差异，使 "Veo 3.1 - Lite" 与 "Veo 3.1 - Lite [Lower Priority]" 相互匹配
            aliases.update({
                "veo 3 1 lite",
                "veo lite",
                "veo 3.1 - lite",
                "veo 3.1 - lite [lower priority]",
                "lower priority",
                "lite lower priority"
            })
        if "fast" in target:
            aliases.update({"veo 3 1 fast", "veo fast"})
        if "quality" in target:
            aliases.update({"veo 3 1 quality", "veo quality"})
        if "lower priority" in target:
            aliases.update({"lower priority"})
            if "lite" in target:
                aliases.update({"lite lower priority"})
        return any(alias and alias in clean for alias in aliases)
    if model.lower() == "imagen 4":
        return "imagen" in clean
    aliases = {target}
    if "nano banana 2" in target:
        aliases.update({"nano banana 2", "banana 2"})
    if "nano banana pro" in target:
        aliases.update({"nano banana pro", "banana pro"})
    return any(alias and alias in clean for alias in aliases)


def _click_fx_tab(page, label, scope=None):
    """点击新版 Flow 的 tab 按钮，并尽量确认选中态。"""
    root = scope or page
    label_norm = _normalize_fx_status_text(label)
    patterns = [
        ("[role='tab']", True),
        ("button", True),
    ]
    for selector, exact in patterns:
        try:
            btns = root.locator(selector).filter(has_text=re.compile(re.escape(label), re.I))
            count = btns.count()
            for i in range(count):
                btn = btns.nth(i)
                if not btn.is_visible():
                    continue
                blob = " ".join(filter(None, [
                    btn.inner_text() or "",
                    btn.get_attribute("id") or "",
                    btn.get_attribute("aria-label") or "",
                    btn.get_attribute("aria-controls") or "",
                    btn.get_attribute("data-state") or "",
                ]))
                blob_norm = _normalize_fx_status_text(blob)
                if label_norm not in blob_norm:
                    continue
                btn.click(force=True)
                random_sleep(0.4, 0.8)
                try:
                    if btn.get_attribute("aria-selected") == "true" or btn.get_attribute("data-state") == "active":
                        return True
                except Exception:
                    return True
                if exact:
                    return True
        except Exception:
            pass

    # JS 兜底：有些 tab 在 Playwright 文本定位下会被动画层拦截
    try:
        clicked = page.evaluate("""(targetLabel) => {
            const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            const target = norm(targetLabel);
            const btns = Array.from(document.querySelectorAll("[role='tab'],button"));
            const match = btns.find((b) => {
                if (b.offsetParent === null) return false;
                const blob = [
                    b.innerText || '',
                    b.id || '',
                    b.getAttribute('aria-label') || '',
                    b.getAttribute('aria-controls') || '',
                ].join(' ');
                return norm(blob).includes(target);
            });
            if (!match) return false;
            match.click();
            return true;
        }""", label)
        if clicked:
            random_sleep(0.4, 0.8)
            return True
    except Exception:
        pass
    return False


def _get_open_fx_config_panel(page, trigger_btn=None):
    """锁定当前打开的配置面板，优先使用 aria-labelledby 关联到底部摘要按钮。"""
    button_id = ""
    aria_controls = ""
    try:
        if trigger_btn is not None:
            button_id = (trigger_btn.get_attribute("id") or "").strip()
            aria_controls = (trigger_btn.get_attribute("aria-controls") or "").strip()
    except Exception:
        pass

    if button_id:
        try:
            panel = page.locator(
                f"[role='menu'][data-state='open'][aria-labelledby='{button_id}']"
            ).first
            if panel.is_visible(timeout=1500):
                return panel
        except Exception:
            pass

    if aria_controls:
        try:
            panel = page.locator(f"[id=\"{aria_controls}\"]").first
            if panel.is_visible(timeout=1500):
                return panel
        except Exception:
            pass

    for sel in UI_SELECTORS["google_fx"].get("config_panel_root", []):
        try:
            panel = page.locator(sel).first
            if panel.is_visible(timeout=1500):
                return panel
        except Exception:
            pass

    return None


def _find_fx_model_dropdown(page, scope=None):
    """定位配置面板中的模型下拉按钮。"""
    root = scope or _get_open_fx_config_panel(page) or page
    model_tokens = ["Banana", "Nano", "Imagen", "Veo", "Video", "Pro", "Quality", "Fast", "Lite", "Lower Priority", "3.1", "Omni", "Flash"]

    def _looks_like_model_button(btn):
        try:
            if not btn.is_visible():
                return False
            txt = btn.inner_text() or ""
            desc = " ".join(filter(None, [txt, btn.get_attribute("aria-label") or "", btn.get_attribute("id") or ""]))
            clean = _normalize_fx_status_text(desc)
            if not clean:
                return False
            if any(x in clean for x in [" x1", " x2", " x3", " x4"]):
                return False
            if any(token in clean for token in ["16:9", "9:16", "4:3", "3:4", "1:1", "frames", "ingredients", "image", "video"]):
                if not any(kw.lower() in clean for kw in ["veo", "banana", "imagen", "omni"]):
                    return False
            return any(kw.lower() in clean for kw in [t.lower() for t in model_tokens])
        except Exception:
            return False

    # 优先: aria-haspopup='menu' + 模型关键词 (Radix UI 菜单触发按钮，最稳定)
    for kw in model_tokens:
        try:
            kw_btns = root.locator("button[aria-haspopup='menu']").filter(has_text=kw)
            for i in range(kw_btns.count()):
                btn = kw_btns.nth(i)
                if _looks_like_model_button(btn):
                    log(f"  🎯 模型下拉按钮 (aria-haspopup='menu' + '{kw}')", "GoogleFX")
                    return btn
        except Exception:
            pass

    for sel in [
        "button:has-text('arrow_drop_down')",
        "button[aria-haspopup='menu']",
        "[role='menu'] button",
        "[role='dialog'] button",
        "button",
    ]:
        try:
            btns = root.locator(sel)
            for i in range(btns.count()):
                btn = btns.nth(i)
                if _looks_like_model_button(btn):
                    return btn
        except Exception:
            pass
    return None


def _get_fx_model_dropdown_text(page, scope=None):
    """读取配置面板内模型下拉当前文字。"""
    try:
        model_dd = _find_fx_model_dropdown(page, scope=scope)
        if model_dd and model_dd.is_visible(timeout=1200):
            return (model_dd.inner_text() or "").strip()
    except Exception:
        pass
    return ""


def _click_fx_menu_item(page, label, button_id_hint="", menu_id_hint=""):
    """点击配置面板中的模型菜单项。"""
    target = _normalize_fx_status_text(label)
    resolved_menu_id = _resolve_open_flow_menu_id(page, button_id_hint, menu_id_hint)
    menu_scope = None
    if resolved_menu_id:
        try:
            menu_scope = page.locator(f"[id=\"{resolved_menu_id}\"]").first
            if not menu_scope.is_visible(timeout=1200):
                menu_scope = None
        except Exception:
            menu_scope = None

    scope = menu_scope or page
    el, _ = _click_first_visible(scope, [
        f"[role='menuitem']:has-text('{label}')",
        f"[role='option']:has-text('{label}')",
        f"li:has-text('{label}')",
        f"button:has-text('{label}')",
        f"div:has-text('{label}')",
    ], timeout=1200, force=True)
    if el:
        random_sleep(0.5, 1)
        return True

    try:
        clicked = page.evaluate("""({ targetLabel, menuId }) => {
            const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            const target = norm(targetLabel);
            const root = menuId ? document.getElementById(menuId) : document;
            const nodes = Array.from(root.querySelectorAll("[role='menuitem'],[role='option'],li,button,div"));
            const match = nodes.find((node) => {
                if (node.offsetParent === null) return false;
                const text = norm(node.innerText);
                return text === target || text.includes(target);
            });
            if (!match) return false;
            match.click();
            return true;
        }""", {"targetLabel": label, "menuId": resolved_menu_id})
        if clicked:
            random_sleep(0.5, 1)
            return True
    except Exception:
        pass

    # 兜底：按规范化文本扫描所有可见节点，兼容新 UI 把模型渲染为普通 div/button 的情况
    try:
        nodes = scope.locator("[role='menuitem'], [role='option'], li, button, div")
        for i in range(nodes.count()):
            node = nodes.nth(i)
            if not node.is_visible():
                continue
            text = _normalize_fx_status_text(node.inner_text() or "")
            if not text:
                continue
            if text == target or target in text:
                node.click(force=True)
                random_sleep(0.5, 1)
                return True
    except Exception:
        pass
    return False


def _matches_orientation_text(text, orientation):
    haystack = (text or "").lower()
    return any(token.lower() in haystack for token in _orientation_tokens(orientation))


def _click_orientation_option(page, orientation, scope=None):
    root = scope or page
    tokens = _orientation_tokens(orientation)
    patterns = [orientation] + tokens

    # ── 优先级 0: aria-controls 尾值精确匹配（Radix UI 固定业务值，最稳定）──
    _aria_key = (orientation or "").lower().replace(" ", "_").replace(":", "")
    _aria_suffix = _ARIA_CONTROLS_RATIO_MAP.get(_aria_key)
    if not _aria_suffix:
        # 也尝试按比例文字 (e.g. "9:16")
        for _k, _v in _ARIA_CONTROLS_RATIO_MAP.items():
            if _k in _aria_key or _aria_key in _k:
                _aria_suffix = _v
                break
    if _aria_suffix:
        for _sel in [
            f"[aria-controls$='-{_aria_suffix}']",
            f"[aria-controls*='-{_aria_suffix}']",
        ]:
            try:
                _btn = root.locator(_sel).last
                if _btn.is_visible(timeout=2000):
                    _btn.click(force=True)
                    random_sleep(0.5, 1)
                    log(f"  ✅ 点击比例 tab (aria-controls$='-{_aria_suffix}')", "GoogleFX")
                    return _aria_suffix
            except Exception as _e:
                log(f"  ⚠️ _click_orientation_option 优先级0 sel={_sel!r}: {type(_e).__name__}", "GoogleFX")

    # ── 优先级 1: 精确匹配新版 Flow UI tab（aria-controls 含 PORTRAIT / LANDSCAPE）──
    for pattern in patterns:
        for sel in [
            f"[role='tab'][aria-controls*='{pattern}']",
            f"[role='tab'][id*='{pattern}']",
            f"[role='tab']:has-text('{pattern}')",
        ]:
            try:
                option = root.locator(sel).last
                if option.is_visible():
                    option.click(force=True)
                    random_sleep(0.5, 1)
                    log(f"  ✅ 点击比例 tab (sel='{sel}')", "GoogleFX")
                    return pattern
            except Exception as e:
                log(f"  ⚠️ _click_orientation_option 优先级1 sel={sel!r}: {type(e).__name__}", "GoogleFX")

    # ── 优先级 2: 通用按钮 / 选项文本匹配 ──
    for pattern in patterns:
        el, _ = _click_first_visible(root, [
            f"button:has-text('{pattern}')",
            f"[role='option']:has-text('{pattern}')",
            f"[role='menuitem']:has-text('{pattern}')",
            f"li:has-text('{pattern}')",
            f"div:has-text('{pattern}')",
        ], force=True)
        if el:
            random_sleep(0.5, 1)
            return pattern

    # ── 优先级 3: JS 兜底 ──
    escaped = [token.replace("\\", "\\\\").replace("'", "\\'") for token in patterns]
    try:
        page.evaluate(
            """(patterns) => {
                const candidates = Array.from(document.querySelectorAll(
                    '[role="tab"], button, [role="option"], [role="menuitem"], li, div'
                ));
                const target = candidates.find((el) => {
                    const text = (el.innerText || '').trim();
                    const ac = el.getAttribute('aria-controls') || '';
                    const id = el.id || '';
                    return patterns.some((p) => text.includes(p) || ac.includes(p) || id.includes(p));
                });
                if (target) target.click();
            }""",
            escaped,
        )
        random_sleep(0.5, 1)
        return "/".join(patterns)
    except Exception as e:
        log(f"  ⚠️ _click_orientation_option JS兜底失败: {type(e).__name__}: {e}", "GoogleFX")
        return None


def check_fx_config(status_text, model="Nano Banana 2", orientation="Portrait", count="1x", duration=None, want_video=False, resolved_model_text=""):
    """
    从状态文字判断当前配置是否正确。
    先清除图标噪声文字（arrow_drop_down 等）再判断。

    Known models:
      Video: Veo 3.1 - Lite | Veo 3.1 - Fast | Veo 3.1 - Quality
           | Veo 3.1 - Lite [Lower Priority]
      Image: Nano Banana Pro | Nano Banana 2 | Imagen 4
    """
    # 清除 Google FX UI 图标语义噪声，避免对分支结果产生干扰
    clean = _normalize_fx_status_text(status_text)

    checks = {}
    # 视频模式下，状态栏常只显示 "Video"，不能再把它当成模型验证通过。
    model_source = resolved_model_text if (want_video and resolved_model_text) else status_text
    checks["model"] = _matches_model_status(model_source, model)
    checks["orientation"] = _matches_orientation_text(clean, orientation) if orientation else True
    checks["count"] = count.lower() in clean if count else True
    if want_video and duration:
        duration_label = _normalize_video_duration_label(duration)
        checks["duration"] = (duration_label in clean) if duration_label else True
    if want_video:
        checks["mode"] = ("video" in clean) or ("视频" in clean) or ("veo" in clean)
    else:
        checks["mode"] = ("video" not in clean) and ("视频" not in clean) and ("veo" not in clean)
    return checks


def fix_fx_config(page, cfg_btn, checks, model="Nano Banana 2", orientation="Portrait", count="1x", duration=None, want_video=False, mode_label="", video_submode=None):
    """打开配置面板并修正不正确的配置项。"""
    log("⚙️ 需要修改配置，打开面板...", "GoogleFX")
    cfg_btn.click()
    random_sleep(1.5, 2.5)
    fix_info = {
        "resolved_model_text": "",
        "duration_clicked": False,
        "video_submode_clicked": False,
        "clicked_keys": [],
        "resolved_keys": [],
    }
    panel_scope = _get_open_fx_config_panel(page, cfg_btn) or page

    if not checks.get("mode", True):
        target_mode_name = "Video" if want_video else "Image"
        target_mode_cn = "视频" if want_video else "图片"
        aria_mode_suffix = "VIDEO" if want_video else "IMAGE"
        desired_mode_labels = [label for label in [mode_label, target_mode_name, target_mode_cn] if label]
        log(f"  → 切换到 {target_mode_name} 模式 (aria-controls$='-{aria_mode_suffix}')", "GoogleFX")
        try:
            # 优先: aria-controls 尾值 (Radix UI 固定业务值，最稳定)
            _mode_btn = panel_scope.locator(f"[aria-controls$='-{aria_mode_suffix}']").first
            if _mode_btn.is_visible(timeout=2000):
                _mode_btn.click(force=True)
                random_sleep(0.5, 0.8)
                log(f"  ✅ {target_mode_name} 已点击 (aria-controls$='-{aria_mode_suffix}')", "GoogleFX")
                fix_info["clicked_keys"].append("mode")
            else:
                mode_clicked = False
                for label in desired_mode_labels:
                    if _click_fx_tab(page, label, scope=panel_scope):
                        log(f"  ✅ {label} 已点击 (tab fallback)", "GoogleFX")
                        mode_clicked = True
                        fix_info["clicked_keys"].append("mode")
                        break
                if not mode_clicked:
                    log(f"  ⚠️ 未找到 {target_mode_name} 模式 tab", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ {target_mode_name} 模式切换异常: {e}", "GoogleFX")

    if not checks.get("orientation", True):
        log(f"  → 切换到 {orientation}", "GoogleFX")
        try:
            matched = _click_orientation_option(page, orientation, scope=panel_scope)
            if matched:
                log(f"  ✅ {orientation} 已点击 ({matched})", "GoogleFX")
                fix_info["clicked_keys"].append("orientation")
            else:
                log(f"  ⚠️ 未找到 {orientation} 对应选项", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ {orientation} 切换异常: {e}", "GoogleFX")

    if not checks.get("count", True):
        log(f"  → 切换到 {count}", "GoogleFX")
        try:
            # 优先: role=tab + 文字精确匹配（比模糊匹配更安全，避免误点其他 tab）
            _count_btn = panel_scope.locator("button[role='tab']").filter(
                has_text=re.compile(f"^{re.escape(count)}$", re.I)
            ).first
            if _count_btn.is_visible(timeout=2000):
                _count_btn.click(force=True)
                random_sleep(0.4, 0.8)
                log(f"  ✅ {count} 已点击 (role=tab + 精确匹配)", "GoogleFX")
                fix_info["clicked_keys"].append("count")
            elif _click_fx_tab(page, count, scope=panel_scope):
                log(f"  ✅ {count} 已点击 (tab fallback)", "GoogleFX")
                fix_info["clicked_keys"].append("count")
            else:
                log(f"  ⚠️ 未找到 {count} 数量 tab", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ {count} 切换异常: {e}", "GoogleFX")

    duration_label = _normalize_video_duration_label(duration)
    if want_video and not checks.get("duration", True) and duration_label:
        log(f"  → 切换时长: 先点 4s，再点 {duration_label}", "GoogleFX")
        try:
            baseline_match = _click_video_duration_tab(page, panel_scope, "4s")
            if baseline_match:
                log(f"  ✅ 4s 已点击 ({baseline_match})", "GoogleFX")
            else:
                log("  ⚠️ 未找到 4s 时长 tab，继续尝试目标时长", "GoogleFX")

            if duration_label == "4s" and baseline_match:
                log("  ✅ 目标时长 4s 已通过基准点击确认", "GoogleFX")
                fix_info["duration_clicked"] = True
                fix_info["clicked_keys"].append("duration")
            else:
                target_match = _click_video_duration_tab(page, panel_scope, duration_label)
                if target_match:
                    log(f"  ✅ {duration_label} 已点击 ({target_match})", "GoogleFX")
                    fix_info["duration_clicked"] = True
                    fix_info["clicked_keys"].append("duration")
                else:
                    log(f"  ⚠️ 未找到 {duration_label} 时长 tab", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ {duration_label} 切换异常: {e}", "GoogleFX")

    # ── 视频子模式切换 (帧 VIDEO_FRAMES / 素材 VIDEO_REFERENCES) ──
    if want_video and not checks.get("video_submode", True) and video_submode:
        _target_suffix = video_submode  # e.g. 'VIDEO_FRAMES'
        _submode_label = '帧' if video_submode == 'VIDEO_FRAMES' else '素材'
        log(f"  → 切换视频子模式到 {_submode_label} ({_target_suffix})", "GoogleFX")
        if _switch_video_submode(page, _target_suffix, scope=panel_scope):
            log(f"  ✅ 视频子模式已切换: {_submode_label}", "GoogleFX")
            fix_info["video_submode_clicked"] = True
            fix_info["clicked_keys"].append("video_submode")
        else:
            log(f"  ⚠️ 视频子模式切换失败: {_submode_label}", "GoogleFX")

    if not checks.get("model", True):
        log(f"  → 切换到 {model}", "GoogleFX")
        try:
            model_dd = _find_fx_model_dropdown(page, scope=panel_scope)

            if model_dd and model_dd.is_visible():
                curr = _get_fx_model_dropdown_text(page, scope=panel_scope)
                log(f"  模型下拉文字: '{curr}'", "GoogleFX")
                # 如果当前模型名已包含目标模型，无需切换
                if _matches_model_status(curr, model):
                    log(f"  ✅ 模型已正确: {model}", "GoogleFX")
                    fix_info["resolved_model_text"] = curr
                    fix_info["resolved_keys"].append("model")
                else:
                    model_dd.click(force=True)
                    random_sleep(1, 2)
                    # 等待下拉选项出现
                    page.wait_for_timeout(800)
                    model_btn_id = ""
                    try:
                        model_btn_id = (model_dd.get_attribute("id") or "").strip()
                    except Exception:
                        pass
                    selected = False
                    # 备选模型列表，用于处理免费/付费/Pro套餐等不同套餐下模型的不同命名/可用性 (例如 Veo 3.1 - Lite 与 Veo 3.1 - Lite [Lower Priority] 互为备选)
                    candidate_models = [model]
                    if model == "Veo 3.1 - Lite [Lower Priority]":
                        candidate_models.append("Veo 3.1 - Lite")
                    elif model == "Veo 3.1 - Lite":
                        candidate_models.append("Veo 3.1 - Lite [Lower Priority]")

                    for target_model in candidate_models:
                        if _click_fx_menu_item(page, target_model, button_id_hint=model_btn_id):
                            log(f"  ✅ {target_model} 已选择 (match '{target_model}')", "GoogleFX")
                            selected = True
                            fix_info["clicked_keys"].append("model")
                            break

                    # 策略2: 关键词匹配 (如 'Banana Pro', 'Imagen 4')
                    if not selected:
                        # 取模型名中最具区分性的部分
                        keywords = [model]  # 首先尝试全名
                        if " " in model:
                            parts = model.split()
                            # 去掉过短的单词，取后半部分组合
                            keywords += [" ".join(parts[-2:]), " ".join(parts[-3:]), parts[-1]]
                        for kw in keywords:
                            if len(kw) < 2: continue
                            if _click_fx_menu_item(page, kw, button_id_hint=model_btn_id):
                                log(f"  ✅ {model} 已选择 (keyword='{kw}')", "GoogleFX")
                                selected = True
                                fix_info["clicked_keys"].append("model")
                            if selected: break
                    if not selected:
                        log(f"  ❌ 模型 '{model}' 选项未找到", "GoogleFX")
                    current_after = _get_fx_model_dropdown_text(page, scope=panel_scope)
                    fix_info["resolved_model_text"] = current_after
                    log(f"  模型下拉复检: '{current_after or '<空>'}'", "GoogleFX")
            else:
                log(f"  ❌ 模型下拉按钮未找到", "GoogleFX")
        except Exception as e:
            log(f"  ❌ 模型异常: {e}", "GoogleFX")
    elif want_video:
        fix_info["resolved_model_text"] = _get_fx_model_dropdown_text(page, scope=panel_scope)

    # 关闭面板: 先按 Escape，再等待面板收起
    try:
        page.keyboard.press("Escape")
    except Exception as e:
        log(f"  ⚠️ fix_fx_config 关闭面板 Escape 失败: {type(e).__name__}", "GoogleFX")
    random_sleep(1.5, 2.5)  # 等待底部工具栏状态按钮恢复显示正确内容
    return fix_info


def click_fx_send_button(page, input_el=None):
    """点击发送按钮 (新版 UI: arrow icon / aria-label / Create / Enter)"""
    sent = False
    # 方法0: Generate 按钮（新版 Flow UI 首选，aria-controls 稳定 Radix UI）
    # ✅ Patch: scroll_into_view + hover + 随机停顿，避免直接 click 触发反自动化检测
    try:
        gen_btn = page.locator("button").filter(
            has_text=re.compile(r"^Generate$", re.I)
        ).last
        if gen_btn.is_visible(timeout=1500):
            gen_btn.scroll_into_view_if_needed()
            gen_btn.hover()
            random_sleep(0.3, 0.7)   # 鼠标停在按钮上的自然停顿
            gen_btn.click()
            sent = True
            log("✅ 已点击 Generate 按钮", "GoogleFX")
    except Exception as e:
        log(f"  ⚠️ click_fx_send Generate: {type(e).__name__}", "GoogleFX")
    # 方法1: 找包含 arrow icon 的按钮
    if not sent:
        try:
            all_btns = page.locator("button:visible")
            cnt = all_btns.count()
            for bi in range(cnt - 1, max(cnt - 10, -1), -1):
                try:
                    b = all_btns.nth(bi)
                    t = b.inner_text().strip()
                    if 'arrow_forward' in t or 'send' in t or 'arrow_upward' in t:
                        b.click()
                        sent = True
                        log("✅ 已点击发送 (arrow icon)", "GoogleFX")
                        break
                except Exception as e:
                    log(f"  ⚠️ click_fx_send 方法1 内层: {type(e).__name__}", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ click_fx_send 方法1 外层: {type(e).__name__}: {e}", "GoogleFX")
    # 方法2: aria-label
    if not sent:
        for label in ["Send", "send", "Submit", "submit", "Create"]:
            try:
                sb = page.locator(f"button[aria-label*='{label}']").last
                if sb.is_visible():
                    sb.click()
                    sent = True
                    log(f"✅ 已点击发送 (aria-label: {label})", "GoogleFX")
                    break
            except Exception as e:
                log(f"  ⚠️ click_fx_send 方法2 label={label!r}: {type(e).__name__}", "GoogleFX")
    # 方法3: Create / Generate 按钮（文字包含匹配兜底）
    if not sent:
        for _btn_text in ["Generate", "Create"]:
            try:
                fallback_btn = page.locator("button").filter(has_text=_btn_text).last
                if fallback_btn.is_visible():
                    fallback_btn.click()
                    sent = True
                    log(f"✅ 已点击 {_btn_text} 按钮", "GoogleFX")
                    break
            except Exception as e:
                log(f"  ⚠️ click_fx_send 方法3 {_btn_text}: {type(e).__name__}: {e}", "GoogleFX")
    # 方法4: Enter
    if not sent and input_el:
        input_el.press("Enter")
        log("⚠️ 按 Enter 提交", "GoogleFX")
        sent = True

    if sent:
        try:
            from utils.proxy_rotator import ProxyRotator
            ProxyRotator().increment_request_counter(1)
        except Exception as e:
            log(f"⚠️ 递增代理请求计数器异常: {e}", "GoogleFX")

    return sent

# ==============================================================================
# 🖼️ 图生图：将已有 Flow 图片加为 Prompt 参考
# ==============================================================================



def _add_flow_image_to_prompt(page, image_ref: str, tile_id: str = "") -> bool:
    """
    在 Flow 画布中找到指定图片，hover → [role='toolbar'] → more_vert → Add to Prompt。
    实测 DOM (2026-04-07):
      - hover tile 后出现 [role='toolbar']（含 favorite / redo / more_vert 三个按钮）
      - more_vert 按钮: button[aria-haspopup='menu'] 在 toolbar 内
      - 点击后弹出 [role='menu'][data-state='open']
      - Add to Prompt: button[role='menuitem']:has-text('Add to Prompt')
    image_ref: UUID | 完整 getMediaUrlRedirect URL | 含 UUID 的本地路径
    返回 True 表示成功，False 表示失败（不中断生成流程）。
    """
    # 提取 UUID（支持: 纯UUID / getMediaUrlRedirect URL / 含UUID的本地路径）
    uuid = _extract_flow_image_uuid(image_ref)
    if not uuid and not tile_id:
        log(f"⚠️ 无法解析参考图定位信息: '{str(image_ref)[:60]}'", "GoogleFX")
        return False

    ref_label = (uuid or tile_id or "unknown")[:16]
    log(f"🖼️ 图生图: hover tile → more_vert → Add to Prompt ({ref_label}...)", "GoogleFX")

    try:
        max_mount_attempts = 2
        for mount_attempt in range(1, max_mount_attempts + 1):
            _safe_press_escape(page, f"_add_flow_image_to_prompt 起始清理 attempt={mount_attempt}")
            if mount_attempt == 1:
                random_sleep(0.3, 0.5)
            else:
                log(f"  ↺ 挂载重试第 {mount_attempt} 次，放慢点击节奏", "GoogleFX")
                random_sleep(0.9, 1.4)

            # 1. 确认画布上有此图，获取位置信息并锁定 tile
            canvas_img = _resolve_flow_tile_info(page, uuid=uuid or "", tile_id=tile_id or "")

            if not canvas_img:
                log(f"  ⚠️ 画布上未找到目标卡片: {ref_label}...", "GoogleFX")
                return False

            tile_id = (canvas_img.get("tileId") or "").strip()
            log(
                f"  🎯 找到画布图片 {canvas_img['w']:.0f}×{canvas_img['h']:.0f}px"
                + (f" | tile={tile_id[:12]}..." if tile_id else "")
                + (f" | mount_attempt={mount_attempt}" if max_mount_attempts > 1 else ""),
                "GoogleFX",
            )

            # 2. 进入 hover 态并尝试直接点击 toolbar 中的 "Add to prompt" 按钮
            before_refs = _get_prompt_reference_uuids(page, limit=6)
            _hover_flow_tile_for_toolbar(page, uuid=uuid or "", tile_id=tile_id)
            
            clicked_direct = False
            if tile_id:
                try:
                    tile_scope = page.locator(f"[data-tile-id='{tile_id}']").first
                    toolbar = tile_scope.locator("[role='toolbar']").first
                    if toolbar.is_visible(timeout=1000):
                        # 查找候选按钮（直接包含 Add / 添加 或 Prompt / 提示 的按钮）
                        for direct_sel in [
                            "button[aria-label*='Prompt']",
                            "button[title*='Prompt']",
                            "button[aria-label*='prompt']",
                            "button[title*='prompt']",
                            "button[aria-label*='提示词']",
                            "button[title*='提示词']",
                            "button[aria-label*='提示']",
                            "button[title*='提示']",
                            "button[aria-label='Add']",
                            "button[title='Add']",
                            "button[aria-label='添加']",
                            "button[title='添加']",
                            "button:has-text('Add')",
                            "button:has-text('添加')",
                        ]:
                            btn = toolbar.locator(direct_sel).first
                            if btn.is_visible(timeout=500):
                                btn.click(force=True)
                                log(f"  ✅ [Direct Click] 在 toolbar 中直接点击了 {direct_sel!r}", "GoogleFX")
                                clicked_direct = True
                                break
                except Exception as _direct_err:
                    log(f"  ⚠️ 尝试直接点击 toolbar 按钮失败: {_direct_err}", "GoogleFX")

            menu_id_hint = ""
            if not clicked_direct:
                # 3. 备选: 点击 more_vert 弹出菜单再选择
                menu_id_hint = _click_flow_more_menu(page, uuid=uuid or "", tile_id=tile_id)
                menu_open = False
                for menu_sel in [
                    "[role='menu'][data-state='open']",
                    "[data-radix-menu-content][data-state='open']",
                    "[role='menu']",
                ]:
                    try:
                        if page.locator(menu_sel).last.is_visible(timeout=500 + (mount_attempt - 1) * 300):
                            menu_open = True
                            break
                    except Exception:
                        continue
                if not menu_id_hint and not menu_open:
                    log(
                        f"  ❌ Add to Prompt 失败 | stage=menu_not_open | tile_id={tile_id or '<none>'} | "
                        f"menu_id=<none> | refs_before={before_refs} | mount_attempt={mount_attempt}",
                        "GoogleFX",
                    )
                    if mount_attempt < max_mount_attempts:
                        continue
                    return False

                if mount_attempt == 1:
                    random_sleep(0.4, 0.7)
                else:
                    random_sleep(0.8, 1.2)

                # 4. 点击 Add to Prompt 菜单项
                if not _click_flow_add_to_prompt(page, menu_id_hint=menu_id_hint, tile_id_hint=tile_id):
                    if mount_attempt < max_mount_attempts:
                        continue
                    return False

            ready, ready_sel = _wait_for_flow_reference_ready(
                page,
                timeout_seconds=10 + (mount_attempt - 1) * 4,
                settle_range=(0.3, 0.6) if mount_attempt == 1 else (0.8, 1.2),
            )
            changed, after_refs = _wait_for_prompt_reference_change(
                page,
                previous_refs=before_refs,
                expected_uuid=uuid or "",
                timeout_seconds=8 + (mount_attempt - 1) * 4,
            )
            if ready or changed:
                log(
                    f"✅ 参考图 {uuid[:16]}... 已加入 Prompt | ready={ready} | "
                    f"selector={ready_sel or '<none>'} | refs_after={after_refs} | mount_attempt={mount_attempt}",
                    "GoogleFX",
                )
                return True

            after_refs_norm = [item.lower() for item in after_refs] if after_refs else []
            if uuid and uuid.lower() in after_refs_norm:
                log(
                    f"✅ 参考图 {uuid[:16]}... 已在 references 列表中命中（兜底）| selector={ready_sel or '<none>'} | "
                    f"refs_after={after_refs} | mount_attempt={mount_attempt}",
                    "GoogleFX",
                )
                return True

            log(
                f"  ❌ Add to Prompt 失败 | stage=prompt_ref_not_attached | tile_id={tile_id or '<none>'} | "
                f"menu_id={menu_id_hint or '<none>'} | refs_before={before_refs} | "
                f"refs_after={after_refs} | mount_attempt={mount_attempt}",
                "GoogleFX",
            )
            _safe_press_escape(page, f"_add_flow_image_to_prompt 挂图失败收尾 attempt={mount_attempt}")

        return False

    except Exception as e:
        log(f"⚠️ _add_flow_image_to_prompt 失败: {e}", "GoogleFX")
        _safe_press_escape(page, "_add_flow_image_to_prompt 异常收尾")
        return False


# ==============================================================================
# 🎬 Google FX (Veo 3.1) 视频生成
# ==============================================================================

def _generate_video_google_fx(req: VideoRequest):
    return _run_with_google_fx_dedupe("single_video", req, _generate_video_google_fx_unlocked)




# ==============================================================================
# 🎬 Google FX (Veo 3.1) 批量视频 — 多任务并行提交 & 统一监听
# ==============================================================================











def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(int(os.getenv(name, str(default))), minimum)
    except (TypeError, ValueError):
        return default


_VIDEO_BATCH_FORCE_SERIAL = os.getenv("GOOGLE_FX_VIDEO_BATCH_FORCE_SERIAL", "1").strip().lower() not in ("0", "false", "no")
_GOOGLE_FX_RUN_LOCK_WAIT_SECONDS = _env_int("GOOGLE_FX_RUN_LOCK_WAIT_SECONDS", 1800, minimum=1)
_GOOGLE_FX_DEDUP_TTL_SECONDS = _env_int("GOOGLE_FX_DEDUP_TTL_SECONDS", 600, minimum=0)
_GOOGLE_FX_RUN_LOCK = threading.RLock()
_GOOGLE_FX_DEDUP_LOCK = threading.Lock()
_GOOGLE_FX_INFLIGHT_REQUESTS = {}


def _request_payload_for_dedupe(req):
    """Return a stable plain dict for request de-duplication."""
    if hasattr(req, "model_dump"):
        return req.model_dump()
    if hasattr(req, "dict"):
        return req.dict()
    return getattr(req, "__dict__", str(req))


def _google_fx_request_fingerprint(label: str, req) -> str:
    payload = _request_payload_for_dedupe(req)
    raw = json.dumps({"label": label, "payload": payload}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _purge_google_fx_dedupe_cache(now: float):
    if _GOOGLE_FX_DEDUP_TTL_SECONDS <= 0:
        return
    expired = [
        key for key, entry in _GOOGLE_FX_INFLIGHT_REQUESTS.items()
        if entry.get("done_at") and now - entry["done_at"] > _GOOGLE_FX_DEDUP_TTL_SECONDS
    ]
    for key in expired:
        _GOOGLE_FX_INFLIGHT_REQUESTS.pop(key, None)


def _run_with_google_fx_lock(label: str, fn, *args, **kwargs):
    """Serialize Google FX page automation; the shared Flow canvas is not concurrency-safe."""
    log(f"🔐 等待 Google FX 运行锁: {label}", "GoogleFX")
    _check_cancelled()
    acquired = _GOOGLE_FX_RUN_LOCK.acquire(timeout=_GOOGLE_FX_RUN_LOCK_WAIT_SECONDS)
    if not acquired:
        raise RuntimeError(f"Google FX run lock timeout after {_GOOGLE_FX_RUN_LOCK_WAIT_SECONDS}s: {label}")
    try:
        _check_cancelled()
        log(f"🔐 已获得 Google FX 运行锁: {label}", "GoogleFX")
        return fn(*args, **kwargs)
    finally:
        try:
            _GOOGLE_FX_RUN_LOCK.release()
            log(f"🔓 已释放 Google FX 运行锁: {label}", "GoogleFX")
        except RuntimeError:
            pass


def _run_with_google_fx_dedupe(label: str, req, fn):
    """
    Coalesce duplicate Google FX requests.

    n8n or an HTTP client may retry the same payload while the first UI run is
    still active. Without this guard, the same prompt can be submitted twice to
    Flow. Duplicates wait for the first run and reuse its result.
    """
    if _GOOGLE_FX_DEDUP_TTL_SECONDS <= 0:
        return _run_with_google_fx_lock(label, fn, req)

    key = _google_fx_request_fingerprint(label, req)
    short_key = key[:12]
    now = time.time()
    owner = False

    with _GOOGLE_FX_DEDUP_LOCK:
        _purge_google_fx_dedupe_cache(now)
        entry = _GOOGLE_FX_INFLIGHT_REQUESTS.get(key)
        if entry is None:
            entry = {
                "event": threading.Event(),
                "started_at": now,
                "done_at": None,
                "result": None,
                "error": None,
            }
            _GOOGLE_FX_INFLIGHT_REQUESTS[key] = entry
            owner = True
        elif entry.get("done_at"):
            log(f"♻️ 命中重复 Google FX 请求缓存: {label} key={short_key}", "GoogleFX")
            if entry.get("error"):
                raise RuntimeError(str(entry["error"]))
            return copy.deepcopy(entry.get("result"))
        else:
            log(f"♻️ 检测到重复 Google FX 请求，等待首个任务完成: {label} key={short_key}", "GoogleFX")

    if not owner:
        wait_timeout = _GOOGLE_FX_RUN_LOCK_WAIT_SECONDS + MAX_WAIT_SECONDS + 60
        if not entry["event"].wait(timeout=wait_timeout):
            raise RuntimeError(f"Duplicate Google FX request wait timeout: {label} key={short_key}")
        if entry.get("error"):
            raise RuntimeError(str(entry["error"]))
        return copy.deepcopy(entry.get("result"))

    try:
        result = _run_with_google_fx_lock(label, fn, req)
        with _GOOGLE_FX_DEDUP_LOCK:
            if isinstance(result, dict) and result.get("status") == "failed":
                _GOOGLE_FX_INFLIGHT_REQUESTS.pop(key, None)
            else:
                entry["result"] = copy.deepcopy(result)
                entry["done_at"] = time.time()
        return result
    except Exception as e:
        with _GOOGLE_FX_DEDUP_LOCK:
            _GOOGLE_FX_INFLIGHT_REQUESTS.pop(key, None)
        raise
    finally:
        entry["event"].set()






def _generate_videos_batch_google_fx(req):
    return _run_with_google_fx_dedupe("video_batch", req, _generate_videos_batch_google_fx_unlocked)




# ==============================================================================
# 🖼️ Google FX (Nano Banana 2 / Imagen 3) 图片批量生成
# ==============================================================================

def _generate_images_batch_google_fx(req: ImageBatchRequest):
    return _run_with_google_fx_dedupe("image_batch", req, _generate_images_batch_google_fx_unlocked)




# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📦 子模块入口向下兼容路由 (Route and Re-export)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from services.google_fx_video import (
    _generate_video_google_fx_unlocked,
    _generate_videos_batch_google_fx_unlocked,
)

from services.google_fx_image import (
    _generate_images_batch_google_fx_unlocked,
)
