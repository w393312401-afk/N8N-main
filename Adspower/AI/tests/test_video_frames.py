# -*- coding: utf-8 -*-
"""
🎬 首尾帧视频功能测试脚本
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
--mode upload      → 只测上传（不发送生成），截图后退出
--mode start       → 仅首帧完整生成
--mode both        → 首尾双帧完整生成
--mode text        → 纯文字生成
--mode all         → start + both + text 全跑
--mode stability   → 多轮重复首尾帧生成，验证修复后稳定性

图片路径可通过重新写 IMG_START/IMG_END 或通过命令行 --start / --end 低上传。
"""

import os
import sys
import time
from pprint import pprint

# 测试脚本位于 tests/，把 core/ 加入导入路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

from models import VideoRequest
from services.google_fx import _generate_video_google_fx

# ── 公共配置 ──────────────────────────────────────────────────
USER_ID = "ku07skg"   # profile_id: ku07skg  |  debug_port: 65260

IMG_DIR   = "/Users/fly/Desktop/N8N-main/AI_video/images"
IMG_START = os.path.join(IMG_DIR, "fx_batch_1775049613_0.jpg")
IMG_END   = os.path.join(IMG_DIR, "fx_batch_1775055570_0.jpg")

TEST_PROMPT = (
    "Dramatic timelapse transformation: an abandoned industrial building "
    "is renovated into a modern space, cinematic lighting, 9:16 vertical"
)

SCREENSHOT_DIR = "/tmp/fx_test_shots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def _header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────
# 🆕 Upload-only 测试：只走上传流程，截图确认，不发生成
# ─────────────────────────────────────────────────────────────
def test_upload_only():
    """
    只测试首尾帧上传流程：
      1. 打开浏览器 / 导航到 Flow
      2. 切换 Video 模式
      3. 上传首帧 (Start)
      4. 上传尾帧  (End)
      5. 截图保存，立即退出（不输入提示词、不点击生成）
    """
    _header("📸 Upload-Only 测试：首尾帧上传（不发生成）")
    print(f"  首帧: {IMG_START}")
    print(f"  尾帧: {IMG_END}")

    import time as _time
    from playwright.sync_api import sync_playwright
    from utils.browser import get_ads_ws_url, find_or_create_page, random_sleep, clean_path
    from services.google_fx import (
        find_fx_config_button, check_fx_config, fix_fx_config,
        _wait_for_fx_toolbar, _normalize_ratio_value,
        _safe_press_escape,
    )
    from ui_selectors import RATIO_MAP

    img_path     = clean_path(IMG_START)
    end_img_path = clean_path(IMG_END)
    model        = "Veo 3.1 - Fast"
    ratio        = "9:16"

    # 浏览器已打开时直接用 ws url（get_ads_ws_url 在已开启状态下可能返回空）
    WS_URL = "ws://127.0.0.1:65260/devtools/browser/c30cd17d-7b81-4fa9-af0c-f113d04f8699"

    try:
        ws_url = WS_URL
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(ws_url)
            context = browser.contexts[0]
            page    = find_or_create_page(context, "labs.google")
            page.bring_to_front()

            if "labs.google" not in page.url:
                page.goto("https://labs.google/fx/tools/flow", timeout=60000)
                random_sleep(1, 2)

            # New project
            try:
                btn = page.locator("button").filter(has_text="New project").first
                if btn.is_visible():
                    print("🆕 点击 New project")
                    btn.click(); random_sleep(3, 5)
            except: pass

            _wait_for_fx_toolbar(page, timeout=30)

            # 清理历史参考图
            try:
                close_btns = page.locator('button:has(i:has-text("close"))')
                page.wait_for_timeout(800)
                for _ in range(close_btns.count()):
                    try:
                        b = close_btns.first
                        if b.is_visible(): b.click(force=True); random_sleep(0.4, 0.8)
                    except: pass
            except: pass

            # 配置 Video 模式
            selected_ratio = _normalize_ratio_value(ratio)
            vid_ratio = RATIO_MAP.get(selected_ratio, selected_ratio) if selected_ratio else None
            cfg_btn, status_text = find_fx_config_button(page)
            if cfg_btn:
                checks = check_fx_config(status_text, model=model,
                                         orientation=vid_ratio, count="x1", want_video=True)
                print(f"  配置状态: '{status_text}'")
                print(f"  Video: {'✅' if checks['mode'] else '❌'}  "
                      f"模型: {'✅' if checks['model'] else '❌'}  "
                      f"比例: {'✅' if checks['orientation'] else '❌'}")
                if not all(checks.values()):
                    fix_fx_config(page, cfg_btn, checks, model=model,
                                  orientation=vid_ratio, count="x1", want_video=True)
            else:
                print("  ❌ 未找到配置按钮")

            # ── 调用内部上传逻辑（复用 _generate_video_google_fx 的内部函数）──
            # 最简方式：通过一个仅上传的 VideoRequest 触发，然后在生成前截图
            # 实际上 _generate_video_google_fx 会一直执行，所以我们用
            # 独立内联逻辑来只做上传。

            from services.google_fx import (
                _wait_for_flow_reference_ready,
            )

            def upload_frame(local_path, label):
                """简化版上传帧，复用已验证的选择逻辑。"""
                abs_path = os.path.abspath(local_path)
                asset_name = os.path.basename(abs_path)
                print(f"\n  📸 上传 {label} 帧: {asset_name}")

                # Step 1: 点击 Start / End 入口
                entry_btn = None
                dialog_id = None
                frame_dialog = None
                for _sel_str in [
                    f"div[type='button'][aria-haspopup='dialog'][aria-controls]:text-is('{label}')",
                    f"div[type='button'][aria-haspopup='dialog']:text-is('{label}')",
                    f"div[aria-haspopup='dialog']:text-is('{label}')",
                    f".jekiem:text-is('{label}')",
                ]:
                    try:
                        c = page.locator(_sel_str).first
                        if c.is_visible(timeout=3000):
                            entry_btn = c
                            dialog_id = c.get_attribute("aria-controls")
                            c.click()
                            print(f"    🎯 已点击 {label} 入口")
                            break
                    except: pass

                if not entry_btn:
                    print(f"    ❌ 未找到 {label} 入口")
                    return False

                random_sleep(0.8, 1.2)

                # Step 2: 锁定 dialog
                if dialog_id:
                    try:
                        frame_dialog = page.locator(f'[id="{dialog_id}"]').first
                        frame_dialog.wait_for(state="visible", timeout=6000)
                        print(f"    ✅ dialog: #{dialog_id}")
                    except: frame_dialog = None
                if frame_dialog is None:
                    try:
                        vd = page.locator("[role='dialog']:visible")
                        if vd.count(): frame_dialog = vd.last
                    except: pass

                upload_scope = frame_dialog if frame_dialog else page

                # Step 3: 尝试从素材列表直接点选
                for sel_str in [
                    f'img[alt="{asset_name}"]',
                    f'div.sc-70a6bd2c-20:has-text("{asset_name}")',
                    f'div.sc-70a6bd2c-14:has-text("{asset_name}")',
                ]:
                    try:
                        matches = upload_scope.locator(sel_str)
                        for idx in range(matches.count()):
                            node = matches.nth(idx)
                            if not node.is_visible(timeout=2000): continue
                            try:
                                card = node.locator(
                                    "xpath=ancestor::div[contains(@class,'sc-70a6bd2c-14')]"
                                ).first
                                if card.is_visible(timeout=1000):
                                    card.click(force=True)
                                else:
                                    node.click(force=True)
                            except:
                                node.click(force=True)
                            print(f"    ✅ 已选现有素材: {asset_name}")
                            random_sleep(0.5, 0.8)
                            return True
                    except: pass

                # Step 4: 等待 media picker 再试一次
                try:
                    page.locator("input[placeholder='Search for Assets']").wait_for(
                        state="visible", timeout=5000
                    )
                    print("    ✅ Media Picker 就绪")
                except: pass

                for sel_str in [
                    f'img[alt="{asset_name}"]',
                    f'div.sc-70a6bd2c-20:has-text("{asset_name}")',
                ]:
                    try:
                        m = upload_scope.locator(sel_str)
                        if m.count() and m.first.is_visible(timeout=2000):
                            m.first.click(force=True)
                            print(f"    ✅ 已选现有素材 (picker): {asset_name}")
                            return True
                    except: pass

                # Step 5: file input 上传
                # ⚠️ 不能先全页搜索预挂载的 file input（首帧上传后 DOM 中可能残留旧 input）
                # 必须先找 Upload 触发区域，再在 dialog scope 内查找 file input
                file_input = None
                upload_trigger = None
                for up_sel in ["div.sc-70a6bd2c-10.fxheTi", "div.sc-70a6bd2c-10",
                               "div[class*='upload']", "button:has-text('Upload')"]:
                    try:
                        ms = upload_scope.locator(up_sel)
                        for idx in range(ms.count()):
                            el = ms.nth(idx)
                            if el.is_visible(timeout=1500) and "upload" in (el.inner_text() or "").lower():
                                upload_trigger = el
                                print(f"    🎯 Upload 触发区域 ({up_sel!r})")
                                break
                        if upload_trigger:
                            break
                    except: pass

                if upload_trigger is None:
                    print(f"    ❌ 在 {label} dialog 内未找到 Upload 触发区域")
                    return False

                upload_trigger.click(force=True)
                print("    ✅ 已点击 Upload image")
                random_sleep(0.4, 0.6)

                # 必须在 upload_scope (dialog) 内查找，避免复用其他帧残留的 file input
                for fi_sel in ["input[type='file'][accept='image/*']", "input[type='file']"]:
                    try:
                        fi = upload_scope.locator(fi_sel).first
                        if fi.count():
                            file_input = fi
                            print(f"    🎯 file input 已定位 (scope=dialog, {fi_sel!r})")
                            break
                    except: pass
                # 兜底: 如果 dialog scope 未找到，降级到全页查找（但记录警告）
                if file_input is None:
                    for fi_sel in ["input[type='file'][accept='image/*']", "input[type='file']"]:
                        try:
                            fi = page.locator(fi_sel).first
                            if fi.count():
                                file_input = fi
                                print(f"    ⚠️ file input 回退全页定位 ({fi_sel!r})")
                                break
                        except: pass

                if file_input is None:
                    print("    ❌ 未找到 file input")
                    return False

                file_input.set_input_files(abs_path)
                print(f"    ✅ set_input_files: {asset_name}")
                random_sleep(1.5, 2.5)

                # Crop and Save
                try:
                    crop_btn = page.locator("button:has-text('Crop and Save')").last
                    crop_btn.wait_for(state="visible", timeout=12000)
                    crop_btn.click()
                    print("    ✅ Crop and Save")
                    try:
                        page.locator("button:has-text('Crop and Save')").wait_for(state="hidden", timeout=8000)
                        print("    ✅ Crop dialog 已关闭")
                    except:
                        random_sleep(2.0, 3.0)
                        print("    ⚠️ Crop dialog 关闭超时，强制等待 2.0-3.0s")
                    # ⚠️ Start 帧 Crop 完成后，额外等待 UI 稳定
                    if label == "Start":
                        random_sleep(1.5, 2.5)
                        print("    ⏳ Start 帧处理完毕，等待 UI 稳定后再上传 End 帧")
                except Exception as _ce:
                    print(f"    ⚠️ Crop and Save 未出现或失败: {_ce}")

                return True

            # ── 执行上传 ──
            start_ok = upload_frame(img_path, "Start")
            end_ok   = upload_frame(end_img_path, "End")

            # ── 截图 ──
            shot_path = os.path.join(SCREENSHOT_DIR, f"upload_test_{int(time.time())}.png")
            page.screenshot(path=shot_path, full_page=False)
            print(f"\n  📷 截图已保存: {shot_path}")

            print("\n── 上传结果 ──")
            print(f"  Start 帧: {'✅ 成功' if start_ok else '❌ 失败'}")
            print(f"  End   帧: {'✅ 成功' if end_ok   else '❌ 失败'}")
            print("  ⏹️  不发送生成，直接退出。")

            browser.close()
            return {"start": start_ok, "end": end_ok, "screenshot": shot_path}

    except Exception as e:
        print(f"\n❌ 异常: {e}")
        return {"start": False, "end": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# 场景 1: 仅首帧完整生成
# ─────────────────────────────────────────────────────────────
def test_start_frame_only():
    _header("🎬 场景1: 仅首帧 (Start frame)")
    req = VideoRequest(user_id=USER_ID, prompt=TEST_PROMPT,
                       model="Veo 3.1 - Fast", ratio="9:16",
                       image=IMG_START, end_image="")
    result = _generate_video_google_fx(req)
    print("\n── 结果 ──"); pprint(result)
    return result


# ─────────────────────────────────────────────────────────────
# 场景 2: 首尾双帧完整生成
# ─────────────────────────────────────────────────────────────
def test_start_and_end_frame():
    _header("🎬 场景2: 首尾双帧 (Start + End frame)")
    req = VideoRequest(user_id=USER_ID, prompt=TEST_PROMPT,
                       model="Veo 3.1 - Fast", ratio="9:16",
                       image=IMG_START, end_image=IMG_END)
    result = _generate_video_google_fx(req)
    print("\n── 结果 ──"); pprint(result)
    return result


# ─────────────────────────────────────────────────────────────
# 场景 3: 纯文字生成
# ─────────────────────────────────────────────────────────────
def test_text_to_video():
    _header("🖊️  场景3: 纯文字生成 (Text to Video)")
    req = VideoRequest(user_id=USER_ID, prompt=TEST_PROMPT,
                       model="Veo 3.1 - Fast", ratio="9:16",
                       image="", end_image="")
    result = _generate_video_google_fx(req)
    print("\n── 结果 ──"); pprint(result)
    return result


# ─────────────────────────────────────────────────────────────
# 🔄 稳定性测试: 多轮重复首尾帧完整生成，统计成功率
# ─────────────────────────────────────────────────────────────
def test_stability_both_frames(rounds: int = 3):
    """
    稳定性测试: 连续跑多轮首尾帧完整生成，验证修复后的稳定性。
    """
    _header(f"🔄 稳定性测试: 首尾帧生成 × {rounds} 轮")
    pass_count = 0
    fail_count = 0
    results = []

    for i in range(1, rounds + 1):
        print(f"\n{'='*60}")
        print(f"  🔁 第 {i}/{rounds} 轮")
        print(f"{'='*60}")
        req = VideoRequest(
            user_id=USER_ID,
            prompt=TEST_PROMPT,
            model="Veo 3.1 - Fast",
            ratio="9:16",
            image=IMG_START,
            end_image=IMG_END,
        )
        t0 = time.time()
        result = _generate_video_google_fx(req)
        elapsed = time.time() - t0
        ok = result.get("status") == "success"
        if ok:
            pass_count += 1
            print(f"  ✅ 第 {i} 轮成功 | 耗时 {elapsed:.0f}s")
        else:
            fail_count += 1
            print(f"  ❌ 第 {i} 轮失败 | 耗时 {elapsed:.0f}s | {result.get('message','')[:80]}")
        results.append({"round": i, "ok": ok, "elapsed": elapsed, "result": result})

    print(f"\n{'='*60}")
    print(f"  📊 稳定性测试完成: {pass_count}/{rounds} 成功  (成功率 {pass_count/rounds*100:.0f}%)")
    print(f"{'='*60}")
    return results


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="首尾帧视频功能测试")
    parser.add_argument(
        "--mode",
        choices=["upload", "start", "both", "text", "all", "stability"],
        default="upload",
        help=(
            "upload    = 只测上传，不发生成 (默认)\n"
            "start     = 仅首帧完整生成\n"
            "both      = 首尾双帧完整生成\n"
            "text      = 纯文字生成\n"
            "all       = start + both + text 全跑\n"
            "stability = 多轮重复首尾帧生成，验证稳定性"
        ),
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="stability 模式下的测试轮数 (默认 3)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default="",
        help="首帧图片本地路径（覆盖脚本内 IMG_START）",
    )
    parser.add_argument(
        "--end",
        type=str,
        default="",
        help="尾帧图片本地路径（覆盖脚本内 IMG_END）",
    )
    args = parser.parse_args()

    # 运行时覆盖图片路径
    if args.start:
        IMG_START = args.start
    if args.end:
        IMG_END = args.end

    # ━━ 验证文件存在 ━━
    missing = []
    for path, label in [(IMG_START, "首帧"), (IMG_END, "尾帧")]:
        status = "✅" if os.path.exists(path) else "❌"
        print(f"  {status} {label}: {path}")
        if not os.path.exists(path):
            missing.append(label)
    print()

    if args.mode in ("upload", "start", "both", "all", "stability") and missing:
        print(f"⚠️  以下图片文件不存在: {', '.join(missing)}")
        print("💡 请通过 --start / --end 参数指定有效的本地图片路径：")
        print(f"   python3 tests/test_video_frames.py --mode {args.mode} \\")
        print(f"     --start /path/to/start_frame.jpg \\")
        print(f"     --end /path/to/end_frame.jpg")
        if args.mode in ("upload", "both", "all", "stability"):
            sys.exit(1)
        # start 模式可以尝试，但首帧不存在也会失败——提示用户
        if "首帧" in missing:
            sys.exit(1)

    if args.mode == "upload":
        test_upload_only()
    elif args.mode == "start":
        test_start_frame_only()
    elif args.mode == "both":
        test_start_and_end_frame()
    elif args.mode == "text":
        test_text_to_video()
    elif args.mode == "all":
        test_start_frame_only()
        test_start_and_end_frame()
        test_text_to_video()
    elif args.mode == "stability":
        test_stability_both_frames(rounds=args.rounds)
