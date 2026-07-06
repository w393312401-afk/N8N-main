# -*- coding: utf-8 -*-
"""
🌐 ADS 指纹浏览器 多环境管理器
===================================
通过 AdsPower Local API 发现、启动并接管所有浏览器环境，
使用 Playwright CDP 连接实现自动化控制。

用法:
    python3 ads_env_manager.py [--port 50325]
"""

import os
import sys
import time
import json
import base64
import signal
import traceback
import requests
import urllib3
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# macOS / 跨平台编码兼容性处理
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# ==============================================================================
# 🎨 终端美化
# ==============================================================================
class Colors:
    PURPLE = "\033[95m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    GRAY   = "\033[90m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"

def log(msg, prefix="System", color=None):
    """精致化日志输出"""
    ICONS = {
        "System": "⚙️ ", "Success": "✅", "Error": "❌",
        "Warning": "⚠️ ", "Env": "🌐", "Browser": "🔌",
        "Action": "🎯", "Info": "💡",
    }
    COLORS = {
        "System": Colors.GRAY, "Success": Colors.GREEN, "Error": Colors.RED,
        "Warning": Colors.YELLOW, "Env": Colors.CYAN, "Browser": Colors.PURPLE,
        "Action": Colors.BLUE, "Info": Colors.GRAY,
    }
    c = color or COLORS.get(prefix, Colors.GRAY)
    icon = ICONS.get(prefix, "📝")
    t = time.strftime("%H:%M:%S")
    print(f"{c}[{t}] {icon} {msg}{Colors.RESET}", flush=True)


# ==============================================================================
# 📦 数据结构
# ==============================================================================
@dataclass
class AdsEnvironment:
    """单个 ADS 浏览器环境"""
    user_id: str
    serial_number: str = ""
    name: str = ""
    group_name: str = ""
    domain_name: str = ""
    ws_url: str = ""
    browser: Optional[Browser] = field(default=None, repr=False)
    context: Optional[BrowserContext] = field(default=None, repr=False)
    pages: List[Page] = field(default_factory=list, repr=False)
    connected: bool = False
    raw_data: Dict = field(default_factory=dict, repr=False)

    @property
    def display_name(self):
        return self.name or self.domain_name or f"环境-{self.serial_number}"

    @property
    def status_icon(self):
        return "🟢" if self.connected else "⚪"


# ==============================================================================
# 🧩 核心管理器
# ==============================================================================
class AdsEnvManager:
    """ADS 多环境管理器"""

    def __init__(self, port: str = "50325"):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.envs: Dict[str, AdsEnvironment] = {}
        self._playwright = None
        self._pw_instance = None
        # 静音参数
        self.launch_args = '%5B%22--disable-features%3DHardwareMediaKeyHandling%22%2C%22--mute-audio%22%5D'

    # ------------------------------------------------------------------
    # 发现环境
    # ------------------------------------------------------------------
    def discover(self) -> List[AdsEnvironment]:
        """发现所有 AdsPower 浏览器环境"""
        log("正在扫描 AdsPower 环境...", "Env")
        try:
            url = f"{self.base_url}/api/v1/user/list?page=1&page_size=100"
            resp = requests.get(url, timeout=10).json()
            if resp.get("code") != 0:
                log(f"API 错误: {resp.get('msg', '未知错误')}", "Error")
                return []

            profiles = resp.get("data", {}).get("list", [])
            log(f"发现 {len(profiles)} 个浏览器环境", "Success")

            for p in profiles:
                uid = p.get("user_id", "")
                if uid not in self.envs:
                    self.envs[uid] = AdsEnvironment(
                        user_id=uid,
                        serial_number=str(p.get("serial_number", "")),
                        name=p.get("name", ""),
                        group_name=p.get("group_name", ""),
                        domain_name=p.get("domain_name", ""),
                        raw_data=p,
                    )
                else:
                    # 更新已有信息
                    env = self.envs[uid]
                    env.name = p.get("name", env.name)
                    env.serial_number = str(p.get("serial_number", env.serial_number))
                    env.group_name = p.get("group_name", env.group_name)
                    env.domain_name = p.get("domain_name", env.domain_name)
                    env.raw_data = p

            return list(self.envs.values())

        except requests.ConnectionError:
            log("无法连接 AdsPower！请确认 AdsPower 客户端已打开。", "Error")
            return []
        except Exception as e:
            log(f"发现环境时出错: {e}", "Error")
            return []

    # ------------------------------------------------------------------
    # 启动 & 接管
    # ------------------------------------------------------------------
    def _ensure_playwright(self):
        """确保 Playwright 实例存在"""
        if self._pw_instance is None:
            self._playwright = sync_playwright().start()
            self._pw_instance = self._playwright

    def open_browser(self, user_id: str) -> bool:
        """启动并接管指定环境的浏览器"""
        env = self.envs.get(user_id)
        if not env:
            log(f"未找到环境: {user_id}", "Error")
            return False

        if env.connected:
            log(f"[{env.display_name}] 已处于连接状态", "Warning")
            return True

        try:
            # 1. 调用 AdsPower API 启动浏览器
            log(f"[{env.display_name}] 正在启动浏览器...", "Browser")
            api_url = f"{self.base_url}/api/v1/browser/start?user_id={user_id}&launch_args={self.launch_args}"
            resp = requests.get(api_url, timeout=30).json()

            if resp.get("code") != 0:
                log(f"[{env.display_name}] 启动失败: {resp.get('msg', '未知')}", "Error")
                return False

            ws_url = resp["data"]["ws"]["puppeteer"]
            env.ws_url = ws_url
            log(f"[{env.display_name}] 获取 WebSocket: {ws_url[:60]}...", "Browser")

            # 2. 通过 Playwright CDP 接管
            self._ensure_playwright()
            browser = self._pw_instance.chromium.connect_over_cdp(ws_url)
            env.browser = browser
            env.context = browser.contexts[0] if browser.contexts else None
            env.pages = list(env.context.pages) if env.context else []
            env.connected = True

            page_urls = [p.url[:50] for p in env.pages[:3]]
            log(f"[{env.display_name}] ✅ 接管成功！{len(env.pages)} 个页面: {page_urls}", "Success")
            return True

        except Exception as e:
            log(f"[{env.display_name}] 接管失败: {e}", "Error")
            env.connected = False
            return False

    def open_all(self) -> Dict[str, bool]:
        """批量启动并接管所有环境"""
        if not self.envs:
            self.discover()

        results = {}
        total = len(self.envs)
        for i, (uid, env) in enumerate(self.envs.items(), 1):
            log(f"📡 正在接管 {i}/{total}: {env.display_name} ({uid})", "Action")
            results[uid] = self.open_browser(uid)
            if i < total:
                time.sleep(2)  # 间隔2秒，避免过快启动

        connected = sum(1 for v in results.values() if v)
        log(f"批量接管完成: {connected}/{total} 个环境已连接", "Success")
        return results

    def close_browser(self, user_id: str) -> bool:
        """关闭指定环境的浏览器"""
        env = self.envs.get(user_id)
        if not env:
            log(f"未找到环境: {user_id}", "Error")
            return False

        try:
            # 断开 Playwright 连接
            if env.browser:
                try:
                    env.browser.close()
                except:
                    pass

            # 调用 AdsPower API 关闭
            api_url = f"{self.base_url}/api/v1/browser/stop?user_id={user_id}"
            requests.get(api_url, timeout=10)

            env.browser = None
            env.context = None
            env.pages = []
            env.connected = False
            env.ws_url = ""
            log(f"[{env.display_name}] 浏览器已关闭", "Success")
            return True

        except Exception as e:
            log(f"[{env.display_name}] 关闭失败: {e}", "Error")
            return False

    def close_all(self):
        """关闭所有环境"""
        for uid in list(self.envs.keys()):
            self.close_browser(uid)
        log("所有环境已关闭", "Success")

    # ------------------------------------------------------------------
    # 操作命令
    # ------------------------------------------------------------------
    def _get_env(self, identifier: str) -> Optional[AdsEnvironment]:
        """通过 user_id 或序号查找环境"""
        # 优先精确匹配 user_id
        if identifier in self.envs:
            return self.envs[identifier]
        # 尝试序号匹配
        for env in self.envs.values():
            if env.serial_number == identifier:
                return env
        # 尝试名称匹配
        for env in self.envs.values():
            if env.display_name == identifier:
                return env
        return None

    def _get_connected_env(self, identifier: str) -> Optional[AdsEnvironment]:
        """查找已连接的环境"""
        env = self._get_env(identifier)
        if not env:
            log(f"未找到环境: {identifier}", "Error")
            return None
        if not env.connected:
            log(f"[{env.display_name}] 未连接，请先 open", "Warning")
            return None
        return env

    def goto(self, identifier: str, url: str):
        """导航到指定 URL"""
        env = self._get_connected_env(identifier)
        if not env:
            return
        try:
            page = env.pages[0] if env.pages else env.context.new_page()
            log(f"[{env.display_name}] 正在导航到: {url}", "Action")
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            # 刷新页面列表
            env.pages = list(env.context.pages) if env.context else []
            log(f"[{env.display_name}] ✅ 导航完成: {page.title()}", "Success")
        except Exception as e:
            log(f"[{env.display_name}] 导航失败: {e}", "Error")

    def goto_all(self, url: str):
        """所有环境导航到同一 URL"""
        for uid, env in self.envs.items():
            if env.connected:
                self.goto(uid, url)
                time.sleep(1)

    def screenshot(self, identifier: str, save_dir: str = "/Users/fly/Desktop"):
        """截图"""
        env = self._get_connected_env(identifier)
        if not env or not env.pages:
            return
        try:
            page = env.pages[0]
            filename = f"ads_screenshot_{env.serial_number}_{int(time.time())}.png"
            filepath = os.path.join(save_dir, filename)
            page.screenshot(path=filepath, full_page=False)
            log(f"[{env.display_name}] 截图已保存: {filepath}", "Success")
        except Exception as e:
            log(f"[{env.display_name}] 截图失败: {e}", "Error")

    def screenshot_all(self, save_dir: str = "/Users/fly/Desktop"):
        """所有环境截图"""
        for uid, env in self.envs.items():
            if env.connected:
                self.screenshot(uid, save_dir)

    def exec_js(self, identifier: str, js_code: str):
        """在指定环境执行 JavaScript"""
        env = self._get_connected_env(identifier)
        if not env or not env.pages:
            return
        try:
            page = env.pages[0]
            result = page.evaluate(js_code)
            log(f"[{env.display_name}] JS 执行结果:", "Success")
            print(f"  → {json.dumps(result, ensure_ascii=False, indent=2) if result else '(无返回值)'}")
        except Exception as e:
            log(f"[{env.display_name}] JS 执行失败: {e}", "Error")

    def exec_js_all(self, js_code: str):
        """所有环境执行 JavaScript"""
        for uid, env in self.envs.items():
            if env.connected:
                self.exec_js(uid, js_code)

    def get_cookies(self, identifier: str):
        """获取指定环境的 cookies"""
        env = self._get_connected_env(identifier)
        if not env or not env.context:
            return
        try:
            cookies = env.context.cookies()
            log(f"[{env.display_name}] 获取到 {len(cookies)} 个 cookies:", "Success")
            for c in cookies[:10]:
                print(f"  🍪 {c.get('name', '?')[:30]} = {str(c.get('value', ''))[:40]}... ({c.get('domain', '')})")
            if len(cookies) > 10:
                print(f"  ... 还有 {len(cookies) - 10} 个 cookies")
        except Exception as e:
            log(f"[{env.display_name}] 获取 cookies 失败: {e}", "Error")

    def get_page_info(self, identifier: str):
        """获取指定环境的页面信息"""
        env = self._get_connected_env(identifier)
        if not env:
            return
        # 更新页面列表
        env.pages = list(env.context.pages) if env.context else []
        if not env.pages:
            log(f"[{env.display_name}] 没有打开的页面", "Warning")
            return
        for i, page in enumerate(env.pages):
            try:
                title = page.title()[:50] if page.title() else "(无标题)"
                url = page.url[:80]
                print(f"  📄 页面 {i}: {title}")
                print(f"       URL: {url}")
            except:
                print(f"  📄 页面 {i}: (已关闭或无法访问)")

    # ------------------------------------------------------------------
    # 状态显示
    # ------------------------------------------------------------------
    def show_status(self):
        """显示所有环境状态"""
        if not self.envs:
            log("尚未发现任何环境，请先运行 discover", "Warning")
            return

        print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}  🌐 ADS 指纹浏览器环境面板  ({len(self.envs)} 个环境){Colors.RESET}")
        print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
        print(f"  {'序号':<6} {'状态':<4} {'名称':<20} {'User ID':<15} {'当前页面'}")
        print(f"  {'─'*6} {'─'*4} {'─'*20} {'─'*15} {'─'*25}")

        for env in sorted(self.envs.values(), key=lambda e: e.serial_number):
            # 获取当前主页面 URL
            page_url = ""
            if env.connected and env.pages:
                try:
                    env.pages = list(env.context.pages) if env.context else env.pages
                    page_url = env.pages[0].url[:35] if env.pages else ""
                except:
                    page_url = "(访问错误)"

            name_display = env.display_name[:18]
            print(f"  {env.serial_number:<6} {env.status_icon:<4} {name_display:<20} {env.user_id:<15} {page_url}")

        connected = sum(1 for e in self.envs.values() if e.connected)
        print(f"\n  {Colors.GREEN}已连接: {connected}{Colors.RESET} / {Colors.DIM}总计: {len(self.envs)}{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*70}{Colors.RESET}\n")

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------
    def cleanup(self):
        """清理所有资源"""
        log("正在清理资源...", "System")
        for uid, env in self.envs.items():
            if env.browser:
                try:
                    env.browser.close()
                except:
                    pass
                env.connected = False
        if self._playwright:
            try:
                self._playwright.stop()
            except:
                pass
        log("资源清理完毕", "Success")


# ==============================================================================
# 🎮 交互式命令行界面
# ==============================================================================
def print_help():
    """打印帮助信息"""
    print(f"""
{Colors.BOLD}📋 可用命令:{Colors.RESET}

  {Colors.CYAN}环境管理:{Colors.RESET}
    list / ls              列出所有环境及状态
    discover / scan        重新扫描 AdsPower 环境
    open <id>              启动并接管指定环境 (id = 序号 / user_id / 名称)
    open all               启动并接管所有环境
    close <id>             关闭指定环境
    close all              关闭所有环境

  {Colors.CYAN}浏览器操作:{Colors.RESET}
    goto <id> <url>        导航到指定 URL
    goto all <url>         所有环境导航到同一 URL
    screenshot <id>        截取指定环境的截图到桌面
    screenshot all         所有环境截图
    pages <id>             查看指定环境的所有页面信息
    cookies <id>           获取指定环境的 cookies
    exec <id> <js>         在指定环境执行 JavaScript
    exec all <js>          在所有环境执行 JavaScript

  {Colors.CYAN}其他:{Colors.RESET}
    help / h / ?           显示帮助
    quit / exit / q        退出程序
""")


def interactive_loop(manager: AdsEnvManager):
    """交互式命令行主循环"""
    print(f"""
{Colors.BOLD}{Colors.CYAN}
╔══════════════════════════════════════════════════╗
║      🌐 ADS 指纹浏览器 多环境管理器 v1.0       ║
╚══════════════════════════════════════════════════╝
{Colors.RESET}""")

    # 自动发现
    manager.discover()
    manager.show_status()
    print(f"  💡 输入 {Colors.BOLD}help{Colors.RESET} 查看所有命令\n")

    while True:
        try:
            raw = input(f"{Colors.GREEN}ads>{Colors.RESET} ").strip()
            if not raw:
                continue

            parts = raw.split(maxsplit=2)
            cmd = parts[0].lower()

            # ---- 退出 ----
            if cmd in ("quit", "exit", "q"):
                manager.cleanup()
                log("再见! 👋", "System")
                break

            # ---- 帮助 ----
            elif cmd in ("help", "h", "?"):
                print_help()

            # ---- 列表 ----
            elif cmd in ("list", "ls"):
                manager.show_status()

            # ---- 发现 ----
            elif cmd in ("discover", "scan"):
                manager.discover()
                manager.show_status()

            # ---- 打开 ----
            elif cmd == "open":
                if len(parts) < 2:
                    log("用法: open <id> 或 open all", "Warning")
                elif parts[1].lower() == "all":
                    manager.open_all()
                    manager.show_status()
                else:
                    manager.open_browser(parts[1])
                    manager.show_status()

            # ---- 关闭 ----
            elif cmd == "close":
                if len(parts) < 2:
                    log("用法: close <id> 或 close all", "Warning")
                elif parts[1].lower() == "all":
                    manager.close_all()
                    manager.show_status()
                else:
                    manager.close_browser(parts[1])
                    manager.show_status()

            # ---- 导航 ----
            elif cmd == "goto":
                if len(parts) < 3:
                    log("用法: goto <id> <url> 或 goto all <url>", "Warning")
                elif parts[1].lower() == "all":
                    manager.goto_all(parts[2])
                else:
                    # 可能 URL 在第3个参数
                    url = parts[2] if len(parts) > 2 else ""
                    manager.goto(parts[1], url)

            # ---- 截图 ----
            elif cmd == "screenshot":
                if len(parts) < 2:
                    log("用法: screenshot <id> 或 screenshot all", "Warning")
                elif parts[1].lower() == "all":
                    manager.screenshot_all()
                else:
                    manager.screenshot(parts[1])

            # ---- 页面 ----
            elif cmd == "pages":
                if len(parts) < 2:
                    log("用法: pages <id>", "Warning")
                else:
                    manager.get_page_info(parts[1])

            # ---- Cookies ----
            elif cmd == "cookies":
                if len(parts) < 2:
                    log("用法: cookies <id>", "Warning")
                else:
                    manager.get_cookies(parts[1])

            # ---- JS 执行 ----
            elif cmd == "exec":
                if len(parts) < 3:
                    log("用法: exec <id> <javascript> 或 exec all <javascript>", "Warning")
                elif parts[1].lower() == "all":
                    manager.exec_js_all(parts[2])
                else:
                    manager.exec_js(parts[1], parts[2])

            else:
                log(f"未知命令: {cmd}。输入 help 查看帮助。", "Warning")

        except KeyboardInterrupt:
            print()
            manager.cleanup()
            log("已中断 (Ctrl+C)。再见! 👋", "System")
            break
        except EOFError:
            manager.cleanup()
            break
        except Exception as e:
            log(f"命令执行出错: {e}", "Error")
            traceback.print_exc()


# ==============================================================================
# 🚀 入口
# ==============================================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ADS 指纹浏览器 多环境管理器")
    parser.add_argument("--port", default="50325", help="AdsPower 本地 API 端口 (默认 50325)")
    args = parser.parse_args()

    manager = AdsEnvManager(port=args.port)

    # 优雅退出
    def signal_handler(sig, frame):
        print()
        manager.cleanup()
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    interactive_loop(manager)
