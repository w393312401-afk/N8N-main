#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔎 Google FX 选择器烟雾测试
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
不生成任何内容，只打开 Flow 页面逐条检查关键选择器是否仍能命中。
Google 前端改版当天即可发现选择器腐烂，而不是等生产任务失败才知道。

用法:
  python3 tools/selector_smoke_test.py                # 完整检查（需 AdsPower 在运行）
  python3 tools/selector_smoke_test.py --stop-browser # 检查后关闭浏览器

⚠️ 只在服务空闲时运行（不要与正在生成的任务抢同一个浏览器画布）。
可配合 cron / n8n 每日定时调用；退出码非 0 = 有必需选择器族全部失效，需要人工修选择器。

报告同时追加到 runtime/selector_smoke_report.json 供历史比对。
"""

import json
import os
import sys
import time

AI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AI_DIR, "core"))

from playwright.sync_api import sync_playwright

from ui_selectors import UI_SELECTORS, SELECTOR_VERSION
from utils.browser import get_ads_ws_url, find_or_create_page, stop_ads_browser

FX = UI_SELECTORS["google_fx"]

# (族名, 选择器列表, 是否必需, 检查场景: home=Flow首页 / project=项目画布 / panel=配置面板)
CHECKS = [
    ("new_project_btn",     FX["new_project_btn"],                          False, "home"),
    ("project_links",       ["a[href*='/project/']"],                       False, "home"),
    ("prompt_input",        ["[data-slate-editor='true']"] + FX["prompt_input"], True,  "project"),
    ("add_media_btn",       FX["add_media_btn"],                            True,  "project"),
    ("mode_tab_image",      FX["mode_tab_image"] + ["[aria-controls$='-IMAGE']"],  True, "panel"),
    ("mode_tab_video",      FX["mode_tab_video"] + ["[aria-controls$='-VIDEO']"],  True, "panel"),
    ("ratio_tab_16_9",      [FX["ratio_tab"]["16:9"], "[aria-controls$='-LANDSCAPE']"], True, "panel"),
    ("ratio_tab_9_16",      [FX["ratio_tab"]["9:16"], "[aria-controls$='-PORTRAIT']"],  True, "panel"),
    ("count_tab_x1",        [FX["count_tab"]["x1"], "[aria-controls$='-content-1']"],   True, "panel"),
    ("config_panel_root",   FX["config_panel_root"],                        True,  "panel"),
]


def check_family(page, name, selectors, timeout_ms=2500):
    """返回 (命中层级, 命中的选择器)；全部未命中返回 (-1, '')。"""
    per_sel = max(timeout_ms // max(len(selectors), 1), 400)
    for idx, sel in enumerate(selectors):
        try:
            if page.locator(sel).first.is_visible(timeout=per_sel):
                return idx, sel
        except Exception:
            continue
    return -1, ""


def main():
    stop_after = "--stop-browser" in sys.argv
    report = {
        "ran_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "selector_version": SELECTOR_VERSION,
        "results": {},
        "required_missing": [],
        "skipped": [],
    }

    print(f"🔎 选择器烟雾测试 | SELECTOR_VERSION={SELECTOR_VERSION}")
    ws_url = get_ads_ws_url(auto_rotate_proxy=False)  # 烟雾测试不消耗代理轮换
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(ws_url)
        context = browser.contexts[0]
        page = find_or_create_page(context, "labs.google", fallback_url="https://labs.google/fx/tools/flow")
        page.bring_to_front()
        if "labs.google" not in page.url:
            page.goto("https://labs.google/fx/tools/flow", timeout=60000)
        page.wait_for_timeout(3000)

        # ── 场景 1: Flow 首页 ──
        for name, sels, required, scene in CHECKS:
            if scene != "home":
                continue
            idx, hit = check_family(page, name, sels)
            report["results"][name] = {"hit_index": idx, "hit_selector": hit, "required": required}

        # ── 场景 2: 打开最近项目（只读导航，不生成）──
        in_project = False
        try:
            link = page.locator("a[href*='/project/']").first
            if link.is_visible(timeout=3000):
                link.click()
                page.wait_for_timeout(5000)
                in_project = True
        except Exception:
            pass
        if not in_project and "/project/" in page.url:
            in_project = True

        if in_project:
            for name, sels, required, scene in CHECKS:
                if scene != "project":
                    continue
                idx, hit = check_family(page, name, sels)
                report["results"][name] = {"hit_index": idx, "hit_selector": hit, "required": required}

            # ── 场景 3: 打开底部配置面板检查 tab（只开面板，Escape 关闭）──
            try:
                from services.google_fx_helpers import find_fx_config_button
                cfg_btn, status_text = find_fx_config_button(page)
                report["results"]["config_button"] = {
                    "hit_index": 0 if cfg_btn else -1,
                    "hit_selector": (status_text or "")[:80],
                    "required": True,
                }
                if cfg_btn:
                    cfg_btn.click()
                    page.wait_for_timeout(1500)
                    for name, sels, required, scene in CHECKS:
                        if scene != "panel":
                            continue
                        idx, hit = check_family(page, name, sels)
                        report["results"][name] = {"hit_index": idx, "hit_selector": hit, "required": required}
                    page.keyboard.press("Escape")
            except Exception as e:
                report["results"]["config_button"] = {"hit_index": -1, "hit_selector": f"error: {e}", "required": True}
        else:
            report["skipped"] = [name for name, _s, _r, scene in CHECKS if scene in ("project", "panel")]
            report["skipped"].append("config_button")
            print("⚠️ 未找到可打开的历史项目，画布级选择器跳过（首页级检查仍有效）")

    if stop_after:
        stop_ads_browser()

    # ── 汇总 ──
    print(f"\n{'族名':<22} {'层级':>4}  命中选择器")
    print("─" * 78)
    for name, info in report["results"].items():
        idx = info["hit_index"]
        mark = "✅" if idx == 0 else ("🟡" if idx > 0 else "❌")
        tail = " [必需]" if info["required"] and idx < 0 else ""
        print(f"{mark} {name:<20} {idx:>4}  {info['hit_selector'][:48]}{tail}")
        if info["required"] and idx < 0:
            report["required_missing"].append(name)
    if report["skipped"]:
        print(f"⏭️ 跳过: {', '.join(report['skipped'])}")

    # 追加历史报告
    try:
        report_path = os.path.join(AI_DIR, "runtime", "selector_smoke_report.json")
        history = []
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        history.append(report)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(history[-30:], f, ensure_ascii=False, indent=2)
        print(f"\n📄 报告已追加: {report_path}")
    except Exception as e:
        print(f"⚠️ 报告写入失败: {e}")

    # 选择器命中层级统计摘要（生产运行期间积累）
    try:
        from utils import selector_stats
        rows = selector_stats.summarize()[:5]
        if rows:
            print("\n📊 生产环境选择器健康度（主选择器命中率最低的 5 个族）:")
            for r in rows:
                print(f"  primary={r['primary_ratio']:.0%} miss={r['miss']} hits={r['total_hits']}  {r['family'][:60]}")
    except Exception:
        pass

    if report["required_missing"]:
        print(f"\n❌ 必需选择器族全部失效: {', '.join(report['required_missing'])} — Google FX 可能已改版，请更新 ui_selectors.py")
        return 1
    print("\n✅ 所有必需选择器族均可命中")
    return 0


if __name__ == "__main__":
    sys.exit(main())
