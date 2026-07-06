# 📚 AdsPower AI 服务 — 项目说明书

> **版本**: 2.1  
> **更新日期**: 2026-03-24  
> **🌏 服务地址**: `http://127.0.0.1:8000`

---

## 🔰 新手入口

**第一次使用？** 请先阅读 👉 [快速开始.md](./快速开始.md)，5 分钟即可启动服务。

---

## 一、项目简介

本项目是一套基于 **FastAPI + Playwright + AdsPower** 的自动化 API 服务。

它通过浏览器自动化调用 Google FX 等 AI 平台，实现：
- 🎬 **视频生成**（文生视频、图生视频、首尾帧视频）
- 🖼️ **图片生成**（文生图、图生图、批量生成）
- 🔗 **视频合并**（多段视频拼接）

主要配合 **n8n 工作流** 使用。

---

## 二、目录结构

```
AI/
│
├── 📖 快速开始.md            ← 新手从这里开始！
├── 📚 README_CN.md           ← 本文件（详细说明）
├── 🔧 MAINTENANCE.md         ← 维护和排障指南
├── ⚙️ .env                   ← 所有配置在这里修改
│
├── 🍎 mac/                   ← macOS 启动目录（小白关注这里）
│   ├── 服务管理.command       ← 双击启动服务（推荐）
│   ├── run_test.sh            ← 测试脚本
│   └── lib/                  ← 内部库（无需关注）
│       ├── env.sh
│       ├── deps.sh
│       └── server.sh
│
├── 🪟 win/                   ← Windows 启动目录
│   └── start_server.bat      ← 双击启动服务
│
├── ⚙️ core/                  ← 核心代码（⚠️ 小白请勿修改）
│   ├── app.py                ← API 路由注册
│   ├── config.py             ← 参数配置（读取 .env）
│   ├── models.py             ← 请求数据模型
│   ├── ui_selectors.py       ← 浏览器 UI 选择器
│   ├── ads_all_in_one.py     ← 兼容旧版入口
│   ├── utils/                ← 通用工具（日志/浏览器/UI）
│   └── services/             ← 业务逻辑（Google FX / FFmpeg）
│
├── 🛠️ tools/                 ← 独立辅助工具（进阶玩家）
│   ├── ads_env_manager.py    ← AdsPower 多环境管理器
│   ├── watcher.py            ← AI 任务文件夹监听器（跨沙盒 IPC）
│   └── test_api.py           ← API 集成测试脚本
│
├── 🧪 tests/                 ← 测试脚本（和正式代码分开存放）
│   └── test_video_frames.py  ← 首尾帧视频测试
│
├── 📁 logs/                  ← 运行日志（自动生成，超过 10MB 自动轮转为 .bak）
│   ├── server.log            ← 服务运行日志
│   └── startup.log           ← 启动过程日志
│
└── 📁 runtime/               ← 运行时临时文件（自动管理）
```

---

## 三、配置说明（`.env` 文件）

所有配置集中在项目根目录的 `.env` 文件，**小白只需修改这一个文件**。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `SERVER_HOST` | `127.0.0.1` | 服务监听地址（本机访问，一般不用改） |
| `SERVER_PORT` | `8000` | 服务端口（冲突时修改） |
| `ADSPOWER_PORT` | `50325` | AdsPower 本地 API 端口 |
| `ADSPOWER_DEFAULT_USER_ID` | `k1a01try` | 默认使用的 AdsPower 浏览器环境 ID |
| `ADSPWR_OUTPUT_DIR` | `~/Desktop/AI生成` | 生成文件保存目录（留空使用默认） |
| `ADSPWR_RELOAD` | `0` | 热重载开关，开发时可设为 `1` |

---

## 四、可用 AI 模型

### 🎬 视频生成

| 模型 | 平台 | API 路由 | 说明 |
|------|------|----------|------|
| `Veo 3.1` | Google FX | `/generate_video` | 默认，支持参考图 |

### 🖼️ 图片生成

| 模型 | 平台 | 说明 |
|------|------|------|
| `Nano Banana 2` | Google FX (Imagen) | 默认图片模型 |
| `Imagen 3` | Google FX (Imagen) | 高质量图片 |

### 📐 支持的画面比例

`16:9` · `9:16` · `1:1` · `4:3` · `3:4`

---

## 五、API 接口文档

> **交互式文档（推荐）**：服务启动后访问 `http://127.0.0.1:8000/docs`

### 5.1 健康检查

```bash
curl http://127.0.0.1:8000/
```

### 5.2 视频生成（Google FX）

```bash
curl -X POST http://127.0.0.1:8000/generate_video \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "一只猫在海边奔跑",
    "image": "/path/to/reference.jpg",
    "ratio": "16:9",
    "model": "Veo 3.1"
  }'
```

> `image` 字段为可选，留空即为纯文生视频。

### 5.4 批量图片生成

```bash
curl -X POST http://127.0.0.1:8000/generate_images_batch \
  -H "Content-Type: application/json" \
  -d '{
    "prompts": ["赛博朋克风格的猫", "水彩画风格的山水"],
    "images": [],
    "ratio": "1:1",
    "model": "Nano Banana 2"
  }'
```

> `images` 传空数组为纯文生图，传图片路径时作为参考图。

### 5.5 n8n 统一任务入口（Google FX）

这个接口给 n8n 使用，统一返回 `ok/status/error_code/error_message/result_path`，便于工作流做任务锁、失败分类和人工接管。

图片任务：

```bash
curl -X POST http://127.0.0.1:8000/google_fx/run \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "notion-page-id-or-job-id",
    "kind": "image",
    "prompts": ["赛博朋克风格的猫"],
    "images": [],
    "ratio": "1:1",
    "output_path": "/Users/fly/Desktop/AI_video/test/images"
  }'
```

视频任务：

```bash
curl -X POST http://127.0.0.1:8000/google_fx/run \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "notion-page-id-or-job-id",
    "kind": "video",
    "prompt": "一只猫在海边奔跑",
    "image": "/path/to/start.jpg",
    "end_image": "/path/to/end.jpg",
    "ratio": "16:9",
    "output_path": "/Users/fly/Desktop/AI_video/test/videos"
  }'
```

返回示例：

```json
{
  "ok": false,
  "status": "manual_required",
  "task_id": "notion-page-id-or-job-id",
  "kind": "image",
  "result_path": "",
  "result_paths": [],
  "error_code": "login_required",
  "error_message": "Login screen detected",
  "retryable": false
}
```

遇到 `manual_required` 时，n8n 应暂停队列并通知人工处理，不要自动重试。

### 5.6 视频合并

```bash
curl -X POST http://127.0.0.1:8000/merge_videos \
  -H "Content-Type: application/json" \
  -d '{
    "video_paths": ["/path/to/video1.mp4", "/path/to/video2.mp4"],
    "output_filename": "merged_video.mp4"
  }'
```

### 5.6 列出 AdsPower 浏览器环境

```bash
curl "http://127.0.0.1:8000/environments?port=50325"
```

---

## 六、依赖关系图

```
app.py (路由入口)
├── config.py          ← 读取 .env 配置
├── models.py          ← 请求数据结构
├── utils/
│   ├── logger.py      ← 日志工具
│   ├── browser.py     ← 浏览器操作
│   └── ui_helpers.py  ← UI 交互辅助
└── services/
    ├── google_fx.py   ← Google FX 视频/图片逻辑
    └── ffmpeg.py      ← 视频合并逻辑
```

> **规则**：依赖单向流动 `config → utils → services → app`，禁止循环引用。

---

## 七、相关文档

| 文档 | 适合人群 | 内容 |
|------|---------|------|
| [快速开始.md](./快速开始.md) | 🔰 新手 | 5 分钟上手启动 |
| [README_CN.md](./README_CN.md) | 📖 所有人 | 完整项目说明 |
| [MAINTENANCE.md](./MAINTENANCE.md) | 🛠️ 维护者 | 扩展、排障、规范 |
| [结构优化清单.md](./结构优化清单.md) | 🧹 维护者 | 工程清理与结构优化待办 |
