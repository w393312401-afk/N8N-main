# -*- coding: utf-8 -*-
"""
🛠️ Google FX Helpers (UI Interaction, Navigation, Upload & Canvas Helpers)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔒 LOCKED 2026-03-25 — 本文件包含 find_fx_config_button / check_fx_config /
   fix_fx_config (原定义于 services/google_fx.py，整体搬移，函数体逐字未改动)。
   禁止在未获用户明确指示前修改这三个函数的任何逻辑。
"""

import os
import re
import time
import random
import requests

from config import MAX_WAIT_SECONDS, OUTPUT_DIR
from utils.logger import log
from utils.browser import random_sleep, clean_path, get_ads_ws_url, find_or_create_page
from ui_selectors import UI_SELECTORS, RATIO_MAP, ORIENT_ICON_MAP
from utils import selector_stats
from utils import cancel_flag
from services.google_fx_dom import _click_first_visible, _find_first_visible, _safe_press_escape

_SLATE_EDITOR_SELECTOR = "[data-slate-editor='true']"


# ── _click_new_project_button ──
def _click_new_project_button(page):
    """点击 New project，兼容 add_2 图标 and 纯文本按钮。"""
    for sel in UI_SELECTORS["google_fx"].get("new_project_btn", []):
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click(force=True)
                random_sleep(3, 5)
                log(f"🆕 点击 'New project' 成功 (sel={sel!r})", "GoogleFX")
                return True
        except Exception:
            pass
    return False


# ── _find_add2_btn ──
def _find_add2_btn(page):
    """多策略定位 add_2 (Create) 按钮，返回 Locator 或 None"""
    return _find_first_visible(page, [
        "button[aria-haspopup='dialog']:has(span:text('Create'))",
        "button[aria-haspopup='dialog']:has(i.google-symbols:text('add_2'))",
        "button[aria-haspopup='dialog']:has(i:text('add_2'))",
        "button[aria-haspopup='dialog']",
        "button[aria-haspopup='menu']:has(span:text('Create'))",
        "button[aria-haspopup='menu']:has(span:text('添加媒体'))",
        "button[aria-haspopup='menu']:has(i:text('add'))",
        "button[aria-haspopup='menu']",
    ], family="fx_add2_btn")


# ── _wait_for_fx_toolbar ──
def _wait_for_fx_toolbar(page, timeout=30):
    """等待底部工具栏中的输入区出现。"""
    log("📍 等待底部工具栏...", "GoogleFX")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _find_fx_prompt_input(page, announce=False):
            log("✅ 底部工具栏已加载", "GoogleFX")
            return True
        # 随时检测是否需要人工干预（登录、滑块、安全拦截等）
        try:
            _raise_if_manual_intervention_required(page, context_label="等待工具栏中")
        except RuntimeError as e:
            if "MANUAL_REQUIRED" in str(e):
                log(f"⚠️ 等待工具栏时检测到需要人工处理: {e}", "GoogleFX")
                raise
        time.sleep(1)
    
    # 案发现场保留
    try:
        from utils.ui_helpers import handle_element_not_found
        handle_element_not_found(page, "底部工具栏输入框")
    except Exception as e:
        log(f"⚠️ 保存案发现场截图失败: {e}", "GoogleFX")
        
    raise RuntimeError("等待底部工具栏超时，未检测到可用输入框")


# ── _extract_flow_image_uuid ──
def _extract_flow_image_uuid(image_ref: str):
    """从本地路径 / URL / 纯 UUID 中提取 Flow 图片 UUID。"""
    if not image_ref:
        return None
    value = str(image_ref).strip()
    if not value:
        return None

    uuid_pattern = r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    basename = os.path.basename(value.split('?', 1)[0].split('#', 1)[0])
    basename_matches = re.findall(uuid_pattern, basename, flags=re.IGNORECASE)
    if basename_matches:
        return basename_matches[-1]

    matches = re.findall(uuid_pattern, value, flags=re.IGNORECASE)
    return matches[-1] if matches else None


# ── _get_recent_flow_image_uuids ──
def _get_recent_flow_image_uuids(page, limit=2):
    """
    获取画布里最近的一批图片 UUID。
    Flow 新图通常会被插到画布顶部，因此按视觉位置从左上到右下排序后取前几个。
    """
    cards = _get_recent_flow_image_cards(page, limit=limit)
    return [item.get("uuid") for item in cards if item.get("uuid")]


# ── _get_recent_flow_image_cards ──
def _get_recent_flow_image_cards(page, limit=2):
    """
    获取画布里最近的一批图片卡片，返回 [{tile_id, uuid, top, left, area}]。
    只保留唯一 tile，避免新版 DOM 中同一张图被重复枚举。
    limit 仅作为"最少返回"的提示——函数始终返回 JS 扫描到的全部有效卡片，
    以确保按 UUID 匹配时不会因截断而漏掉目标。
    """
    try:
        cards = page.evaluate("""() => {
            const rows = [];
            const uuidRegex = /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i;
            const seenTileIds = new Set();
            const tiles = Array.from(document.querySelectorAll('div[data-tile-id]'));
            for (const tile of tiles) {
                const tileId = tile.getAttribute('data-tile-id') || '';
                if (!tileId || seenTileIds.has(tileId)) continue;
                seenTileIds.add(tileId);
                const imgs = Array.from(tile.querySelectorAll('img'));
                const img = imgs.find((node) => {
                    const width = node.offsetWidth || node.naturalWidth || 0;
                    const height = node.offsetHeight || node.naturalHeight || 0;
                    return width > 40 && height > 40;
                });
                if (!img) continue;
                const src = img.currentSrc || img.src || '';
                const match = src.match(uuidRegex);
                if (!match) continue;
                const rect = tile.getBoundingClientRect();
                rows.push({
                    tile_id: tileId,
                    uuid: match[1],
                    top: rect.top || 0,
                    left: rect.left || 0,
                    area: (rect.width || 0) * (rect.height || 0),
                });
            }
            rows.sort((a, b) => {
                if (a.top !== b.top) return a.top - b.top;
                if (a.left !== b.left) return a.left - b.left;
                return b.area - a.area;
            });
            return rows;
        }""")
    except Exception as e:
        log(f"⚠️ 获取最新图片卡片失败: {type(e).__name__}", "GoogleFX")
        return []

    return [item for item in cards if item.get("uuid") and item.get("tile_id")]


# ── _find_tile_by_uuid_js ──
def _find_tile_by_uuid_js(page, uuid):
    """
    通过 img[src*=UUID] 在整个 DOM（含虚拟滚动区域）中精确定位卡片。
    找到后自动 scrollIntoView，返回 tile info dict 或 None。
    """
    if not uuid:
        return None
    try:
        result = page.evaluate("""(targetUuid) => {
            const imgs = Array.from(document.querySelectorAll('img[src*="' + targetUuid + '"]'));
            const big = imgs.find(i => {
                const w = i.offsetWidth || i.naturalWidth || 0;
                const h = i.offsetHeight || i.naturalHeight || 0;
                return w > 30 && h > 30;
            }) || imgs[0];
            if (!big) return null;
            const tile = big.closest('[data-tile-id]');
            if (!tile) return null;
            tile.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
            const rect = tile.getBoundingClientRect();
            return {
                tile_id: tile.getAttribute('data-tile-id') || '',
                uuid: targetUuid,
                top: rect.top || 0,
                left: rect.left || 0,
                area: (rect.width || 0) * (rect.height || 0),
            };
        }""", uuid)
        if result and result.get("tile_id"):
            log(f"  🎯 通过 img[src*=UUID] 精确定位卡片: {uuid[:16]}... (tile={result['tile_id']})", "GoogleFX")
            return result
    except Exception as e:
        log(f"  ⚠️ _find_tile_by_uuid_js 失败: {type(e).__name__}", "GoogleFX")
    return None


# ── _resolve_flow_tile_info ──
def _resolve_flow_tile_info(page, uuid: str = "", tile_id: str = ""):
    """解析目标 Flow 卡片的位置与 tile_id，供 hover / toolbar 定位复用。"""
    try:
        return page.evaluate("""({ uuid, tileId }) => {
            const tile = tileId ? document.querySelector('[data-tile-id="' + tileId + '"]') : null;
            const tileImgs = tile ? Array.from(tile.querySelectorAll('img')) : [];
            const imgs = tileImgs.length > 0
                ? tileImgs
                : Array.from(document.querySelectorAll(uuid ? 'img[src*="' + uuid + '"]' : 'img'));
            const big = imgs.find(i => (i.offsetWidth || i.naturalWidth || 0) > 50);
            const target = big || imgs[0];
            if (!target) return null;
            const resolvedTile = tile || target.closest('[data-tile-id]');
            if (!resolvedTile) return null;
            const rect = resolvedTile.getBoundingClientRect();
            if (resolvedTile.scrollIntoView) {
                resolvedTile.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
            } else if (target.scrollIntoView) {
                target.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
            }
            return {
                w: rect.width,
                h: rect.height,
                top: rect.top,
                left: rect.left,
                right: rect.right,
                bottom: rect.bottom,
                centerX: rect.left + (rect.width / 2),
                centerY: rect.top + (rect.height / 2),
                hoverX: rect.right - Math.min(Math.max(rect.width * 0.18, 42), 120),
                hoverY: rect.top + Math.min(Math.max(rect.height * 0.2, 32), 110),
                tileId: resolvedTile.getAttribute('data-tile-id') || '',
            };
        }""", {"uuid": uuid or "", "tileId": tile_id or ""})
    except Exception as e:
        log(f"⚠️ _resolve_flow_tile_info 失败: {type(e).__name__}", "GoogleFX")
        return None


# ── _hover_flow_tile_for_toolbar ──
def _hover_flow_tile_for_toolbar(page, uuid: str = "", tile_id: str = ""):
    """
    让 Flow 卡片稳定进入 hover 态。
    先尝试 Locator.hover，再补一段真实鼠标轨迹与 JS mouseenter 事件。
    """
    info = _resolve_flow_tile_info(page, uuid=uuid, tile_id=tile_id)
    if not info:
        return None

    resolved_tile_id = (info.get("tileId") or tile_id or "").strip()
    tile_scope = page.locator(f"[data-tile-id='{resolved_tile_id}']").first if resolved_tile_id else None

    try:
        if tile_scope and tile_scope.is_visible(timeout=2000):
            tile_scope.hover()
            log("  ✅ Hover 命中 tile 容器", "GoogleFX")
    except Exception:
        pass

    try:
        page.mouse.move(max(info["left"] - 20, 5), max(info["top"] - 20, 5))
        page.mouse.move(info["centerX"], info["centerY"], steps=8)
        page.mouse.move(info["hoverX"], info["hoverY"], steps=10)
        log("  ✅ 鼠标轨迹已扫过 tile 工具栏区域", "GoogleFX")
    except Exception as e:
        log(f"  ⚠️ 鼠标 hover 轨迹失败: {type(e).__name__}", "GoogleFX")

    try:
        page.evaluate("""({ tileId }) => {
            const tile = tileId ? document.querySelector('[data-tile-id="' + tileId + '"]') : null;
            if (!tile) return false;
            for (const evtName of ['mouseenter', 'mouseover', 'mousemove']) {
                tile.dispatchEvent(new MouseEvent(evtName, { bubbles: true, cancelable: true, view: window }));
            }
            const rect = tile.getBoundingClientRect();
            const hotspot = document.elementFromPoint(
                rect.right - Math.min(Math.max(rect.width * 0.18, 42), 120),
                rect.top + Math.min(Math.max(rect.height * 0.2, 32), 110),
            );
            if (hotspot) {
                for (const evtName of ['mouseenter', 'mouseover', 'mousemove']) {
                    hotspot.dispatchEvent(new MouseEvent(evtName, { bubbles: true, cancelable: true, view: window }));
                }
            }
            return true;
        }""", {"tileId": resolved_tile_id})
    except Exception:
        pass

    random_sleep(0.4, 0.7)
    return info


# ── _click_flow_more_menu ──
def _click_flow_more_menu(page, uuid: str = "", tile_id: str = "") -> str:
    """点击目标卡片右上角 more_vert 菜单，成功时返回 aria-controls 指向的菜单 id。"""
    attempts = 4
    last_tile_id = tile_id or ""

    for attempt in range(1, attempts + 1):
        info = _hover_flow_tile_for_toolbar(page, uuid=uuid, tile_id=last_tile_id)
        if not info:
            return ""

        last_tile_id = (info.get("tileId") or last_tile_id or "").strip()
        tile_scope = page.locator(f"[data-tile-id='{last_tile_id}']").first if last_tile_id else None
        more_clicked = False
        menu_id = ""
        button_id = ""
        button_timeout = 1200 + (attempt - 1) * 500
        menu_wait_ms = 250 + (attempt - 1) * 180

        scopes = []
        if tile_scope is not None:
            try:
                toolbar_scope = tile_scope.locator("[role='toolbar']").first
                scopes.append(("tile-toolbar", toolbar_scope))
            except Exception:
                pass
            scopes.append(("tile", tile_scope))

        page.wait_for_timeout(menu_wait_ms)

        for scope_name, scope in scopes:
            for more_sel in [
                "button[aria-haspopup='menu']",
                "button:has(i:text-is('more_vert'))",
                "button:has(i:text-is('more_horiz'))",
                "button:has(i:text-is('menu'))",
                "button[aria-label='More']",
                "button[aria-label='更多']",
                "button[aria-label='More options']",
                "button[aria-label*='more' i]",
                "button[aria-label*='更多']",
                "button:has(span:text-is('More'))",
                "button:has(span:text-is('更多'))",
                "button:has-text('More')",
                "button:has-text('更多')",
                "button:has-text('more_vert')",
            ]:
                try:
                    btn = scope.locator(more_sel).last
                    if btn.is_visible(timeout=button_timeout):
                        box = btn.bounding_box()
                        # 防止误触底部控制栏按钮（如模型选择、画幅选择等）
                        viewport_height = page.viewport_size.get("height", 800) if page.viewport_size else 800
                        if box and box.get("y", 0) > viewport_height - 120:
                            continue

                        menu_id = (btn.get_attribute("aria-controls") or "").strip()
                        button_id = (btn.get_attribute("id") or "").strip()
                        btn.scroll_into_view_if_needed()
                        btn.click(force=False)
                        more_clicked = True
                        page.wait_for_timeout(menu_wait_ms)
                        menu_id = _resolve_open_flow_menu_id(page, button_id=button_id, menu_id_hint=menu_id)
                        log(
                            f"  ✅ 点击 more_vert (scope={scope_name}, sel={more_sel!r}, attempt={attempt}, "
                            f"button_id={button_id or '<none>'}, menu_id={menu_id or '<none>'})",
                            "GoogleFX",
                        )
                        break
                except Exception:
                    continue
            if more_clicked:
                break

        if not more_clicked:
            try:
                js_result = page.evaluate("""({ uuid, tileId }) => {
                    const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const tile = tileId ? document.querySelector('[data-tile-id="' + tileId + '"]') : null;
                    const fallbackImg = uuid
                        ? Array.from(document.querySelectorAll('img[src*="' + uuid + '"]')).find((img) => {
                            const w = img.offsetWidth || img.naturalWidth || 0;
                            const h = img.offsetHeight || img.naturalHeight || 0;
                            return w > 40 && h > 40;
                        })
                        : null;
                    const resolvedTile = tile || (fallbackImg ? fallbackImg.closest('[data-tile-id]') : null);
                    if (!resolvedTile) return false;

                    for (const evtName of ['mouseenter', 'mouseover', 'mousemove']) {
                        resolvedTile.dispatchEvent(new MouseEvent(evtName, { bubbles: true, cancelable: true, view: window }));
                    }

                    const rect = resolvedTile.getBoundingClientRect();
                    const candidates = Array.from(document.querySelectorAll('button,[role="button"]')).filter((btn) => {
                        if (!btn || btn.offsetParent === null) return false;
                        const r = btn.getBoundingClientRect();
                        // 排除页面底部控制栏（模型/比例/提示词输入框等）
                        if (r.top > window.innerHeight - 120 || btn.closest('footer, form, [role="form"], [data-testid*="prompt"]')) return false;

                        const iconText = (btn.querySelector('i, span, svg')?.innerText || '').toLowerCase();
                        const labelText = norm([
                            btn.innerText || '',
                            btn.getAttribute('aria-label') || '',
                            btn.getAttribute('title') || '',
                            iconText
                        ].join(' '));

                        // 按钮必须属于当前 tile 容器或其关联 toolbar，或者包含明确的 more 图标/文本
                        const isInsideTile = resolvedTile.contains(btn);
                        const hasMoreText = labelText.includes('more_vert') ||
                            labelText.includes('more_horiz') ||
                            labelText === 'more' ||
                            labelText.includes('more options') ||
                            labelText.includes('更多');

                        if (!isInsideTile && !hasMoreText) return false;

                        const horizontalNear = r.right >= rect.left - 20 && r.left <= rect.right + 20;
                        const verticalNear = r.bottom >= rect.top - 20 && r.top <= rect.top + Math.max(rect.height * 0.5, 120);
                        return horizontalNear && verticalNear;
                    });
                    if (!candidates.length) return false;
                    candidates.sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        if (ar.top !== br.top) return ar.top - br.top;
                        return br.left - ar.left;
                    });
                    const target = candidates[0];
                    for (const evtName of ['mouseenter', 'mouseover', 'mousemove']) {
                        target.dispatchEvent(new MouseEvent(evtName, { bubbles: true, cancelable: true, view: window }));
                    }
                    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    return {
                        clicked: true,
                        menuId: target.getAttribute('aria-controls') || '',
                        buttonId: target.getAttribute('id') || '',
                    };
                }""", {"uuid": uuid or "", "tileId": last_tile_id or ""})
                if js_result and js_result.get("clicked"):
                    more_clicked = True
                    menu_id = (js_result.get("menuId") or "").strip()
                    button_id = (js_result.get("buttonId") or "").strip()
                    page.wait_for_timeout(menu_wait_ms)
                    menu_id = _resolve_open_flow_menu_id(page, button_id=button_id, menu_id_hint=menu_id)
                    log(
                        f"  ✅ JS fallback 点击 more_vert (attempt={attempt}, "
                        f"button_id={button_id or '<none>'}, menu_id={menu_id or '<none>'})",
                        "GoogleFX",
                    )
            except Exception as e:
                log(f"  ⚠️ more_vert JS fallback: {type(e).__name__}", "GoogleFX")

        if more_clicked:
            return menu_id

        _safe_press_escape(page, f"_click_flow_more_menu attempt={attempt} cleanup")
        page.wait_for_timeout(220 + attempt * 220)
        log(f"  ⚠️ more_vert 第 {attempt} 次尝试失败，重新 hover", "GoogleFX")

    log(f"  ❌ Add to Prompt 失败 | stage=menu_button_missing | tile_id={last_tile_id or '<none>'} | menu_id=<none>", "GoogleFX")
    return ""


# ── _get_flow_menu_debug_info ──
def _get_flow_menu_debug_info(page, menu_id_hint: str = ""):
    """抓取当前打开菜单的简要诊断信息，便于排查 Add to Prompt 偶发失败。"""
    try:
        return page.evaluate("""({ menuId }) => {
            const visible = (el) => {
                if (!el || el.offsetParent === null) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 4 && rect.height > 4;
            };
            const hinted = menuId ? document.getElementById(menuId) : null;
            const menus = Array.from(document.querySelectorAll(
                '[role="menu"][data-state="open"], [data-radix-menu-content][data-state="open"], [role="menu"]'
            )).filter(visible);
            const root = (hinted && visible(hinted)) ? hinted : (menus.length ? menus[menus.length - 1] : null);
            if (!root) {
                return {
                    menuId: menuId || '',
                    menuFound: false,
                    menuText: '',
                    hasMenuitem: false,
                    itemTexts: [],
                };
            }

            const items = Array.from(root.querySelectorAll('[role="menuitem"], button, div, span'))
                .filter(visible)
                .map((el) => ((el.innerText || '').replace(/\\s+/g, ' ').trim()))
                .filter(Boolean);

            return {
                menuId: root.id || menuId || '',
                menuFound: true,
                menuText: ((root.innerText || '').replace(/\\s+/g, ' ').trim()).slice(0, 300),
                hasMenuitem: root.querySelectorAll('[role="menuitem"]').length > 0,
                itemTexts: items.slice(0, 8),
            };
        }""", {"menuId": menu_id_hint or ""})
    except Exception as e:
        return {
            "menuId": menu_id_hint or "",
            "menuFound": False,
            "menuText": "",
            "hasMenuitem": False,
            "itemTexts": [f"debug_error:{type(e).__name__}"],
        }


# ── _resolve_open_flow_menu_id ──
def _resolve_open_flow_menu_id(page, button_id: str = "", menu_id_hint: str = "") -> str:
    """根据触发按钮与当前可见菜单，尽量反查实际打开的菜单 id。"""
    try:
        menu_id = page.evaluate("""({ buttonId, menuId }) => {
            const visible = (el) => {
                if (!el || el.offsetParent === null) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 4 && rect.height > 4;
            };
            const menus = Array.from(document.querySelectorAll(
                '[role="menu"][data-state="open"], [data-radix-menu-content][data-state="open"], [role="menu"]'
            )).filter(visible);
            if (!menus.length) return '';

            const hinted = menuId ? menus.find((menu) => menu.id === menuId) : null;
            if (hinted) return hinted.id || '';

            const trigger = buttonId ? document.getElementById(buttonId) : null;
            if (trigger) {
                const ariaControls = trigger.getAttribute('aria-controls') || '';
                if (ariaControls) {
                    const controlled = menus.find((menu) => menu.id === ariaControls);
                    if (controlled) return controlled.id || ariaControls;
                }
                const labelled = menus.find((menu) => (menu.getAttribute('aria-labelledby') || '') === buttonId);
                if (labelled) return labelled.id || '';
                const triggerRect = trigger.getBoundingClientRect();
                const nearest = menus
                    .map((menu) => {
                        const rect = menu.getBoundingClientRect();
                        const dx = rect.left - triggerRect.left;
                        const dy = rect.top - triggerRect.bottom;
                        return { menu, score: Math.abs(dx) + Math.abs(dy) };
                    })
                    .sort((a, b) => a.score - b.score)[0];
                if (nearest?.menu) return nearest.menu.id || '';
            }

            return menus[menus.length - 1]?.id || '';
        }""", {"buttonId": button_id or "", "menuId": menu_id_hint or ""})
        return (menu_id or "").strip()
    except Exception as e:
        log(f"  ⚠️ 反查打开菜单失败: {type(e).__name__}", "GoogleFX")
        return ""


# ── _click_flow_add_to_prompt ──
def _click_flow_add_to_prompt(page, menu_id_hint: str = "", tile_id_hint: str = "") -> bool:
    """点击已展开菜单中的 Add to Prompt，兼容大小写与 portal 渲染差异。"""
    add_patterns = [
        "Add to Prompt",
        "Add to prompt",
        "add to prompt",
        "添加到提示词",
        "添加到提示",
    ]

    open_menu = None
    if menu_id_hint:
        try:
            hinted = page.locator(f"[id=\"{menu_id_hint}\"]").first
            hinted.wait_for(state="visible", timeout=2500)
            open_menu = hinted
            log(f"  ✅ 已锁定打开菜单 (id={menu_id_hint})", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ menu_id 提示未命中 ({menu_id_hint}): {type(e).__name__}", "GoogleFX")

    for menu_sel in [
        "[role='menu'][data-state='open']",
        "[data-radix-menu-content][data-state='open']",
        "[role='menu']",
    ]:
        try:
            candidate = page.locator(menu_sel).last
            if candidate.is_visible(timeout=1500):
                open_menu = candidate
                log(f"  ✅ 已锁定打开菜单 (sel={menu_sel!r})", "GoogleFX")
                break
        except Exception:
            pass

    for add_sel in [
        "button[role='menuitem']:has-text('Add to Prompt')",
        "button[role='menuitemradio']:has-text('Add to Prompt')",
        "button[role='menuitemcheckbox']:has-text('Add to Prompt')",
        "[role='menuitem']:has-text('Add to Prompt')",
        "[role='menuitemradio']:has-text('Add to Prompt')",
        "[role='menuitemcheckbox']:has-text('Add to Prompt')",
        "button[role='menuitem']:has-text('Add to prompt')",
        "[role='menuitem']:has-text('Add to prompt')",
        "button[role='menuitemradio']:has-text('Add to prompt')",
        "button[role='menuitemcheckbox']:has-text('Add to prompt')",
        "button[role='menuitem']:has-text('添加到提示词')",
        "button[role='menuitemradio']:has-text('添加到提示词')",
        "button[role='menuitemcheckbox']:has-text('添加到提示词')",
        "[role='menuitem']:has-text('添加到提示词')",
        "[role='menuitemradio']:has-text('添加到提示词')",
        "[role='menuitemcheckbox']:has-text('添加到提示词')",
        "button[role='menuitem']:has-text('添加到提示')",
        "button[role='menuitemradio']:has-text('添加到提示')",
        "button[role='menuitemcheckbox']:has-text('添加到提示')",
        "[role='menuitem']:has-text('添加到提示')",
        "[role='menuitemradio']:has-text('添加到提示')",
        "[role='menuitemcheckbox']:has-text('添加到提示')",
    ]:
        try:
            scope = open_menu if open_menu is not None else page
            add_btn = scope.locator(add_sel).first
            if add_btn.is_visible(timeout=2500):
                add_btn.scroll_into_view_if_needed()
                try:
                    add_btn.click(force=False, timeout=2000)
                except Exception:
                    add_btn.click(force=True)
                log(f"  ✅ 点击 Add to Prompt (sel={add_sel!r})", "GoogleFX")
                return True
        except Exception:
            continue

    try:
        js_add_clicked = page.evaluate("""({ patterns, menuId }) => {
            const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            const visible = (el) => {
                if (!el || el.offsetParent === null) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 4 && rect.height > 4;
            };

            const hinted = menuId ? document.getElementById(menuId) : null;
            const menus = Array.from(document.querySelectorAll(
                '[role="menu"][data-state="open"], [data-radix-menu-content][data-state="open"], [role="menu"]'
            )).filter(visible);

            const roots = [];
            if (hinted && visible(hinted)) roots.push(hinted);
            if (menus.length) roots.push(...menus.reverse());
            if (!roots.length) roots.push(document.body);
            for (const root of roots) {
                // 优先查找真正的 [role="menuitem"] 或 button 交互元素
                const candidates = Array.from(root.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], button')).filter(visible);
                let target = candidates.find((item) => {
                    const text = norm(item.innerText || '');
                    const label = norm(item.getAttribute('aria-label') || '');
                    const title = norm(item.getAttribute('title') || '');
                    return patterns.some((pattern) => {
                        const p = norm(pattern);
                        return text === p || label === p || title === p || text.includes(p) || label.includes(p);
                    });
                });

                if (!target) {
                    const allItems = Array.from(root.querySelectorAll('div, span')).filter(visible);
                    const subItem = allItems.find((item) => {
                        const text = norm(item.innerText || '');
                        return patterns.some((pattern) => norm(pattern) === text);
                    });
                    if (subItem) {
                        target = subItem.closest('[role="menuitem"], button') || subItem;
                    }
                }

                if (!target) continue;
                if (typeof target.click === 'function') {
                    target.click();
                } else {
                    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                }
                return true;
            }
            return false;
        }""", {"patterns": add_patterns, "menuId": menu_id_hint or ""})
        if js_add_clicked:
            log("  ✅ JS fallback 点击 Add to Prompt", "GoogleFX")
            return True
    except Exception as e:
        log(f"  ⚠️ Add to Prompt JS fallback: {type(e).__name__}", "GoogleFX")

    debug_info = _get_flow_menu_debug_info(page, menu_id_hint=menu_id_hint)
    log(
        "  ❌ Add to Prompt 失败 | "
        f"stage=menu_item_not_found | tile_id={tile_id_hint or '<none>'} | "
        f"menu_id={debug_info.get('menuId') or menu_id_hint or '<none>'} | "
        f"menu_found={debug_info.get('menuFound')} | "
        f"has_menuitem={debug_info.get('hasMenuitem')} | "
        f"menu_text={debug_info.get('menuText')!r} | "
        f"items={debug_info.get('itemTexts')}",
        "GoogleFX",
    )
    _safe_press_escape(page, "_click_flow_add_to_prompt 关闭菜单")
    return False


# ── _mount_flow_images_to_prompt ──
def _mount_flow_images_to_prompt(page, image_refs, context_label="参考图"):
    """
    优先按传入 ref 在当前画布里命中对应卡片；命中不到时通过
    img[src*=UUID] 精确定位（含 scrollIntoView）。
    只有在「所有请求的 UUID 都已命中或通过精确定位找到」时才回退到可见卡片顺序
    （仅限单张参考图场景）。视频模式多张参考图场景下不做回退，直接返回已命中的卡片，
    避免挂载错误的图片导致顺序校验失败。
    返回成功挂载的 UUID 列表。
    """
    requested = [ref for ref in (image_refs or []) if str(ref or "").strip()]
    if not requested:
        return []

    desired_count = min(len(requested), 2)
    ordered_cards = []
    seen_tiles = set()
    visible_cards = _get_recent_flow_image_cards(page, limit=desired_count)
    cards_by_uuid = {
        item.get("uuid"): item
        for item in visible_cards
        if item.get("uuid") and item.get("tile_id")
    }
    missing_requested = []

    for ref in requested:
        uuid = _extract_flow_image_uuid(str(ref))
        matched = cards_by_uuid.get(uuid) if uuid else None
        if matched and matched.get("tile_id") not in seen_tiles:
            ordered_cards.append(matched)
            seen_tiles.add(matched.get("tile_id"))
        elif uuid:
            missing_requested.append(uuid)

    log(f"🧭 {context_label}: 画布扫描到 {len(visible_cards)} 张卡片，命中 {len(ordered_cards)} 张", "GoogleFX")

    if missing_requested:
        log(f"🔍 {context_label}: 尝试通过 img[src*=UUID] 精确定位 {len(missing_requested)} 张未命中卡片", "GoogleFX")
        still_missing = []
        for uuid in missing_requested:
            found = _find_tile_by_uuid_js(page, uuid)
            if found and found.get("tile_id") not in seen_tiles:
                ordered_cards.append(found)
                seen_tiles.add(found.get("tile_id"))
                log(f"  ✅ {context_label}: UUID {uuid[:16]}... 通过精确定位命中", "GoogleFX")
            else:
                still_missing.append(uuid)
        if still_missing:
            log(f"⚠️ {context_label}: 仍有 {len(still_missing)} 张未找到: {', '.join(u[:8] for u in still_missing[:4])}", "GoogleFX")

    if len(ordered_cards) < desired_count:
        # 🚨 不再回退到"随便一张可见卡片"：挂错图片比挂载失败更危险（会静默生成
        # 错误的首/尾帧视频而不报错）。找不到就如实报告未命中数量，让调用方按
        # mounted < expected 的既有校验逻辑走重试/失败流程。
        log(
            f"⚠️ {context_label}: 当前页未找到请求 UUID，跳过可见卡片回退 "
            f"({len(ordered_cards)}/{desired_count} 命中，避免挂错图片)",
            "GoogleFX",
        )

    mounted = []
    for idx, card in enumerate(ordered_cards[:desired_count], start=1):
        uuid = card.get("uuid") or ""
        tile_id = card.get("tile_id") or ""
        log(f"🖼️ {context_label}: 挂载第 {idx} 张卡片 ({uuid[:16]}...)", "GoogleFX")
        if not _add_flow_image_to_prompt(page, uuid, tile_id=tile_id):
            log(f"  ❌ {context_label}: Add to Prompt 失败 ({uuid[:16]}...)", "GoogleFX")
            continue
        ready, ready_sel = _wait_for_flow_reference_ready(
            page,
            timeout_seconds=15,
            settle_range=(0.5, 1.0),
        )
        if ready:
            log(f"  ✅ {context_label}: 已挂入提示词框 (sel={ready_sel!r})", "GoogleFX")
            mounted.append(uuid)
        else:
            log(f"  ⚠️ {context_label}: 挂载后未检测到就绪信号 ({uuid[:16]}...)", "GoogleFX")

    return mounted


# ── _wait_for_prompt_reference_change ──
def _wait_for_prompt_reference_change(page, previous_refs=None, expected_uuid: str = "", timeout_seconds: int = 12):
    """等待 Prompt 参考图列表发生真实变化，而不是只依赖菜单点击成功。"""
    before = [item for item in (previous_refs or []) if item]
    expected = (expected_uuid or "").strip().lower()
    before_norm = [item.lower() for item in before]
    deadline = time.time() + max(timeout_seconds, 1)

    while time.time() < deadline:
        current = _get_prompt_reference_uuids(page, limit=max(len(before) + 3, 4))
        current_norm = [item.lower() for item in current]
        if expected and expected in current_norm and current != before:
            return True, current
        if expected and expected in current_norm and expected in before_norm:
            return True, current
        if len(current) > len(before):
            return True, current
        if not expected and current != before:
            return True, current
        time.sleep(0.5)

    return False, _get_prompt_reference_uuids(page, limit=max(len(before) + 3, 4))


# ── _clear_prompt_reference_chips_video ──
# 2026-07-20: 与下方 _clear_prompt_reference_chips_image 是两份独立、行为不同的实现
# (JS dispatchEvent 单趟 vs Playwright locator + max_rounds 循环)，分别被视频/图片
# 生成流程实际调用。拆分搬移时按用户决定改名共存，不合并逻辑，避免真机行为回归。
def _clear_prompt_reference_chips_video(page):
    """清空提示词输入区已挂入的参考图，用于顺序重试。（视频生成流程使用）"""
    try:
        removed = page.evaluate("""() => {
            const isVisible = (el) => !!el && el.offsetParent !== null;
            const buttons = Array.from(document.querySelectorAll('button'))
                .filter((btn) => {
                    if (!isVisible(btn)) return false;
                    const rect = btn.getBoundingClientRect();
                    if (rect.top < window.innerHeight - 420) return false;
                    const texts = Array.from(btn.querySelectorAll('i, span'))
                        .map((node) => (node.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase());
                    const blob = ((btn.innerText || '') + ' ' + (btn.getAttribute('aria-label') || '')).toLowerCase();
                    return texts.includes('cancel') || blob.includes('remove');
                });
            for (const btn of buttons.reverse()) {
                btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            }
            return buttons.length;
        }""")
        if removed:
            log(f"🧹 已清空 {removed} 个 Prompt 参考图", "GoogleFX")
            random_sleep(0.4, 0.8)
        return removed
    except Exception as e:
        log(f"⚠️ 清空 Prompt 参考图失败: {type(e).__name__}", "GoogleFX")
        return 0


# ── _clear_existing_uploaded_frame ──
def _clear_existing_uploaded_frame(page, label: str):
    """如果 Start/End 槽位已经有上传的图片，点击其 cancel/remove 按钮将其清空，保证重新进入时精确选择。"""
    labels_to_try = {
        "Start": ["Start", "起始"],
        "End":   ["End",   "结束"],
    }.get(label, [label])
    
    try:
        cleared = page.evaluate("""(labelsToTry) => {
            const containers = Array.from(document.querySelectorAll(
                'div[type="button"][aria-haspopup="dialog"], [aria-haspopup="dialog"], .jekiem, .EGCPj'
            ));
            
            for (const container of containers) {
                const text = (container.innerText || container.textContent || '').trim();
                if (labelsToTry.includes(text)) {
                    continue;
                }
                
                const closeBtn = container.querySelector('button, i, [role="button"]');
                if (closeBtn) {
                    const btnText = (closeBtn.innerText || closeBtn.textContent || '').trim().toLowerCase();
                    const btnLabel = (closeBtn.getAttribute('aria-label') || '').toLowerCase();
                    if (btnText.includes('cancel') || btnText.includes('close') || 
                        btnLabel.includes('remove') || btnLabel.includes('clear') || btnLabel.includes('delete')) {
                        closeBtn.click();
                        return true;
                    }
                }
                
                const parent = container.parentElement;
                if (parent) {
                    const parentClose = Array.from(parent.querySelectorAll('button, i, [role="button"]')).find(el => {
                        const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                        const l = (el.getAttribute('aria-label') || '').toLowerCase();
                        return t.includes('cancel') || t.includes('close') || l.includes('remove') || l.includes('clear') || l.includes('delete');
                    });
                    if (parentClose) {
                        parentClose.click();
                        return true;
                    }
                }
            }
            return false;
        }""", labels_to_try)
        if cleared:
            log(f"🧹 检测到 {label} 帧槽位已有旧图片，已自动清空", "GoogleFX")
            random_sleep(0.6, 1.2)
            return True
    except Exception as e:
        log(f"⚠️ 清除 {label} 帧槽位图片异常: {type(e).__name__}: {e}", "GoogleFX")
    return False


def _upload_to_slot_directly(page, label: str, file_path: str) -> bool:
    """直接将本地图片上传到指定帧槽位 (Start/End)。"""
    _clear_existing_uploaded_frame(page, label)
    
    selector = 'div[type="button"][aria-haspopup="dialog"], [aria-haspopup="dialog"], .jekiem, .EGCPj'
    containers = page.locator(selector)
    count = containers.count()
    
    target_container = None
    labels_to_try = {
        "Start": ["Start", "起始"],
        "End":   ["End",   "结束"],
    }.get(label, [label])
    
    for i in range(count):
        el = containers.nth(i)
        try:
            txt = el.inner_text().strip()
            if any(lbl in txt for lbl in labels_to_try):
                target_container = el
                break
        except Exception:
            pass
            
    if not target_container:
        log(f"  ❌ 未找到 {label} 帧槽位容器", "GoogleFX")
        return False
        
    try:
        target_container.click(force=True)
        random_sleep(1.0, 1.5)
    except Exception as e:
        log(f"  ❌ 点击 {label} 帧槽位容器失败: {e}", "GoogleFX")
        return False
        
    try:
        upload_menu_item = page.locator("button[role='menuitem']:has-text('上传'), button[role='menuitem']:has-text('Upload')").first
        if upload_menu_item.is_visible(timeout=1500):
            upload_menu_item.click(force=True)
            random_sleep(0.8, 1.2)
    except Exception:
        pass
        
    try:
        file_input = page.locator("input[type='file']").first
        if not file_input or file_input.count() == 0:
            log(f"  ❌ 未找到 {label} 上传对应的 file input", "GoogleFX")
            return False
        abs_path = os.path.abspath(file_path)
        file_input.set_input_files(abs_path)
        log(f"  ✅ {label} 槽位已设置输入文件: {os.path.basename(file_path)}", "GoogleFX")
        random_sleep(4.0, 6.0)  # 等待上传并就绪
        return True
    except Exception as e:
        log(f"  ❌ {label} 槽位上传文件异常: {e}", "GoogleFX")
        return False


# ── _mount_video_prompt_refs ──
def _mount_video_prompt_refs(page, start_ref: str = "", end_ref: str = "", start_path: str = "", end_path: str = ""):
    """
    视频参考图的语义顺序固定为 Start -> End。
    Flow 当前 UI 保持插入顺序（先添加的在前），因此直接按语义顺序
    (Start→End) 挂载即可。仅在首选策略失败时才回退到反序尝试。
    """
    _clear_prompt_reference_chips_video(page)

    semantic_refs = [ref for ref in [start_ref, end_ref] if str(ref or "").strip()]
    expected_uuids = [_extract_flow_image_uuid(ref) for ref in semantic_refs if _extract_flow_image_uuid(ref)]
    if not semantic_refs:
        return []

    attempts = []
    if len(semantic_refs) == 2:
        attempts.append(("semantic_order", semantic_refs))
        reverse_refs = [ref for ref in [end_ref, start_ref] if str(ref or "").strip()]
        if reverse_refs != semantic_refs:
            attempts.append(("reverse_fallback", reverse_refs))
    else:
        attempts.append(("single_ref", semantic_refs))

    last_actual = []
    last_mounted = []
    for idx, (strategy_name, refs_to_mount) in enumerate(attempts, start=1):
        if idx > 1:
            _clear_prompt_reference_chips_video(page)

        log(f"🧭 视频参考图挂载策略: {strategy_name}", "GoogleFX")
        mounted = _mount_flow_images_to_prompt(
            page,
            refs_to_mount,
            context_label=f"视频参考卡片[{strategy_name}]",
        )
        actual_order = _get_prompt_reference_uuids(page, limit=len(expected_uuids) or 1)
        last_actual = actual_order
        last_mounted = mounted

        log(
            f"🧭 视频参考图顺序校验 | expected={expected_uuids} | actual={actual_order}",
            "GoogleFX",
        )

        if len(expected_uuids) == 1:
            if actual_order[:1] == expected_uuids[:1]:
                return mounted
        elif actual_order[:len(expected_uuids)] == expected_uuids:
            return mounted

    log(
        f"⚠️ 视频参考图顺序校验失败，尝试通过直接上传到 Start/End 槽位进行挂载... | expected={expected_uuids} | actual={last_actual} | mounted={last_mounted}",
        "GoogleFX",
    )
    _clear_prompt_reference_chips_video(page)
    
    slot_mounted = []
    if start_path and os.path.exists(start_path):
        ok1 = _upload_to_slot_directly(page, "Start", start_path)
        if ok1:
            slot_mounted.append(_extract_flow_image_uuid(start_ref) or "start_uploaded")
            
    if end_path and os.path.exists(end_path):
        ok2 = _upload_to_slot_directly(page, "End", end_path)
        if ok2:
            slot_mounted.append(_extract_flow_image_uuid(end_ref) or "end_uploaded")
            
    if slot_mounted:
        log(f"✅ 槽位直接上传成功: {slot_mounted}", "GoogleFX")
        return slot_mounted

    return []


# ── _upload_image_to_canvas_and_mount ──
def _upload_image_to_canvas_and_mount(page, local_path: str, timeout: int = 60) -> bool:
    """
    回退策略：当画布上找不到参考图 UUID 时（如页面刷新后画布清空），
    通过 Create (add_2) → Upload 按钮将本地图片上传到画布，
    等待新图出现后自动 Add to Prompt。
    返回 True 表示成功挂载，False 表示失败。
    """
    if not local_path or not os.path.exists(local_path):
        log(f"  ❌ 上传回退: 文件不存在 {local_path}", "GoogleFX")
        return False

    log(f"🔄 参考图回退: 通过上传方式挂载 {os.path.basename(local_path)}", "GoogleFX")

    known_uuids = _get_panel_uuids(page)

    add2_btn = _find_add2_btn(page)
    if not add2_btn:
        log("  ❌ 上传回退: 未找到 Create (add_2) 按钮", "GoogleFX")
        return False

    try:
        add2_btn.click()
        random_sleep(1.0, 1.5)
        log("  ✅ 已点击 Create 按钮", "GoogleFX")
    except Exception as e:
        log(f"  ❌ 上传回退: 点击 Create 失败: {e}", "GoogleFX")
        return False

    uploaded = False
    try:
        upload_sels = [
            "button:has-text('Upload')", "button:has-text('上传')",
            "[role='button']:has-text('Upload')", "[role='button']:has-text('上传')",
            "div[class*='upload']", "label:has-text('Upload')",
            "button[aria-label*='Upload']", "button[aria-label*='上传']",
            "button[role='menuitem']:has-text('上传')",
            "button[role='menuitem']:has-text('Upload')",
        ]
        for _up_sel in upload_sels:
            try:
                _matches = page.locator(_up_sel)
                for _idx in range(_matches.count()):
                    _el = _matches.nth(_idx)
                    if _el.is_visible(timeout=2000):
                        _el.click(force=True)
                        log(f"  ✅ 已点击 Upload 触发区域 ({_up_sel!r})", "GoogleFX")
                        random_sleep(0.8, 1.5)
                        break
                else:
                    continue
                break
            except Exception:
                continue

        file_input = None
        for _fi_sel in ["input[type='file']", "input[accept*='image']"]:
            try:
                _fi = page.locator(_fi_sel).first
                if _fi.count() > 0:
                    file_input = _fi
                    break
            except Exception:
                pass

        if file_input:
            abs_path = os.path.abspath(local_path)
            file_input.set_input_files(abs_path)
            log(f"  ✅ set_input_files: {os.path.basename(abs_path)}", "GoogleFX")
            uploaded = True
        else:
            log("  ❌ 上传回退: 未找到 file input", "GoogleFX")
            _safe_press_escape(page, "上传回退 file input 未找到")
            return False

    except Exception as e:
        log(f"  ❌ 上传回退: 上传操作失败: {e}", "GoogleFX")
        _safe_press_escape(page, "上传回退异常")
        return False

    if not uploaded:
        _safe_press_escape(page, "上传回退未完成")
        return False

    log("  ⏳ 等待上传图片出现在画布...", "GoogleFX")
    new_uuid = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        cur_uuids = _get_panel_uuids(page)
        new_uuids = cur_uuids - known_uuids
        if new_uuids:
            new_uuid = next(iter(new_uuids))
            log(f"  🎉 上传图片已出现: UUID={new_uuid[:16]}...", "GoogleFX")
            break
        time.sleep(2)

    if not new_uuid:
        log("  ❌ 上传回退: 等待超时，未检测到新图", "GoogleFX")
        _safe_press_escape(page, "上传回退超时")
        return False

    _safe_press_escape(page, "上传回退关闭对话框")
    random_sleep(0.5, 1.0)

    _ok = _add_flow_image_to_prompt(page, new_uuid)
    if _ok:
        log(f"  ✅ 上传回退成功: 参考图已挂入 Prompt (UUID={new_uuid[:16]}...)", "GoogleFX")
        return True
    else:
        log(f"  ❌ 上传回退: 图片已上传到画布但 Add to Prompt 失败", "GoogleFX")
        return False


# ── 提示词区分性切片 ──
def _clean_alnum(text):
    return re.sub(r'[^a-zA-Z0-9]', '', text or '').lower()


def _distinct_slices(prompts_map, slice_len=60):
    """为每个 tid 计算能区分彼此的提示词切片 {tid: slice}。

    🚨 2026-07-04 复盘根因：SPARK 所有视频段提示词都以同一段 boilerplate 开头
    （"Use the provided first frame and last frame as exact composition anchors..."），
    前 60 个字母数字字符完全相同。旧逻辑用"前 60 字符"做 tile 兜底匹配，等于所有
    任务都匹配同一批 tile —— 实测导致跨槽位甚至跨任务串片（loft 任务 vid_008 下载
    到了铁路隧道视频）。这里改为：去掉所有提示词的公共前缀后再取切片，保证切片
    只包含该段特有的内容（镜头/动作描述）。
    """
    if not prompts_map:
        return {}
    cleaned = {tid: _clean_alnum(p) for tid, p in prompts_map.items()}
    values = [v for v in cleaned.values() if v]
    if not values:
        return {tid: '' for tid in prompts_map}
    if len(values) >= 2:
        prefix_len = len(os.path.commonprefix(values))
    else:
        prefix_len = 0
    slices = {}
    for tid, v in cleaned.items():
        s = v[prefix_len:prefix_len + slice_len]
        if len(s) < 20:  # 公共前缀吃掉太多（或提示词过短）时回退到全文前缀
            s = v[:slice_len]
        slices[tid] = s
    return slices


# ── _inspect_all_pending_tiles ──
def _inspect_all_pending_tiles(page, tile_ids, prompts_map=None, slices_map=None):
    """批量扫描指定 tile_id 列表的生成状态，返回 {tile_id: {status, videoSrc, ...}}。

    slices_map: {tile_id: 区分性切片}。批量流程应传入基于全批次提示词计算的切片；
    不传时退化为按 prompts_map 内部对比计算（条目少时区分度有限）。
    """
    if not tile_ids:
        return {}
    if slices_map is None:
        slices_map = _distinct_slices(prompts_map or {})
    return page.evaluate("""([tileIds, slicesMap]) => {
        const results = {};
        const claimed = new Set();
        for (const tid of tileIds) {
            let tile = document.querySelector(`div[data-original-tile-id="${tid}"]`) ||
                       document.querySelector(`div[data-tile-id="${tid}"]`);

            if (!tile && slicesMap && slicesMap[tid]) {
                const cleanPrompt = slicesMap[tid];
                if (cleanPrompt) {
                    const allTiles = document.querySelectorAll('div[data-tile-id]');
                    for (const el of allTiles) {
                        // 不抢占已归属其他任务的 tile（同一次扫描或此前已被标记）
                        const stamped = el.getAttribute('data-original-tile-id');
                        if (stamped && stamped !== tid) continue;
                        const domId = el.getAttribute('data-tile-id');
                        if (claimed.has(domId)) continue;
                        const tileText = (el.innerText || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
                        if (tileText.includes(cleanPrompt)) {
                            tile = el;
                            tile.setAttribute('data-original-tile-id', tid);
                            break;
                        }
                    }
                }
            }
            if (tile) claimed.add(tile.getAttribute('data-tile-id'));

            if (!tile) { results[tid] = {status:'missing',videoSrc:null,progress:null,failedText:null}; continue; }
            const text = (tile.innerText || '').toLowerCase();
            const videoEl = tile.querySelector('video');
            const sourceEl = videoEl ? videoEl.querySelector('source') : null;
            const videoSrc = (videoEl && (videoEl.currentSrc || videoEl.src)) || (sourceEl && sourceEl.src) || '';
            const thumbEl = tile.querySelector('img[alt="Video thumbnail"], img[alt="视频缩略图"]');
            const thumbSrc = thumbEl ? (thumbEl.currentSrc || thumbEl.src || '') : '';
            const progressMatch = (tile.innerText || '').match(/(\\d{1,3})\\s*%/);
            const hasProgress = progressMatch !== null;
            const hasFailText = text.includes('failed') || text.includes('something went wrong')
                             || text.includes('unusual activity') || text.includes('help center')
                             || text.includes('出错了') || text.includes('生成失败')
                             || text.includes('失败') || text.includes('使用人数过多');
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
                const t = (i.innerText || i.textContent || '').trim().toLowerCase();
                const isWarning = t === 'warning' || t === 'error' || t === 'error_outline';
                return isWarning && isVisible(i);
            });
            const failed = hasFailText && hasWarningIcon;
            // 🔧 2026-07-04: 收紧 IP 封禁判定。'help center'/'帮助中心' 是 Flow 所有失败
            // 卡片都会带的通用链接，此前把它算作 IP 被封的证据，导致普通生成失败也被
            // 当成封 IP → 整批中止 + 换 IP 重跑 → 大量重复提交。只认 unusual activity。
            const isIpBlocked = failed && (
                text.includes('unusual activity') || text.includes('异常活动')
            );
            let status;
            if (videoSrc) {
                status = 'done';
            } else if (hasProgress || thumbSrc) {
                status = 'generating';
            } else if (failed) {
                status = 'failed';
            } else {
                status = 'generating';
            }
            results[tid] = {
                status: status,
                videoSrc: videoSrc || null,
                progress: (progressMatch ? Number(progressMatch[1]) : null),
                failedText: (status === 'failed') ? (tile.innerText || '') : null,
                isIpBlocked: isIpBlocked,
            };
        }
        return results;
    }""", [tile_ids, slices_map])


# ── _scan_canvas_tiles ──
def _scan_canvas_tiles(page):
    """扫描画布上全部 tile，按文档顺序返回
    [{tileId, originalTileId, textClean, videoSrc, failed}]。
    用于换 IP 重试后认领此前已提交且已生成完成的任务，避免重复提交。"""
    try:
        return page.evaluate(r"""() => {
            return Array.from(document.querySelectorAll('div[data-tile-id]')).map(el => {
                const videoEl = el.querySelector('video');
                const sourceEl = videoEl ? videoEl.querySelector('source') : null;
                const videoSrc = (videoEl && (videoEl.currentSrc || videoEl.src)) || (sourceEl && sourceEl.src) || '';
                const text = (el.innerText || '');
                const lower = text.toLowerCase();
                const failed = lower.includes('failed') || lower.includes('something went wrong')
                            || lower.includes('unusual activity') || lower.includes('生成失败')
                            || lower.includes('异常活动');
                return {
                    tileId: el.getAttribute('data-tile-id'),
                    originalTileId: el.getAttribute('data-original-tile-id') || null,
                    textClean: text.replace(/[^a-zA-Z0-9]/g, '').toLowerCase(),
                    videoSrc: videoSrc || null,
                    failed: failed,
                };
            });
        }""")
    except Exception as e:
        log(f"⚠️ _scan_canvas_tiles 失败: {type(e).__name__}: {e}", "GoogleFX")
        return []


# ── _wait_for_new_tile_id ──
def _wait_for_new_tile_id(page, before_tile_ids, timeout=20, expect_slice=None):
    """Generate 后等待画布出现新 data-tile-id，返回该 ID；超时返回 None。

    expect_slice: 该任务提示词的区分性切片（见 _distinct_slices）。提供时优先返回
    文本包含该切片的新 tile —— 防止同时出现多个新 tile（React 重渲染旧卡片换 id 等）
    时随手拿了别的任务的卡片（2026-07-04 复盘中 vid_009/010 内容整体错位的可疑机制）。
    """
    deadline = time.time() + timeout
    before_set = set(before_tile_ids or [])
    fallback_id = None
    while time.time() < deadline:
        tiles = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('div[data-tile-id]')).map(el => ({
                id: el.getAttribute('data-original-tile-id') || el.getAttribute('data-tile-id'),
                textClean: (el.innerText || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase(),
            }));
        }""")
        new_tiles = [t for t in tiles if t['id'] and t['id'] not in before_set]
        if new_tiles:
            if expect_slice:
                matched = [t for t in new_tiles if expect_slice in t['textClean']]
                if matched:
                    return matched[-1]['id']
                # 暂未匹配到文本（tile 可能尚未渲染提示词），记下候选继续等
                fallback_id = new_tiles[-1]['id']
            else:
                return new_tiles[-1]['id']
        time.sleep(0.5)
    if fallback_id:
        log(f"⚠️ 新 tile 文本未匹配到提示词切片，回退使用最新 tile {fallback_id[:16]}...", "GoogleFX")
    return fallback_id


# ── _fill_prompt_text ──
def _fill_prompt_text(page, input_el, prompt, has_refs=False):
    """向提示词输入框写入文本（复用 _generate_video_google_fx 中的多策略逻辑）。返回 True 表示成功。"""
    filled = False

    if has_refs:
        for attempt_label, fn in [
            ("insert_text", lambda: (
                input_el.click(), random_sleep(0.2, 0.3),
                page.keyboard.press("End"), random_sleep(0.1, 0.2),
                page.keyboard.insert_text(prompt), random_sleep(0.3, 0.5),
            )),
            ("execCommand", lambda: (
                input_el.click(), random_sleep(0.2, 0.3),
                page.evaluate("""(text) => {
                    const ed = document.querySelector('[data-slate-editor="true"]');
                    if (!ed) return; ed.focus();
                    const s = window.getSelection();
                    if (s && s.rangeCount) s.getRangeAt(0).collapse(false);
                    document.execCommand('insertText', false, text);
                }""", prompt), random_sleep(0.3, 0.5),
            )),
        ]:
            if filled:
                break
            try:
                fn()
                editor_text = input_el.inner_text().strip()
                if prompt[:15].lower() in editor_text.lower():
                    filled = True
                    log(f"✅ {attempt_label} 追加提示词成功: {len(prompt)} 字符", "GoogleFX")
            except Exception as e:
                log(f"⚠️ {attempt_label} 追加提示词失败: {e}", "GoogleFX")
    else:
        try:
            input_el.click()
            random_sleep(0.3, 0.5)
            page.keyboard.press("ControlOrMeta+a")
            random_sleep(0.1, 0.2)
            page.keyboard.press("Backspace")
            random_sleep(0.2, 0.3)
            page.evaluate("""(text) => {
                const ed = document.querySelector('[data-slate-editor="true"]');
                if (ed) { ed.focus(); ed.dispatchEvent(new InputEvent('beforeinput',
                    {inputType:'insertText',data:text,bubbles:true,cancelable:true,composed:true})); }
            }""", prompt)
            random_sleep(0.5, 0.8)
            slate_text = page.evaluate("""() => {
                const ed = document.querySelector('[data-slate-editor="true"]');
                return ed ? ed.textContent.trim() : '';
            }""")
            if slate_text and prompt[:15] in slate_text:
                filled = True
                log(f"✅ Slate insertText 成功: {len(prompt)} 字符", "GoogleFX")
        except Exception as e:
            log(f"⚠️ Slate insertText 失败: {e}", "GoogleFX")

        if not filled:
            try:
                input_el.click()
                random_sleep(0.2, 0.3)
                page.keyboard.press("ControlOrMeta+a")
                page.keyboard.press("Backspace")
                random_sleep(0.2, 0.3)
                page.keyboard.type(prompt, delay=20)
                filled = True
                log(f"✅ keyboard.type() 成功: {len(prompt)} 字符", "GoogleFX")
            except Exception as e:
                log(f"⚠️ keyboard.type() 失败: {e}", "GoogleFX")

        if not filled:
            try:
                input_el.click()
                random_sleep(0.2, 0.3)
                page.evaluate("""(t) => { navigator.clipboard.writeText(t); }""", prompt)
                page.keyboard.press("ControlOrMeta+v")
                random_sleep(0.5, 1.0)
                filled = True
                log(f"✅ 剪贴板粘贴尝试完成", "GoogleFX")
            except Exception as e:
                log(f"⚠️ 剪贴板粘贴失败: {e}", "GoogleFX")

    return filled


# ── _submit_video_to_canvas ──
def _submit_video_to_canvas(page, req, before_tile_ids, expect_slice=None):
    """
    在画布上提交一个视频生成任务（不等待完成）。
    流程: 清理旧 chips → 挂载首尾帧 → 写提示词 → Generate → 等新 tile 出现
    返回 {"tile_id": str, "click_time": float}。
    挂载失败时抛 RuntimeError("CANVAS_MOUNT_FAILED:...")。
    expect_slice: 该任务提示词的区分性切片，用于核对新 tile 归属。
    """
    img_path = clean_path(req.image) if req.image else ""
    end_img_path = clean_path(req.end_image) if (hasattr(req, "end_image") and req.end_image) else ""
    has_start = bool(img_path)
    has_end = bool(end_img_path)

    log(f"📤 提交任务: {req.prompt[:40]}... | 首帧={has_start} | 尾帧={has_end}", "GoogleFX")

    try:
        page.wait_for_timeout(500)
        # 🚨 之前这里用 page.locator('button:has(i:has-text("close"))') 无范围限制地扫描
        # 整个页面并点击——批量模式下，之前提交的任务此时可能仍在画布卡片(data-tile-id)里
        # 生成中，而 Flow 的"停止/取消生成"按钮同样用了 close 图标。结果是：提交第 2/3/4/5
        # 个任务时，会误点到还在生成中的前一个任务卡片的取消按钮，导致那个视频被我们自己的
        # 脚本悄悄取消掉——但 Flow 后端有时仍会把它生成完，只是前端要手动刷新一次才会同步，
        # 而 SPARK 这边早已按失败/超时处理并跳过了该视频。这里明确排除任何
        # [data-tile-id] 画布卡片内部的按钮，只清理提示词/工具栏区域残留的弹窗按钮。
        closed_count = page.evaluate("""() => {
            const isVisible = (el) => !!el && el.offsetParent !== null;
            const inCanvasTile = (el) => !!el.closest('div[data-tile-id]');
            const buttons = Array.from(document.querySelectorAll('button')).filter((btn) => {
                if (!isVisible(btn)) return false;
                if (inCanvasTile(btn)) return false;
                const icons = Array.from(btn.querySelectorAll('i'))
                    .map((i) => (i.textContent || '').trim().toLowerCase());
                return icons.includes('close');
            });
            for (const btn of buttons) {
                btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            }
            return buttons.length;
        }""")
        if closed_count:
            log(f"🧹 已关闭 {closed_count} 个残留弹窗（已排除画布卡片，避免误取消生成中任务）", "GoogleFX")
            random_sleep(0.3, 0.5)
    except Exception:
        pass
    _clear_prompt_reference_chips_video(page)
    random_sleep(0.3, 0.5)

    prompt_has_refs = False
    if has_start or has_end:
        start_ref = req.image or img_path if has_start else ""
        end_ref = req.end_image or end_img_path if has_end else ""
        
        # 🔧 2026-07-03: 提取本地图片真实路径，以备在画布未命中时回退到直接对槽位进行文件上传
        start_local = ""
        end_local = ""
        
        def _is_local_path(val):
            if not val:
                return False
            val_str = str(val).strip()
            return os.path.exists(val_str) or "\\" in val_str or "/" in val_str or ":" in val_str

        if _is_local_path(start_ref):
            start_local = start_ref
        elif hasattr(req, "original_image") and req.original_image:
            start_local = req.original_image
            
        if _is_local_path(end_ref):
            end_local = end_ref
        elif hasattr(req, "original_end_image") and req.original_end_image:
            end_local = req.original_end_image

        mounted = _mount_video_prompt_refs(
            page,
            start_ref=start_ref,
            end_ref=end_ref,
            start_path=start_local,
            end_path=end_local
        )
        expected = min(len([r for r in [start_ref, end_ref] if str(r or "").strip()]), 2)
        prompt_has_refs = expected > 0 and len(mounted) >= expected
        if not prompt_has_refs:
            raise RuntimeError(f"CANVAS_MOUNT_FAILED:画布卡片挂载失败 ({len(mounted)}/{expected})")
        log(f"✅ 参考卡片挂载完成 ({len(mounted)}/{expected})", "GoogleFX")

    input_el = _find_fx_prompt_input(page, announce=False)
    if not input_el:
        raise RuntimeError("无法找到视频提示词输入框")
    if not _fill_prompt_text(page, input_el, req.prompt, has_refs=prompt_has_refs):
        raise RuntimeError("视频提示词输入失败")
    random_sleep(0.5, 1.0)

    try:
        input_el.click()
        random_sleep(0.1, 0.2)
        page.keyboard.press("End")
        if prompt_has_refs:
            page.keyboard.type(" ")
            random_sleep(0.15, 0.25)
        else:
            page.keyboard.type(" ")
            random_sleep(0.1, 0.15)
            page.keyboard.press("Backspace")
            random_sleep(0.2, 0.3)
    except Exception as e:
        log(f"⚠️ React state 同步失败: {type(e).__name__}", "GoogleFX")

    click_time = time.time()
    click_fx_send_button(page, input_el)
    log("✅ 已点击 Generate", "GoogleFX")

    new_tile_id = _wait_for_new_tile_id(page, before_tile_ids, timeout=20, expect_slice=expect_slice)
    if not new_tile_id:
        raise RuntimeError("Generate 后未检测到新 tile")
    log(f"🎯 新 tile: {new_tile_id[:16]}...", "GoogleFX")
    
    # 立即为新 tile 设置 data-original-tile-id，防止后续生成过程中 React/UI 更新其 ID 后丢失匹配
    try:
        page.evaluate(f"""(feId) => {{
            const el = document.querySelector(`div[data-tile-id="${{feId}}"]`);
            if (el) {{
                el.setAttribute('data-original-tile-id', feId);
            }}
        }}""", new_tile_id)
    except Exception as e:
        log(f"⚠️ 为新 tile 设置 data-original-tile-id 失败: {e}", "GoogleFX")

    return {"tile_id": new_tile_id, "click_time": click_time}


# ==============================================================================
# 🔒 Google FX 配置面板锁定簇 (find_fx_config_button / check_fx_config / fix_fx_config)
# — 2026-03-25 LOCKED，由 services/google_fx.py 整体搬移至此，函数体逐字未改动。
# 锁定范围: find_fx_config_button / check_fx_config / fix_fx_config
# ==============================================================================

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
            aliases.update({"veo 3 1 lite", "veo lite"})
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
    for tab_idx, (selector, exact) in enumerate(patterns):
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
                selector_stats.record_hit("fx_tab", tab_idx, selector=selector, total=len(patterns))
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
    selector_stats.record_hit("fx_tab", -1, total=len(patterns))
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

    fallback_selectors = UI_SELECTORS["google_fx"].get("config_panel_root", [])
    total_layers = 2 + len(fallback_selectors)

    if button_id:
        try:
            panel = page.locator(
                f"[role='menu'][data-state='open'][aria-labelledby='{button_id}']"
            ).first
            if panel.is_visible(timeout=1500):
                selector_stats.record_hit("fx_config_panel", 0, selector="aria-labelledby", total=total_layers)
                return panel
        except Exception:
            pass

    if aria_controls:
        try:
            panel = page.locator(f"[id=\"{aria_controls}\"]").first
            if panel.is_visible(timeout=1500):
                selector_stats.record_hit("fx_config_panel", 1, selector="aria-controls", total=total_layers)
                return panel
        except Exception:
            pass

    for layer_idx, sel in enumerate(fallback_selectors):
        try:
            panel = page.locator(sel).first
            if panel.is_visible(timeout=1500):
                selector_stats.record_hit("fx_config_panel", 2 + layer_idx, selector=sel, total=total_layers)
                return panel
        except Exception:
            pass

    selector_stats.record_hit("fx_config_panel", -1, total=total_layers)
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
                    selector_stats.record_hit("fx_model_dropdown", 0, selector="button[aria-haspopup='menu']", total=2)
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
                    selector_stats.record_hit("fx_model_dropdown", 1, selector=sel, total=2)
                    return btn
        except Exception:
            pass
    selector_stats.record_hit("fx_model_dropdown", -1, total=2)
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
    ], timeout=1200, force=True, family="fx_menu_item")
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
        ], force=True, family="fx_orientation_option")
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

    # 2026-07-19 复盘：模型切换必须先于时长 tab 检测——4s/6s/8s/10s 这几个时长
    # tab 只有 Omni Flash 的视频面板才会渲染，Veo 系列面板压根没有这个控件（见本文件
    # 顶部 _VALID_VIDEO_DURATIONS 旁的说明）。之前的顺序是先找时长 tab、模型切换放最后，
    # 于是当面板当时还停留在上一次任务用过的 Veo/Nano Banana 配置上时，
    # _click_video_duration_tab 必然找不到任何时长 tab（面板此刻还没切到 Omni Flash），
    # 拿到的 duration 检测结果永远是"未确认"，_verify_and_fix_fx_config 随即把它计入
    # unconfirmed 并抛出"配置未完成，停止生成"，致命错误直接打断整个批次——实测复现
    # 于画布参考图刚上传完成、紧接着提交第一段视频任务时（server.log 19:43:49）。
    # 把模型切换挪到时长检测之前，让面板先落到目标模型（Omni Flash）上，时长 tab 才有
    # 机会真正出现在 DOM 里。
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
                    if _click_fx_menu_item(page, model, button_id_hint=model_btn_id):
                        log(f"  ✅ {model} 已选择 (full match)", "GoogleFX")
                        selected = True
                        fix_info["clicked_keys"].append("model")
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

    # 关闭面板: 先按 Escape，再等待面板收起
    try:
        page.keyboard.press("Escape")
    except Exception as e:
        log(f"  ⚠️ fix_fx_config 关闭面板 Escape 失败: {type(e).__name__}", "GoogleFX")
    random_sleep(1.5, 2.5)  # 等待底部工具栏状态按钮恢复显示正确内容
    return fix_info


# ==============================================================================
# 🔧 FX 配置校验/修复的调用入口 + 模型名规范化 (原 services/google_fx.py，函数体逐字未改动)
# ==============================================================================

def _normalize_ratio_value(ratio):
    """将用户传入的 ratio 规范化：去空格 + 小写 (以便 RATIO_MAP 查表)。"""
    value = (ratio or "").strip()
    if not value:
        return None
    return value.lower()

_VALID_IMAGE_MODELS = ["Nano Banana Pro", "Nano Banana 2", "Imagen 4"]

_VALID_VIDEO_MODELS = [
    "Veo 3.1 - Lite",
    "Veo 3.1 - Fast",
    "Veo 3.1 - Quality",
    "Omni Flash",
    "Veo 3.1 - Lite [Lower Priority]",
]

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


# ==============================================================================
# 🔁 Loop-1 payload — 原分散在 google_fx.py，是 helpers.py 里 8 处函数体内
# lazy import 唯一需要回指的 7 个名字。搬到同一文件后那些 lazy import 全部改为
# 普通同文件调用 (函数体逐字未改动)。
# ==============================================================================

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
                        # 查找精准候选按钮（只匹配明确的 Add to prompt / 添加到提示词，防止误触页面其他 Add 按钮）
                        for direct_sel in [
                            "button[aria-label='Add to prompt' i]",
                            "button[title='Add to prompt' i]",
                            "button[aria-label='Add to Prompt']",
                            "button[title='Add to Prompt']",
                            "button[aria-label='添加到提示词']",
                            "button[title='添加到提示词']",
                            "button:has-text('Add to prompt')",
                            "button:has-text('Add to Prompt')",
                            "button:has-text('添加到提示词')",
                        ]:
                            btn = toolbar.locator(direct_sel).first
                            if btn.is_visible(timeout=500):
                                btn.click(force=False)
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
# 🌐 页面连接 + 画布/卡片维护 (原 services/google_fx.py，函数体逐字未改动)
# ==============================================================================

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
        # 2026-07-19 复盘：这里曾经是唯一一处不带 try/except 的 Flow 导航——
        # google_fx_video.py 的 _prepare_page 里两处同款 page.goto 都用
        # try/except 包住只记警告不重新抛出（页面偶发慢一点，_wait_toolbar_ready
        # 的等待+刷新重试足够自愈），唯独这里裸调用。一次 60s 导航超时（网络
        # 抖动/Google 页面偶发缓慢）就会顺着 _run_round 的 with 块一路冒到
        # run() 的通用 except，被记成"批量生成过程发生致命错误"直接放弃
        # ——整个 chunk（最多 5 段视频）连一次重试机会都没有就全部判失败。
        try:
            page.goto("https://labs.google/fx/tools/flow", timeout=60000)
            random_sleep(1, 2)
        except Exception as nav_err:
            log(f"⚠️ 导航到 Flow 首页超时/失败: {type(nav_err).__name__}: {nav_err}，继续尝试后续步骤...", "GoogleFX")

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
            try:
                page.goto("https://labs.google/fx/tools/flow", timeout=60000)
                random_sleep(2, 4)
            except Exception as nav_err:
                log(f"⚠️ 换 IP 后导航到 Flow 首页超时/失败: {type(nav_err).__name__}: {nav_err}，继续尝试后续步骤...", "GoogleFX")
            # 再次检测，如果仍然被拦截则抛出异常
            _raise_if_manual_intervention_required(page, context_label="Google FX 换 IP 后重试")
        else:
            raise

    return browser, page

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

def _clear_prompt_reference_chips_image(page, max_rounds=6):
    """（图片生成流程使用；见上方 _clear_prompt_reference_chips_video 的改名说明）

    生成开始前，主动清掉输入区已挂载的历史参考图 chip。
    Ctrl+A/Backspace 只能清空 Slate 编辑器内的文本和内联 chip，
    对渲染在编辑器之外（底部工具栏"素材槽"，button[data-card-open] 形式）
    的参考图 chip 不生效，必须单独找到其 remove/cancel/close 控件点掉，
    否则上一次生成残留的参考图会带入下一次请求。

    2026-07-20: 原来把 close_history_btn（button:has(i:has-text('close')) 等，
    page-wide 无范围限制）当主策略，用 page.locator(sel).first 逐轮找「页面上
    第一个匹配的 close 按钮」再点——不限定在底部素材槽区域内，一旦页面上同时有
    别的无关 close/关闭按钮可见（弹窗、提示条等）就会点到不该点的元素上，
    且要逐个点击 + 每次等待，跑满 max_rounds 轮才收尾，耗时也偏长。改为优先走
    范围限定的 JS 批量扫描（只认 button[data-card-open] 内、且渲染在底部输入区
    附近的 cancel/close 图标），一次 evaluate 里把所有匹配项一并点掉；
    找不到任何素材槽 chip 时才回退到旧的 close_history_btn 逐个点击，
    覆盖 JS 选择器覆盖不到的 UI 变体。
    """
    removed_total = 0
    try:
        bulk_removed = page.evaluate("""() => {
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
            const icons = Array.from(document.querySelectorAll("button[data-card-open] i"));
            let count = 0;
            for (const icon of icons) {
                const text = (icon.innerText || icon.textContent || '').trim().toLowerCase();
                if (text !== 'cancel' && text !== 'close') continue;
                const btn = icon.closest('button');
                if (!btn || !isVisible(btn)) continue;
                const rect = btn.getBoundingClientRect();
                if (rect.top < window.innerHeight - 420) continue;  // 只处理底部输入区附近
                btn.click();
                count += 1;
            }
            return count;
        }""") or 0
        removed_total += bulk_removed
        if bulk_removed:
            random_sleep(0.3, 0.6)

        if not bulk_removed:
            close_selectors = UI_SELECTORS["google_fx"].get("close_history_btn", [])
            for _ in range(max_rounds):
                clicked_any = False
                for sel in close_selectors:
                    try:
                        btn = page.locator(sel).first
                        if btn.is_visible(timeout=200):
                            btn.click()
                            clicked_any = True
                            random_sleep(0.3, 0.6)
                            break
                    except Exception:
                        continue
                if not clicked_any:
                    break
                removed_total += 1

        if removed_total:
            log(f"🧹 清除 {removed_total} 个历史参考图 chip（输入区素材槽）", "GoogleFX")
    except Exception as e:
        log(f"  ⚠️ _clear_prompt_reference_chips_image 失败: {type(e).__name__}", "GoogleFX")
    return removed_total

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


# ==============================================================================
# 📡 媒体捕获 / 输出目录 (原 services/google_fx.py，函数体逐字未改动；
# 只被 google_fx_video.py / google_fx_image.py 使用，挪到这里后 google_fx.py
# 不再需要被 video.py/image.py 反向导入)
# ==============================================================================

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

def _ensure_output_dir(req, default_subdir):
    """解析并创建输出目录，保持现有默认规则不变。"""
    output_dir = req.output_path if (hasattr(req, "output_path") and req.output_path) else os.path.join(OUTPUT_DIR, default_subdir)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


# ==============================================================================
# ⏹️ 取消检测 + 紧急代理轮换 + 抓包缓冲上限 (原 services/google_fx.py，
# 函数体逐字未改动；只被 google_fx.py 自身与 google_fx_image.py 使用，挪到这里
# 后 google_fx_image.py 不再需要反向导入 google_fx.py)
# ==============================================================================

def _check_cancelled():
    if cancel_flag.is_cancelled:
        log("🛑 任务已取消，终止执行", "GoogleFX")
        raise RuntimeError("任务已取消")

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

_CAPTURED_DATA_MAXLEN = 200
