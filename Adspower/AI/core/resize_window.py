# -*- coding: utf-8 -*-
"""通过 Playwright 设置 viewport 并使用 JS evaluate 来解决视口问题"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from utils.browser import get_ads_ws_url

USER_ID = "k1c4rryj"
PORT = "50325"

ws_url = get_ads_ws_url(USER_ID, PORT)
print(f"WS URL: {ws_url}")

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(ws_url)
    context = browser.contexts[0]
    
    page = None
    for pg in context.pages:
        if "labs.google" in pg.url:
            page = pg
            break
    
    if not page:
        page = context.pages[0] if context.pages else None
    
    if page:
        print(f"Found page: {page.url[:60]}")
        
        # 检查当前 viewport
        size_before = page.evaluate("JSON.stringify({w: window.innerWidth, h: window.innerHeight, ow: window.outerWidth, oh: window.outerHeight})")
        print(f"Before: {size_before}")
        
        # 尝试方法1: set_viewport_size
        try:
            page.set_viewport_size({"width": 1400, "height": 900})
            print("set_viewport_size succeeded")
        except Exception as e:
            print(f"set_viewport_size failed: {e}")
        
        # 验证
        size_after = page.evaluate("JSON.stringify({w: window.innerWidth, h: window.innerHeight, ow: window.outerWidth, oh: window.outerHeight})")
        print(f"After: {size_after}")
        
        # 检查底部配置按钮是否可见
        buttons = page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const found = btns.filter(b => b.textContent.includes('Banana') || b.textContent.includes('Nano'));
            return found.map(b => ({
                text: b.textContent.trim().substring(0, 50),
                visible: b.offsetParent !== null,
                rect: b.getBoundingClientRect()
            }));
        }""")
        print(f"Banana buttons: {json.dumps(buttons, indent=2)}")
    
    browser.close()
    print("Done")
