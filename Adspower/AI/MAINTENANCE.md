# 🔧 维护与排障指南 — AdsPower AI 服务

> 本文档面向维护者和进阶用户，包含扩展功能、排查问题和代码规范说明。  
> 小白用户遇到问题请先查阅 [快速开始.md](./快速开始.md)。

---

## 一、快速排障（常见问题速查）

### 🔴 服务无法启动

| 现象 | 原因 | 解决方法 |
|------|------|---------|
| `Address already in use` | 端口 8000 被占用 | 修改 `.env` 中的 `SERVER_PORT`，或终止占用进程 |
| `ModuleNotFoundError` | Python 依赖缺失 | 运行 `pip3 install fastapi uvicorn playwright requests python-dotenv python-multipart` |
| `Python 不是命令` | Python 未安装 | 去 [python.org](https://www.python.org) 下载安装，勾选 "Add to PATH" |
| `ffmpeg: command not found` | ffmpeg 未安装 | Mac: `brew install ffmpeg`  Win: 下载后加入系统 PATH |

### 🟡 服务启动但功能异常

| 现象 | 原因 | 解决方法 |
|------|------|---------|
| `ads_power_api_reachable: false` | AdsPower 未打开 | 启动 AdsPower 桌面客户端 |
| `超时未检测到视频/图片` | AI 平台 UI 改版或网络慢 | 更新 `core/ui_selectors.py` 选择器，或增大 `.env` → `MAX_WAIT_SECONDS` |
| `Send button disabled` | 文件上传未完成 | 检查参考图路径是否正确，增大上传等待时间 |
| 下载的视频/图片大小为 0 | blob URL 过期 | 检查 `services/google_fx.py` 中下载逻辑 |

### 🔵 查看错误日志

```bash
# 实时查看服务日志（推荐）
tail -f /Users/fly/Desktop/N8N-main/Adspower/AI/logs/server.log

# 只看错误行
grep "❌\|ERROR\|Exception" /Users/fly/Desktop/N8N-main/Adspower/AI/logs/server.log | tail -30

# 查看启动日志
cat /Users/fly/Desktop/N8N-main/Adspower/AI/logs/startup.log
```

### 🔵 错误截图位置

当关键 UI 元素找不到时，系统自动保存截图到：

```
~/Desktop/AI生成/Errors/error_YYYYMMDD_HHMMSS.png
```

---

## 二、如何更新 UI 选择器

当 AI 平台更新了网页界面，自动化操作可能会失败。修复方法：

1. **定位问题**：查看日志中的 `❌` 错误，打开错误截图确认是哪个元素找不到
2. **打开浏览器调试**：在 AdsPower 浏览器里手动访问平台，右键元素 → 检查
3. **更新选择器**：编辑 `core/ui_selectors.py`，修改对应平台的选择器

```python
# 示例：ui_selectors.py 结构
UI_SELECTORS = {
    "google_fx": {
        "prompt_input": [
            'textarea[placeholder*="anything"]',  # 优先级最高
            'div[contenteditable="true"]',         # 备用
            'textarea',                            # 兜底
        ],
        # ... 其他选择器
    },
}
```

> 💡 每个选择器列表按优先级排列，`robust_click()` / `robust_fill()` 会依次尝试。

4. **重启服务**后重新测试。

---

## 三、如何添加新的 AI 平台

以添加 **Midjourney** 为例，只需 3 步：

### 第 1 步：创建服务文件

```python
# core/services/midjourney.py

from config import MAX_WAIT_SECONDS, OUTPUT_DIR
from models import VideoRequest
from utils.logger import log
from utils.browser import get_ads_ws_url, find_or_create_page

def _generate_video_midjourney(req: VideoRequest):
    result = {"status": "failed", "video_url": None, "message": ""}
    # ... 你的 Midjourney 自动化逻辑 ...
    return result
```

### 第 2 步：在 `app.py` 注册路由

```python
from services.midjourney import _generate_video_midjourney

@app.post("/generate_video_midjourney")
def generate_video_mj(req: VideoRequest):
    return _generate_video_midjourney(req)
```

### 第 3 步（可选）：接入统一路由

```python
# 修改 app.py 中的 generate_video_unified，让 /generate_video 支持新平台
@app.post("/generate_video")
def generate_video_unified(req: VideoRequest):
    model_name = req.model.lower() if req.model else ""
    if "midjourney" in model_name:
        return _generate_video_midjourney(req)
    else:
        return _generate_video_google_fx(req)
```

> ✅ **无需修改** `config.py`、`utils/`、其他 `services/` 文件。

---

## 四、代码规范

### 4.1 文件职责分工

| 层 | 文件 | ✅ 应该包含 | ❌ 不应该包含 |
|---|------|-----------|-------------|
| 配置层 | `config.py` | 常量、超时、路径 | 业务逻辑 |
| 模型层 | `models.py` | Pydantic 模型定义 | 数据处理逻辑 |
| 工具层 | `utils/*.py` | 通用、可复用函数 | 平台专属逻辑 |
| 服务层 | `services/*.py` | 特定平台业务逻辑 | 路由定义、FastAPI 装饰器 |
| 入口层 | `app.py` | 路由注册、中间件 | 具体业务实现 |

### 4.2 新增工具函数的规则

- 函数**只有一个服务用到** → 放在对应 `services/xxx.py` 内部
- 函数**被多个服务共用** → 放在 `utils/` 下合适的文件中

### 4.3 依赖方向（禁止循环引用）

```
config.py  →  utils/  →  services/  →  app.py
               ↑
          ui_selectors.py
```

---

## 五、测试

```bash
# 1. 静态检查：验证模块能正常导入
cd /Users/fly/Desktop/N8N-main/Adspower/AI/core
PYTHONPATH=. python3 -c "from app import app; print('✅ 导入成功:', app.title)"

# 2. 路由检查：验证所有路由已注册
cd /Users/fly/Desktop/N8N-main/Adspower/AI/core
PYTHONPATH=. python3 -c "
from app import app
routes = [r.path for r in app.routes]
for r in ['/', '/generate_video', '/merge_videos', '/environments']:
    print('  ✅' if r in routes else '  ❌', r)
"

# 3. API 集成测试（需要服务已启动 + AdsPower 已打开）
bash /Users/fly/Desktop/N8N-main/Adspower/AI/mac/run_test.sh
```

---

## 六、launchd 常驻服务（macOS 高级用法）

通过 `mac/服务管理.command` 菜单操作即可，以下命令用于手动排障：

```bash
# 查看服务状态
launchctl print gui/$(id -u)/com.fly.adspower.ai.api

# 手动停止
launchctl bootout gui/$(id -u)/com.fly.adspower.ai.api

# 重新加载
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.fly.adspower.ai.api.plist
```

---

## 七、部署检查清单

启动前确认以下各项：

- [ ] AdsPower 桌面客户端已打开
- [ ] 目标 AdsPower 浏览器环境已存在（默认 `k1a01try`，可用 `/environments` 接口查看）
- [ ] Python 3 已安装（`python3 --version`）
- [ ] 所有 Python 依赖已安装（`pip3 list | grep -E "fastapi|uvicorn|playwright"`）
- [ ] `ffmpeg` 已安装（`ffmpeg -version`）
- [ ] `OUTPUT_DIR` 目录可写（默认 `~/Desktop/AI生成/`）
- [ ] 服务端口（默认 8000）未被其他程序占用（`lsof -i :8000`）
