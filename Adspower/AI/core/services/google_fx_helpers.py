# -*- coding: utf-8 -*-
"""
🛠️ Google FX Helpers (UI Interaction, Navigation, Upload & Canvas Helpers)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import re
import time
import random

from config import MAX_WAIT_SECONDS, OUTPUT_DIR
from utils.logger import log
from utils.browser import random_sleep, clean_path
from ui_selectors import UI_SELECTORS, RATIO_MAP


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
    from services.google_fx import _find_first_visible
    return _find_first_visible(page, [
        "button[aria-haspopup='dialog']:has(span:text('Create'))",
        "button[aria-haspopup='dialog']:has(i.google-symbols:text('add_2'))",
        "button[aria-haspopup='dialog']:has(i:text('add_2'))",
        "button[aria-haspopup='dialog']",
        "button[aria-haspopup='menu']:has(span:text('Create'))",
        "button[aria-haspopup='menu']:has(span:text('添加媒体'))",
        "button[aria-haspopup='menu']:has(i:text('add'))",
        "button[aria-haspopup='menu']",
    ])


# ── _wait_for_fx_toolbar ──
def _wait_for_fx_toolbar(page, timeout=30):
    """等待底部工具栏中的输入区出现。"""
    from services.google_fx import _find_fx_prompt_input, _raise_if_manual_intervention_required
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
    from services.google_fx import _safe_press_escape
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
                        menu_id = (btn.get_attribute("aria-controls") or "").strip()
                        button_id = (btn.get_attribute("id") or "").strip()
                        btn.scroll_into_view_if_needed()
                        btn.click(force=True)
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
                        const blob = norm([
                            btn.innerText || '',
                            btn.getAttribute('aria-label') || '',
                            btn.getAttribute('aria-haspopup') || '',
                            btn.getAttribute('title') || '',
                            btn.querySelector('i')?.innerText || '',
                        ].join(' '));
                        if (!(
                            blob.includes('more_vert') ||
                            blob.includes('more_horiz') ||
                            blob.includes('aria-haspopup menu') ||
                            blob === 'more' ||
                            blob === 'more options' ||
                            blob.includes('更多') ||
                            blob.includes('菜单') ||
                            blob.includes(' more ')
                        )) {
                            return false;
                        }
                        const r = btn.getBoundingClientRect();
                        const horizontalNear = r.right >= rect.left - 48 && r.left <= rect.right + 64;
                        const verticalNear = r.bottom >= rect.top - 24 && r.top <= rect.top + Math.max(rect.height * 0.45, 120);
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
    from services.google_fx import _safe_press_escape
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
                const items = Array.from(root.querySelectorAll('[role="menuitem"], button, div, span')).filter(visible);
                const target = items.find((item) => {
                    const text = norm(item.innerText || '');
                    const label = norm(item.getAttribute('aria-label') || '');
                    const title = norm(item.getAttribute('title') || '');
                    return patterns.some((pattern) => {
                        const p = norm(pattern);
                        return text.includes(p) || label.includes(p) || title.includes(p);
                    });
                });
                if (!target) continue;
                target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
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
    from services.google_fx import _add_flow_image_to_prompt, _wait_for_flow_reference_ready
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
    from services.google_fx import _get_prompt_reference_uuids
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


# ── _clear_prompt_reference_chips ──
def _clear_prompt_reference_chips(page):
    """清空提示词输入区已挂入的参考图，用于顺序重试。"""
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
    from services.google_fx import _safe_press_escape
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
    from services.google_fx import _get_prompt_reference_uuids
    _clear_prompt_reference_chips(page)

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
            _clear_prompt_reference_chips(page)

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
    _clear_prompt_reference_chips(page)
    
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
    from services.google_fx import _get_panel_uuids, _safe_press_escape, _add_flow_image_to_prompt
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
    from services.google_fx import _find_fx_prompt_input, click_fx_send_button
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
    _clear_prompt_reference_chips(page)
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
