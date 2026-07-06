from pathlib import Path


target = Path(__file__).resolve().parents[1] / "Adspower" / "AI" / "core" / "utils" / "browser.py"
lines = target.read_text(encoding="utf-8").splitlines()

start = None
end = None
for i, line in enumerate(lines):
    if line.startswith('def get_ads_ws_url('):
        start = i
    if start is not None and i > start and line.startswith('def find_or_create_page('):
        end = i
        break

if start is None or end is None:
    raise SystemExit("Could not locate function boundaries")

replacement = [
    'def get_ads_ws_url(user_id="kxplh32", port="50325"):',
    '    """Return AdsPower websocket URL, preferring an already-active profile."""',
    '    active_url = f"http://127.0.0.1:{port}/api/v1/browser/active?user_id={user_id}"',
    '    active_resp = requests.get(active_url, timeout=5).json()',
    '    if active_resp.get("code") == 0 and active_resp.get("data", {}).get("status") == "Active":',
    '        ws_url = active_resp.get("data", {}).get("ws", {}).get("puppeteer")',
    '        if ws_url:',
    '            log(f"复用已打开的 AdsPower 浏览器: {user_id}", "AdsPower")',
    '            return ws_url',
    '',
    '    launch_args = \'%5B%22--disable-features%3DHardwareMediaKeyHandling%22%2C%22--mute-audio%22%5D\'',
    '    start_url = f"http://127.0.0.1:{port}/api/v1/browser/start?user_id={user_id}&launch_args={launch_args}"',
    '    start_resp = requests.get(start_url, timeout=20).json()',
    '    if start_resp.get("code") != 0:',
    '        raise Exception(f"AdsPower 启动失败: {start_resp.get(\'msg\', \'unknown error\')}")',
    '',
    '    ws_url = start_resp.get("data", {}).get("ws", {}).get("puppeteer")',
    '    if not ws_url:',
    '        raise Exception("AdsPower 未返回 puppeteer websocket 地址")',
    '    return ws_url',
    '',
]

new_lines = lines[:start] + replacement + lines[end:]
target.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print("rewritten", target)
