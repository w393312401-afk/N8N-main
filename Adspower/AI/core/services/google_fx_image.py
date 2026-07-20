# -*- coding: utf-8 -*-
"""
🖼️ Google FX Image Service (Imagen Image Generation - Pure Execution)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import re
import time
import random
import base64
import hashlib
import json
from collections import deque
import requests
from playwright.sync_api import sync_playwright

from config import MAX_WAIT_SECONDS, OUTPUT_DIR
from models import ImageBatchRequest
from utils.logger import log
from utils.browser import random_sleep, clean_path
from utils.ui_helpers import inject_batch_image_observer
from utils import cancel_flag

# L1 DOM 原语
from services.google_fx_dom import _click_first_visible, _find_first_visible, _safe_press_escape
# L2 FX 页面语义 (含媒体捕获 / 输出目录 / 取消检测 / 代理轮换)
from services.google_fx_helpers import (
    _check_cancelled,
    _trigger_emergency_proxy_rotation,
    _CAPTURED_DATA_MAXLEN,
    _normalize_ratio_value,
    _normalize_model_name,
    _verify_and_fix_fx_config,
    _connect_fx_page,
    _raise_if_manual_intervention_required,
    _prepare_fx_canvas,
    _get_panel_uuids,
    _count_error_cards,
    _delete_failed_cards,
    _make_response_handler,
    _ensure_output_dir,
    _clear_prompt_reference_chips_image,
    _add_flow_image_to_prompt,
    _wait_for_flow_reference_ready,
    _find_fx_prompt_input,
    _mount_uuid_as_ref,
    click_fx_send_button,
    _get_prompt_reference_uuids,
)

# ── _generate_images_batch_google_fx_unlocked ──
def _generate_images_batch_google_fx_single_attempt(req: ImageBatchRequest):
    _check_cancelled()
    browser = None
    captured_data = deque(maxlen=_CAPTURED_DATA_MAXLEN)
    result = {"status": "failed", "image_urls": [], "message": ""}

    # Check max limitation
    prompts = req.prompts[:5]
    if not prompts:
        result["message"] = "No prompts provided"
        return result

    log(f"🚀 Google FX 批量生图请求: {len(prompts)} 个, 首个: {prompts[0][:30]}...", "GoogleFX")
    # 模型名归一化：将任意别名/错误名称映射为真实模型
    req.model = _normalize_model_name(req.model, is_video=False)
    log(f"  ℹ️ 实际使用模型: {req.model}", "GoogleFX")

    try:
        with sync_playwright() as p:
            browser, page = _connect_fx_page(p)

            # 🛠️ 0. 新建/清理画布
            _has_ref_images = bool([r for r in (req.images or []) if r and os.path.exists(clean_path(str(r)))])
            _prepare_fx_canvas(page, has_refs=_has_ref_images)


            # 🛠️ 2. 验证配置 (Image 模式)
            selected_ratio = _verify_and_fix_fx_config(
                page, model=req.model, ratio=req.ratio,
                want_video=False, context_label="图片生成",
            )
            # 🛠️ 2.5 参考图挂载 (图生图: 从文件名提取 UUID → canvas tile → Add to Prompt)
            # 要求参考图是此 project 内曾生成的图片，UUID 在画布中可见。
            def _wait_for_new_panel_image(known_uuids, timeout=MAX_WAIT_SECONDS):
                """
                轮询 add_2 面板，直到出现 known_uuids 中没有的新 UUID，返回该 UUID。
                ⚡ 快捷退出: 若编辑器内已检测到 cancel chip（挂载成功标志），
                              立即返回哨兵值 '__chip_mounted__'，避免空等 UUID。
                """
                _CHIP_SENTINEL = "__chip_mounted__"
                _chip_sels = [
                    "div[contenteditable='true'] i.google-symbols:text-is('cancel')",
                    "div[contenteditable='true'] i:text-is('cancel')",
                ]
                deadline = time.time() + timeout
                while time.time() < deadline:
                    _check_cancelled()
                    # ── UUID 检测 ──
                    cur_uuids = _get_panel_uuids(page)  # 使用模块级函数
                    new_uuids = cur_uuids - known_uuids
                    if new_uuids:
                        new_uuid = next(iter(new_uuids))
                        log(f"  🎉 面板出现新图 UUID: {new_uuid[:16]}...", "GoogleFX")
                        return new_uuid
                    # ── cancel chip 早退：chip 已在编辑器内，无需等 UUID ──
                    for _cs in _chip_sels:
                        try:
                            if page.locator(_cs).first.is_visible(timeout=200):
                                log("  ⚡ 检测到 cancel chip，跳过 UUID 等待", "GoogleFX")
                                return _CHIP_SENTINEL
                        except Exception:
                            pass
                    elapsed = int(deadline - time.time())
                    if elapsed % 10 == 0 and elapsed > 0:
                        log(f"  ⏳ 等待新图出现... 剩余 {elapsed}s", "GoogleFX")
                    time.sleep(3)
                return None


            # 🛠️ 2.4 准备并彻底清空编辑器，删除所有历史文本与历史参考图
            input_el = _find_fx_prompt_input(page, announce=True)
            if not input_el:
                raise Exception("无法找到输入框")
            log("🧹 正在彻底清空输入框及历史参考图...", "GoogleFX")
            # 先清掉挂在编辑器之外「素材槽」里的历史参考图 chip
            # （Ctrl+A/Backspace 只能清空编辑器内部，够不到这些）
            _clear_prompt_reference_chips_image(page)
            try:
                input_el.click()
                random_sleep(0.3, 0.5)
                page.keyboard.press("Control+a")
                random_sleep(0.1, 0.2)
                page.keyboard.press("Meta+a")
                random_sleep(0.1, 0.2)
                page.keyboard.press("Backspace")
                random_sleep(0.3, 0.5)
            except Exception as e:
                log(f"  ⚠️ 清空输入框异常: {e}", "GoogleFX")

            ref_image_refs = [clean_path(str(r)) for r in (req.images or []) if r]
            # ⚠️ 去重：防止 n8n 传入重复路径导致同一图片多次处理
            valid_refs = list(dict.fromkeys(p for p in ref_image_refs if os.path.exists(p)))
            if valid_refs:
                log(f"🖼️ 检测到 {len(valid_refs)} 张参考图，从文件名提取 UUID 并在画布挂载...", "GoogleFX")
                mounted_count = 0
                for local_path in valid_refs:
                    _uuid_m = re.search(
                        r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
                        os.path.basename(local_path)
                    )
                    if not _uuid_m:
                        log(f"  ⚠️ 文件名无法提取 UUID，跳过: {os.path.basename(local_path)}", "GoogleFX")
                        continue
                    _ref_uuid = _uuid_m.group(1)
                    log(f"  📎 参考图 UUID: {_ref_uuid[:16]}... ({os.path.basename(local_path)})", "GoogleFX")
                    _ok = _add_flow_image_to_prompt(page, _ref_uuid)
                    if _ok:
                        mounted_count += 1
                        _rr, _rs = _wait_for_flow_reference_ready(page, timeout_seconds=15, settle_range=(0.5, 1.0))
                        if _rr:
                            log(f"  ✅ 参考图已挂入编辑器 (sel={_rs!r})", "GoogleFX")
                        else:
                            log(f"  ⚠️ 挂载后未检测到 cancel chip，继续", "GoogleFX")
                    else:
                        log(f"  ❌ 参考图挂载失败 (UUID: {_ref_uuid[:16]}...)", "GoogleFX")

                if mounted_count == 0:
                    log("⚠️ 所有参考图均未成功挂载，以无参考模式生成", "GoogleFX")
                    valid_refs = []
                else:
                    log(f"✅ 参考图处理完毕 ({mounted_count}/{len(valid_refs)} 张成功)", "GoogleFX")

            elif ref_image_refs:
                log(f"⚠️ 参考图本地文件不存在，跳过挂载: {ref_image_refs}", "GoogleFX")
            
            # 🛠️ 3. 准备 Slate.js 编辑器
            input_el = _find_fx_prompt_input(page, announce=True)
            if not input_el:
                raise Exception("无法找到输入框")

            existing_imgs = set()
            try:
                existing_imgs = set(page.evaluate("""() => Array.from(document.images || [])
                    .map(img => img.currentSrc || img.src || '')
                    .filter(Boolean)"""))
            except Exception as e:
                log(f"  ⚠️ 获取现有图片列表失败: {type(e).__name__}", "GoogleFX")

            inject_batch_image_observer(page, existing_imgs)
            log("🔍 准备生成并监控网络...", "GoogleFX")

            # ━━━ 网络拦截: 监听图片生成相关的网络响应 ━━━
            handle_response = _make_response_handler(captured_data, mode="image")
            page.on("response", handle_response)
            submit_ts = time.time()


            existing_error_count = _count_error_cards(page)  # 模块级函数
            log(f"  📋 提交前页面已有错误卡片: {existing_error_count} 个", "GoogleFX")


            # 🛠️ 4+5. 串行提交 + 等待 + 参考图链式挂载
            # 流程: 提交 prompt[0] → 等第0张图出现在 add_2 面板 → 选中它 → 提交 prompt[1] → ...
            # 这样保证每张图生成完毕才触发下一张，实现真正的图生图链式生成。


            # ── 辅助: 只填写文字（不发送，供后续挂参考后再 submit）──
            def _fill_text_only(prompt_text, idx, has_ref=False):
                """
                把 prompt 写入编辑器，返回 True/False，不触发发送。
                has_ref=True: 编辑器里已经挂了参考图 chip，必须禁止 fill() / Meta+a
                             （两者都会清空整个编辑器内容，把 chip 一起删掉），
                             改为 click→End→keyboard.type() 追加文字。
                has_ref=False: 正常流程，允许 fill() 先清空再写入。
                """
                prompt_filled = False

                # ── 有参考图：只用追加方式，不能清空编辑器 ──
                if has_ref:
                    # 方法A: click → End → 直接 keyboard.insert_text() 追加
                    # ⚠️ 注意：绝对不能用 fill() / Meta+a / selectAll / Backspace
                    #   以上任何清空操作都会把编辑器里的参考图 chip 一起删掉
                    try:
                        input_el.click(); random_sleep(0.3, 0.5)
                        page.keyboard.press("End"); random_sleep(0.1, 0.2)
                        # 使用 insert_text 瞬间粘贴内容，避免逐字敲打的缓慢
                        page.keyboard.insert_text(prompt_text); random_sleep(0.3, 0.5)
                        
                        # 特殊保护：因为前面是输入文字，可能没触发 react 状态更新，按个空格触发一下
                        page.keyboard.press("Space")
                        
                        if prompt_text[:15].lower() in input_el.inner_text().strip().lower():
                            prompt_filled = True
                            log(f"✅ keyboard.insert_text() 追加写入 (有参考图): 第 {idx+1} 个", "GoogleFX")
                    except Exception as e:
                        log(f"⚠️ keyboard.insert_text() 追加失败: {e}", "GoogleFX")

                    # 方法B: execCommand insertText 追加（fill 的 no-clear 替代）
                    if not prompt_filled:
                        try:
                            input_el.click(); random_sleep(0.2, 0.3)
                            page.evaluate("""(text) => {
                                const editor = document.querySelector('[data-slate-editor=true]');
                                if (editor) {
                                    editor.focus();
                                    // 只选文字节点，不选 chip 内联元素
                                    const sel = window.getSelection();
                                    if (sel && sel.rangeCount) {
                                        const r = sel.getRangeAt(0);
                                        r.collapse(false);  // 移到末尾
                                    }
                                }
                                document.execCommand('insertText', false, text);
                            }""", prompt_text)
                            random_sleep(0.3, 0.5)
                            if prompt_text[:15].lower() in input_el.inner_text().strip().lower():
                                prompt_filled = True
                                log(f"✅ execCommand insertText (有参考图): 第 {idx+1} 个", "GoogleFX")
                        except Exception as e:
                            log(f"⚠️ execCommand (有参考图) 失败: {e}", "GoogleFX")

                    if not prompt_filled:
                        log(f"❌ 第 {idx+1} 个 prompt 所有追加方法均失败 (有参考图模式)", "Error")
                    return prompt_filled

                # ── 无参考图：原始三方法，fill() 优先 ──
                # 方法1: fill()
                try:
                    input_el.click(); random_sleep(0.3, 0.5)
                    input_el.fill(prompt_text); random_sleep(0.2, 0.4)
                    if prompt_text[:15].lower() in input_el.inner_text().strip().lower():
                        prompt_filled = True
                        log(f"✅ fill() 写入: 第 {idx+1} 个", "GoogleFX")
                except Exception as e:
                    log(f"⚠️ fill() 失败: {e}", "GoogleFX")
                # 方法2: keyboard.type()
                if not prompt_filled:
                    try:
                        input_el.click(); random_sleep(0.2, 0.3)
                        page.keyboard.press("ControlOrMeta+a"); page.keyboard.press("Backspace")
                        random_sleep(0.2, 0.3)
                        page.keyboard.type(prompt_text, delay=15); random_sleep(0.3, 0.5)
                        if prompt_text[:15].lower() in input_el.inner_text().strip().lower():
                            prompt_filled = True
                            log(f"✅ keyboard.type() 写入: 第 {idx+1} 个", "GoogleFX")
                    except Exception as e:
                        log(f"⚠️ keyboard.type() 失败: {e}", "GoogleFX")

                # 方法3: execCommand()
                if not prompt_filled:
                    try:
                        input_el.click(); random_sleep(0.2, 0.3)
                        page.evaluate("""(text) => {
                            document.execCommand('selectAll', false, null);
                            document.execCommand('insertText', false, text);
                        }""", prompt_text)
                        random_sleep(0.3, 0.5)
                        if prompt_text[:15].lower() in input_el.inner_text().strip().lower():
                            prompt_filled = True
                            log(f"✅ execCommand 写入: 第 {idx+1} 个", "GoogleFX")
                    except Exception as e:
                        log(f"⚠️ execCommand 失败: {e}", "GoogleFX")

                if not prompt_filled:
                    log(f"❌ 第 {idx+1} 个 prompt 所有输入方法均失败", "Error")
                return prompt_filled

            # 🔄 串行执行: 提交 → 等网络捕获 URL → 下载到本地 → 挂参考/提交下一张
            existing_error_count = _count_error_cards(page)
            log(f"  📋 提交前已有错误卡片: {existing_error_count} 个", "GoogleFX")

            output_dir = _ensure_output_dir(req, "images")

            local_paths = []       # 最终保存的本地路径列表
            all_result_urls = []   # 对应的网络 URL（用于面板 UUID 提取）

            def _download_image(img_url, save_idx):
                """下载单张图到本地，返回 local_path 或 None"""
                m_uuid = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', img_url)
                if m_uuid:
                    local_path = os.path.join(output_dir, f"fx_batch_{int(time.time())}_{save_idx}_{m_uuid.group(1)}.jpg")
                else:
                    local_path = os.path.join(output_dir, f"fx_batch_{int(time.time())}_{save_idx}.jpg")

                # ── data URL (canvas.toDataURL) ──
                if img_url.startswith("data:image/"):
                    try:
                        b64_part = img_url.split(",", 1)[1] if "," in img_url else ""
                        img_bytes = base64.b64decode(b64_part)
                        with open(local_path, "wb") as f:
                            f.write(img_bytes)
                        log(f"  ✅ Canvas数据保存: {len(img_bytes)} bytes", "GoogleFX")
                        return local_path
                    except Exception as e:
                        log(f"  ⚠️ Canvas解码失败: {e}", "GoogleFX")
                        return None

                # ── labs.google URL (getMediaUrlRedirect) 需要 cookie → 用 browser fetch ──
                # ── 其他非 http URL → 也用 browser fetch ──
                use_browser_fetch = (
                    "labs.google" in img_url
                    or not img_url.startswith("http")
                )

                if not use_browser_fetch:
                    # ── GCS / 其他公开直链 → requests.get ──
                    try:
                        r = requests.get(img_url, stream=True, timeout=15)
                        r.raise_for_status()
                        with open(local_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                        log(f"  ✅ 直链下载完成: {local_path}", "GoogleFX")
                        return local_path
                    except Exception as e:
                        log(f"  ⚠️ 直链下载失败，降级 browser fetch: {e}", "GoogleFX")
                        use_browser_fetch = True

                # ── browser fetch (带 cookie，适用于 labs.google 及直链失败的兜底) ──
                if use_browser_fetch:
                    try:
                        b64_data = page.evaluate("""async (url) => {
                            const response = await fetch(url);
                            const blob = await response.blob();
                            return new Promise((resolve, reject) => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result.split(',')[1]);
                                reader.onerror = reject;
                                reader.readAsDataURL(blob);
                            });
                        }""", img_url)
                        img_bytes = base64.b64decode(b64_data)
                        with open(local_path, "wb") as f:
                            f.write(img_bytes)
                        log(f"  ✅ Browser fetch 下载完成: {local_path}", "GoogleFX")
                        return local_path
                    except Exception as e:
                        log(f"  ⚠️ Browser fetch 下载失败: {e}", "GoogleFX")
                        return None

            def _wait_for_net_url(submit_ts_this, timeout=MAX_WAIT_SECONDS, known_tile_ids_before_submit=None,
                                   _current_prompt_text=None, _current_prompt_idx=None,
                                   _has_ref_for_this_prompt=False):
                """
                双路并行检测新图片 URL:
                  路径A — 网络拦截 captured_data (被动等待)
                  路径B — DOM 扫描页面上新出现的 img[src*='getMediaUrlRedirect'] (主动探测)
                哪路先出结果就返回，不需要打开面板。
                """
                deadline = time.time() + timeout
                known_net = set(url for ts, url in captured_data if ts < submit_ts_this)

                # 记录提交前页面上已有的 getMediaUrlRedirect img srcs（Canvas + 其他区域）
                try:
                    known_dom_srcs = set(page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('img[src*="getMediaUrlRedirect"]'))
                            .map(img => img.getAttribute('src') || '');
                    }"""))
                except Exception as e:
                    log(f"  ⚠️ 初始化 known_dom_srcs 失败: {type(e).__name__}", "GoogleFX")
                    known_dom_srcs = set()

                poll_count = 0
                while time.time() < deadline:
                    _check_cancelled()
                    poll_count += 1

                    # ── 路径A: 网络拦截 ──
                    for ts, url in reversed(captured_data):
                        if ts >= submit_ts_this - 1 and url not in known_net:
                            log(f"  📡 路径A 网络捕获: {url[:80]}...", "GoogleFX")
                            return url

                    # ── 路径B: DOM 扫描 Canvas 上新出现的图片 ──
                    try:
                        cur_dom_srcs = set(page.evaluate("""() => {
                            return Array.from(document.querySelectorAll('img[src*="getMediaUrlRedirect"]'))
                                .map(img => img.getAttribute('src') || '');
                        }"""))
                        new_srcs = cur_dom_srcs - known_dom_srcs
                        if new_srcs:
                            new_src = next(iter(new_srcs))
                            # 转为绝对 URL
                            full_url = new_src if new_src.startswith("http") else f"https://labs.google{new_src}"
                            log(f"  🖼️  路径B DOM扫描捕获: {new_src[:80]}...", "GoogleFX")
                            return full_url
                    except Exception as e:
                        log(f"  ⚠️ 路径B DOM扫描: {type(e).__name__}", "GoogleFX")

                    # ── 路径C: 检测新提交卡片是否已报错失败 ──
                    try:
                        has_new_failed = page.evaluate("""(beforeIds) => {
                            const beforeSet = new Set(beforeIds || []);
                            const cards = Array.from(document.querySelectorAll('div[data-tile-id]'));
                            
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
                                const tid = card.getAttribute('data-tile-id');
                                if (!tid || beforeSet.has(tid)) continue;
                                const t = (card.innerText || '').toLowerCase();
                                const hasFailText = t.includes('failed') || t.includes('something went wrong')
                                                 || t.includes('unusual activity') || t.includes('help center')
                                                 || t.includes('出错了') || t.includes('生成失败')
                                                 || t.includes('失败') || t.includes('使用人数过多');
                                if (!hasFailText) continue;
                                const icons = Array.from(card.querySelectorAll('i'));
                                const hasWarningIcon = icons.some(i => {
                                    const txt = (i.innerText || i.textContent || '').trim().toLowerCase();
                                    const isWarning = txt === 'warning' || txt === 'error' || txt === 'error_outline';
                                    return isWarning && isVisible(i);
                                });
                                if (hasWarningIcon) return {failed: true, text: card.innerText};
                            }
                            return null;
                        }""", list(known_tile_ids_before_submit or []))
                        if has_new_failed:
                            log(f"  ❌ 检测到新提交卡片已报错失败: {has_new_failed['text'][:100]}", "GoogleFX")
                            return None
                    except Exception as e:
                        log(f"  ⚠️ 路径C 卡片报错检测失败: {type(e).__name__}", "GoogleFX")

                    elapsed = int(deadline - time.time())
                    if poll_count % 5 == 0 and elapsed > 0:
                        log(f"  ⏳ 等待图片 URL... 剩余 {elapsed}s (网络={len(captured_data)}, DOM扫描#{poll_count})", "GoogleFX")
                    time.sleep(2)

                return None

            for idx, prompt_text in enumerate(prompts):
                _check_cancelled()
                log(f"\n{'─'*40}", "GoogleFX")
                log(f"🖼️  Step {idx+1}/{len(prompts)}: '{prompt_text[:50]}...'", "GoogleFX")
                _delete_failed_cards(page)

                # ── Step A: 图生图模式（第一张）→ 参考图已在框里，用追加模式写入文字 ──
                # 注意：valid_refs 挂载是在进入循环前的 2.5 节完成的，
                #       所以第一张图时参考图 chip 已在编辑器中，必须用 has_ref=True 追加，
                #       不能用 fill() 否则 chip 会被清掉。
                has_ref_for_this_prompt = False
                if valid_refs and idx == 0:
                    refs_before_prompt = _get_prompt_reference_uuids(page, limit=8)
                    if refs_before_prompt:
                        has_ref_for_this_prompt = True
                        log(f"  ✅ 检测到参考图已就绪（预检查）", "GoogleFX")
                        filled = _fill_text_only(prompt_text, idx, has_ref=True)
                    else:
                        log(f"  ⏳ 等待参考图就绪信号...", "GoogleFX")
                        _ref_ready, ready_sel = _wait_for_flow_reference_ready(
                            page,
                            timeout_seconds=45,
                            settle_range=(1.0, 2.0),
                        )
                        if _ref_ready:
                            log(f"  ✅ 参考图已就绪 (sel={ready_sel!r})，开始追加输入提示词", "GoogleFX")
                            has_ref_for_this_prompt = True
                            # 有参考图 chip 在框里 → 追加模式，不清空编辑器
                            filled = _fill_text_only(prompt_text, idx, has_ref=True)
                        else:
                            log(f"  ⚠️ 等待45s 参考图仍未就绪，改用无参考模式输入该 prompt", "Error")
                            filled = _fill_text_only(prompt_text, idx, has_ref=False)
                else:
                    # ── 无参考图 / 后续图：正常 fill 写入 ──
                    filled = _fill_text_only(prompt_text, idx, has_ref=False)

                if not filled:
                    log(f"❌ 第 {idx+1} 个 prompt 输入失败，跳过", "Error")
                    continue

                # ── Step B: 非第一张时，在文字填好之后再挂参考图 chip ──
                # 顺序关键：fill 之后再 mount，chip 不会被 fill 清掉
                if idx > 0 and all_result_urls:
                    prev_url = all_result_urls[-1]
                    m_uuid = re.search(r'name=([0-9a-f\-]{30,})', prev_url)
                    if m_uuid:
                        ref_uuid = m_uuid.group(1)
                        log(f"🔗 挂载参考图 chip (UUID: {ref_uuid[:16]}...)", "GoogleFX")
                        mounted = _mount_uuid_as_ref(page, ref_uuid)  # 模块级函数
                        if mounted:
                            has_ref_for_this_prompt = True
                    else:
                        log(f"  ⚠️ 无法从 URL 提取 UUID，跳过参考图挂载", "GoogleFX")

                # ── Step C: 触发 React state 同步，然后发送 ──
                # ⚠️ 有参考图时禁止 Backspace（光标可能停在 chip 上，会把 chip 删掉）
                try:
                    input_el.click(); random_sleep(0.1, 0.2)
                    page.keyboard.press("End")
                    if has_ref_for_this_prompt:
                        # 有参考图首张：只追加空格触发 state 同步，不删除
                        # （Backspace 有概率删掉 chip，不安全）
                        page.keyboard.type(" "); random_sleep(0.15, 0.25)
                    else:
                        # 无参考图 / 后续图：Space+Backspace 触发 state 同步
                        page.keyboard.type(" "); random_sleep(0.1, 0.15)
                        page.keyboard.press("Backspace"); random_sleep(0.2, 0.3)
                except Exception as e:
                    log(f"  ⚠️ React state 触发: {type(e).__name__}", "GoogleFX")
                    if cancel_flag.is_cancelled:
                        raise
                # ✅ Patch: 提交前模拟人工确认停顿（1.2–2.8s），降低提交节奏被识别风险
                random_sleep(1.2, 2.8)

                try:
                    pre_submit_tile_ids = set(page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('div[data-tile-id]'))
                            .map(card => card.getAttribute('data-tile-id') || '')
                            .filter(Boolean);
                    }"""))
                except Exception as e:
                    log(f"  ⚠️ 记录提交前 tile 基线失败: {type(e).__name__}", "GoogleFX")
                    pre_submit_tile_ids = set()
                    if cancel_flag.is_cancelled:
                        raise

                click_fx_send_button(page, input_el)
                log(f"✅ 第 {idx+1}/{len(prompts)} 个 prompt 已提交", "GoogleFX")

                submit_ts_this = time.time()

                # ── 等网络捕获到 URL ──
                log(f"⏳ 等待第 {idx+1} 张图片网络 URL...", "GoogleFX")
                img_url = _wait_for_net_url(
                    submit_ts_this,
                    timeout=MAX_WAIT_SECONDS,
                    known_tile_ids_before_submit=pre_submit_tile_ids,
                    _current_prompt_text=prompt_text,
                    _current_prompt_idx=idx,
                    _has_ref_for_this_prompt=has_ref_for_this_prompt,
                )

                if not img_url:
                    log(f"⚠️ 第 {idx+1} 张图超时未捕获到 URL，跳过", "GoogleFX")
                    continue

                # ── 立即下载到本地 (下载完成 = 图已就绪) ──
                log(f"⬇️  开始下载第 {idx+1} 张图...", "GoogleFX")
                local_path = _download_image(img_url, idx)

                if local_path:
                    local_paths.append(local_path)
                    all_result_urls.append(img_url)
                    log(f"✅ 第 {idx+1} 张图下载完成，准备处理下一张", "GoogleFX")
                else:
                    log(f"⚠️ 第 {idx+1} 张图下载失败，使用原始 URL", "GoogleFX")
                    local_paths.append(img_url)
                    all_result_urls.append(img_url)

            if not local_paths:
                raise Exception("所有 prompt 均未捕获到图片")

            if len(local_paths) < len(prompts):
                log(f"⚠️ 批量生图未完全成功 ({len(local_paths)}/{len(prompts)} 成功)，触发紧急换 IP", "GoogleFX")
                _trigger_emergency_proxy_rotation()

            result["status"] = "success"
            result["image_urls"] = local_paths

    except Exception as e:
        if cancel_flag.is_cancelled or "任务已取消" in str(e):
            log("🛑 任务已取消，跳过代理轮换", "GoogleFX")
            result["message"] = "任务已取消"
        else:
            log(f"❌ generate_images_batch 内部错误: {e}", "Error")
            result["message"] = str(e)
            _trigger_emergency_proxy_rotation()
    finally:
        # 清理 response 事件监听器，防止复用 page 时 handler 堆积泄漏
        try:
            page.remove_listener("response", handle_response)
        except Exception:
            pass
        # 保持浏览器开启，避免画布被清空。后续由 n8n 在工作流末尾统一关闭。
        # if browser:
        #     try:
        #         browser.close()
        #     except Exception:
        #         pass  # CDP 连接模式下 close() 会抛出异常，这是预期行为

    return result


def _generate_images_batch_google_fx_unlocked(req: ImageBatchRequest):
    pacing_delay = random.uniform(15, 25)
    log(f"🕐 Pacing delay: sleeping {pacing_delay:.1f}s before starting generation...", "GoogleFX")
    time.sleep(pacing_delay)
    max_retries = 4
    last_err = None
    for attempt in range(1, max_retries + 1):
        log(f"🔄 开始第 {attempt}/{max_retries} 次图片生成尝试...", "GoogleFX")
        try:
            result = _generate_images_batch_google_fx_single_attempt(req)
            if result.get("status") == "success":
                return result
            err_msg = result.get("message", "")
            if "异常活动" in err_msg or "unusual activity" in err_msg or "所有 prompt 均未捕获到图片" in err_msg:
                raise RuntimeError(err_msg)
            return result
        except Exception as e:
            last_err = e
            if attempt == max_retries:
                break
            log(f"⚠️ 第 {attempt} 次图片生成失败: {e}，准备换 IP 重试...", "GoogleFX")
            cooldown_time = 15 * attempt
            log(f"🕐 冷却等待 {cooldown_time} 秒...", "GoogleFX")
            time.sleep(cooldown_time)
            try:
                from utils.proxy_rotator import ProxyRotator
                rotator = ProxyRotator()
                if rotator.is_configured:
                    rotator.rotate_proxy(force=True)
            except Exception as pr_err:
                log(f"⚠️ 强制换 IP 异常: {pr_err}", "GoogleFX")
    
    log(f"❌ 图片生成在 {max_retries} 次尝试后全部失败。", "GoogleFX")
    return {"status": "failed", "image_urls": [], "message": f"All attempts failed. Last error: {last_err}"}


