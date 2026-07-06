from pathlib import Path
import re


target = Path(__file__).resolve().parents[1] / "Adspower" / "AI" / "core" / "utils" / "browser.py"
text = target.read_text(encoding="utf-8")

replacement = '''def get_ads_ws_url(user_id="kxplh32", port="50325"):
    """Return AdsPower websocket URL, preferring an already-active profile."""
    active_url = f"http://127.0.0.1:{port}/api/v1/browser/active?user_id={user_id}"
    active_resp = requests.get(active_url, timeout=5).json()
    if active_resp.get("code") == 0 and active_resp.get("data", {}).get("status") == "Active":
        ws_url = active_resp.get("data", {}).get("ws", {}).get("puppeteer")
        if ws_url:
            log(f"复用已打开的 AdsPower 浏览器: {user_id}", "AdsPower")
            return ws_url

    launch_args = '%5B%22--disable-features%3DHardwareMediaKeyHandling%22%2C%22--mute-audio%22%5D'
    start_url = f"http://127.0.0.1:{port}/api/v1/browser/start?user_id={user_id}&launch_args={launch_args}"
    start_resp = requests.get(start_url, timeout=20).json()
    if start_resp.get("code") != 0:
        raise Exception(f"AdsPower 启动失败: {start_resp.get('msg', 'unknown error')}")

    ws_url = start_resp.get("data", {}).get("ws", {}).get("puppeteer")
    if not ws_url:
        raise Exception("AdsPower 未返回 puppeteer websocket 地址")
    return ws_url
'''

pattern = re.compile(
    r'def get_ads_ws_url\(user_id="kxplh32", port="50325"\):.*?(?=\n\ndef find_or_create_page)',
    re.S,
)

new_text, count = pattern.subn(replacement.rstrip(), text, count=1)
if count != 1:
    raise SystemExit("Failed to replace get_ads_ws_url()")

target.write_text(new_text, encoding="utf-8")
print("patched", target)
