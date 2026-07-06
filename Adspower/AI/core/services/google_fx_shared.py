# -*- coding: utf-8 -*-
"""
🔧 Google FX 共享工具函数
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
底部工具栏操控、配置检查/修复、发送按钮等辅助函数。
被 google_fx_video.py 和 google_fx_image.py 共同引用。
"""

from utils.logger import log
from utils.browser import random_sleep
from ui_selectors import ORIENT_ICON_MAP, RATIO_MAP


def find_fx_config_button(page):
    """
    找到底部的配置状态按钮 (新版 UI)。
    按钮文字可能是:
      - "🍌 Nano Banana 2 crop_9_16 x1" (Image模式)
      - "Video 📐 x3" (Video模式)
    """
    for pattern in ["Banana", "Nano", "Imagen", "Video", "Veo", "视频", "图片"]:
        try:
            btn = page.locator("button").filter(has_text=pattern).last
            if btn.is_visible():
                txt = btn.inner_text().strip().replace('\n', ' ')
                log(f"  找到配置按钮 ('{pattern}'): '{txt}'", "GoogleFX")
                return btn, txt
        except: pass
    for xn in ["x1", "x2", "x3", "x4"]:
        try:
            btn = page.locator("button").filter(has_text=xn).last
            if btn.is_visible():
                txt = btn.inner_text().strip().replace('\n', ' ')
                log(f"  找到配置按钮 ('{xn}'): '{txt}'", "GoogleFX")
                return btn, txt
        except: pass
    return None, ""


def check_fx_config(status_text, model="Nano Banana 2", orientation="Portrait", count="x1", want_video=False):
    """从状态文字判断当前配置是否正确。"""
    checks = {}
    # 模型匹配: Veo 系列属于 Video 模式，状态栏只显示 "Video" 而非完整版本号
    if model and model.lower().startswith("veo"):
        checks["model"] = any(x in status_text for x in ["Video", "Veo", "视频"])
    else:
        checks["model"] = model in status_text if model else True
    orient_icon = ORIENT_ICON_MAP.get(orientation, "")
    checks["orientation"] = orient_icon in status_text if orient_icon else True
    if count:
        count_alt = f"{count.lstrip('x')}x" if count.startswith("x") else f"x{count.rstrip('x')}"
        checks["count"] = count in status_text or count_alt in status_text
    else:
        checks["count"] = True
    is_video = any(x in status_text for x in ["Video", "Veo", "视频"])
    checks["mode"] = is_video if want_video else not is_video
    return checks


def _click_first_visible(page, selectors):
    """Click the first visible locator from a selector list."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                loc.click()
                return True
        except:
            pass
    return False


def _close_fx_popovers(page):
    """Close nested Radix menus so they cannot intercept the editor click."""
    for _ in range(3):
        try:
            if not page.locator("[data-radix-popper-content-wrapper]:visible, [role='menu']:visible").count():
                break
            page.keyboard.press("Escape")
            random_sleep(0.2, 0.4)
        except:
            pass


def fix_fx_config(page, cfg_btn, checks, model="Nano Banana 2", orientation="Portrait", count="x1", want_video=False):
    """打开配置面板并修正不正确的配置项。"""
    log("⚙️ 需要修改配置，打开面板...", "GoogleFX")
    try:
        cfg_btn.scroll_into_view_if_needed(timeout=5000)
    except:
        pass
    cfg_btn.click(force=True)
    random_sleep(1.5, 2.5)

    if not checks.get("mode", True):
        target_mode_name = "Video" if want_video else "Image"
        log(f"  → 切换到 {target_mode_name} 模式", "GoogleFX")
        try:
            selectors = (
                ["button[role='tab'][id$='-trigger-VIDEO']", "button[role='tab']:has-text('视频')", "button:has-text('Video')"]
                if want_video
                else ["button[role='tab'][id$='-trigger-IMAGE']", "button[role='tab']:has-text('图片')", "button:has-text('Image')"]
            )
            if _click_first_visible(page, selectors):
                random_sleep(0.5, 1)
                log(f"  ✅ {target_mode_name} 已点击", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ {target_mode_name} 模式切换异常: {e}", "GoogleFX")

    if not checks.get("orientation", True):
        log(f"  → 切换到 {orientation}", "GoogleFX")
        try:
            orient_suffix = {
                "Landscape": "LANDSCAPE",
                "Portrait": "PORTRAIT",
                "Square": "SQUARE",
            }.get(orientation)
            selectors = []
            if orient_suffix:
                selectors.append(f"button[role='tab'][id$='-trigger-{orient_suffix}']")
            selectors.extend([f"button:has-text('{orientation}')", f"button:has-text('{orient_icon}')"])
            if _click_first_visible(page, selectors):
                random_sleep(0.5, 1)
                log(f"  ✅ {orientation} 已点击", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ {orientation} 切换异常: {e}", "GoogleFX")

    if not checks.get("count", True):
        log(f"  → 切换到 {count}", "GoogleFX")
        try:
            count_value = count.lstrip("x")
            selectors = [
                f"button[role='tab'][id$='-trigger-{count_value}']",
                f"button:has-text('{count}')",
            ]
            if _click_first_visible(page, selectors):
                random_sleep(0.5, 1)
                log(f"  ✅ {count} 已点击", "GoogleFX")
        except Exception as e:
            log(f"  ⚠️ {count} 切换异常: {e}", "GoogleFX")

    if not checks.get("model", True):
        log(f"  → 切换到 {model}", "GoogleFX")
        try:
            model_dd = None
            for kw in ["Banana", "Nano", "Imagen", "Veo"]:
                try:
                    dd = page.locator("button").filter(has_text=kw)
                    for j in range(dd.count()):
                        t = dd.nth(j).inner_text()
                        if "arrow_drop_down" in t or "▾" in t:
                            model_dd = dd.nth(j)
                            break
                    if model_dd: break
                except: pass
            if not model_dd:
                for kw in ["Banana", "Nano", "Imagen", "Veo"]:
                    try:
                        dd = page.locator("button").filter(has_text=kw).last
                        if dd.is_visible():
                            model_dd = dd
                            break
                    except: pass
            if model_dd and model_dd.is_visible():
                curr = model_dd.inner_text().strip()
                log(f"  模型下拉文字: '{curr}'", "GoogleFX")
                model_key = model.split()[-1] if model else ""
                if model_key and model_key not in curr:
                    model_dd.click()
                    random_sleep(1, 2)
                    pro = None
                    for sel in [
                        f"[role='option']:has-text('{model_key}')",
                        f"[role='menuitem']:has-text('{model_key}')",
                        f"li:has-text('{model_key}')",
                        f"button:has-text('{model}')",
                    ]:
                        try:
                            p_item = page.locator(sel).first
                            if p_item.is_visible():
                                pro = p_item
                                break
                        except: pass
                    if pro:
                        pro.click()
                        random_sleep(0.5, 1)
                        log(f"  ✅ {model} 已选择", "GoogleFX")
                    else:
                        log(f"  ❌ {model_key} 选项未找到", "GoogleFX")
                else:
                    log(f"  ✅ 模型已正确", "GoogleFX")
            else:
                log(f"  ❌ 模型下拉按钮未找到", "GoogleFX")
        except Exception as e:
            log(f"  ❌ 模型异常: {e}", "GoogleFX")

    _close_fx_popovers(page)
    random_sleep(1, 2)


def click_fx_send_button(page, input_el=None):
    """点击发送按钮 (新版 UI: arrow icon / aria-label / Create / Enter)"""
    sent = False
    # 方法1: 找包含 arrow icon 的按钮
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
            except: pass
    except: pass
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
            except: pass
    # 方法3: Create 按钮
    if not sent:
        try:
            create_btn = page.locator("button").filter(has_text="Create").last
            if create_btn.is_visible():
                create_btn.click()
                sent = True
                log("✅ 已点击 Create 按钮", "GoogleFX")
        except: pass
    # 方法4: Enter
    if not sent and input_el:
        input_el.press("Enter")
        log("⚠️ 按 Enter 提交", "GoogleFX")
    return sent
