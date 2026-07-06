# N8N-main

这是一个围绕 `n8n + AdsPower + AI 自动化` 整理的工作仓库，主要用于本地工作流编排、AdsPower 浏览器自动化，以及配套的提示词/技能沉淀。

目前仓库里的核心内容分成 3 块：

- `Adspower/AI`：基于 FastAPI 的本地 AI 自动化服务，负责对接 AdsPower、浏览器自动化、视频/图片生成和分析接口。
- `Adspower/adspower-browser-main`：AdsPower Local API / MCP 相关代码与说明。
- `N8N-skills`：n8n 使用过程中的技能说明、模式、表达式、节点配置参考。

## 目录结构

```text
N8N-main/
├── Adspower/
│   ├── AI/
│   │   ├── core/                  # FastAPI 主服务与核心逻辑
│   │   ├── mac/                   # macOS 启动脚本
│   │   ├── win/                   # Windows 启动脚本
│   │   ├── tools/                 # 测试、监听、环境管理工具
│   │   └── 工作流文件/             # n8n 工作流示例
│   └── adspower-browser-main/     # AdsPower CLI / MCP 项目
└── N8N-skills/                    # n8n 技能与参考文档
```

## 主要用途

### 1. AdsPower AI 本地服务

`Adspower/AI` 是仓库里最偏业务的一部分，已经整理出较完整的中文说明文档：

- [Adspower/AI/README_CN.md](/Users/fly/Desktop/N8N-main/Adspower/AI/README_CN.md)
- [Adspower/AI/configuration_guide.md](/Users/fly/Desktop/N8N-main/Adspower/AI/configuration_guide.md)
- [Adspower/AI/MAINTENANCE.md](/Users/fly/Desktop/N8N-main/Adspower/AI/MAINTENANCE.md)

它主要提供：

- 视频生成接口
- 图片批量生成接口
- Gemini 分析接口
- 视频合并接口
- AdsPower 环境查询与浏览器自动化支持

常用入口文件：

- [Adspower/AI/core/app.py](/Users/fly/Desktop/N8N-main/Adspower/AI/core/app.py)
- [Adspower/AI/mac/start_server.sh](/Users/fly/Desktop/N8N-main/Adspower/AI/mac/start_server.sh)
- [Adspower/AI/win/start_server.bat](/Users/fly/Desktop/N8N-main/Adspower/AI/win/start_server.bat)

### 2. AdsPower MCP / Local API

`Adspower/adspower-browser-main` 主要用于把 AdsPower Local API 以 MCP 形式接给 AI 工具链，便于通过模型直接操作浏览器环境。

参考文档：

- [Adspower/adspower-browser-main/README.md](/Users/fly/Desktop/N8N-main/Adspower/adspower-browser-main/README.md)

### 3. n8n 技能与参考资料

`N8N-skills` 里保存了常见 n8n 主题的说明文档，例如：

- JavaScript Code 节点
- Python Code 节点
- Expression 语法
- MCP 工具使用
- 节点配置规范
- 工作流模式与校验

适合在设计、排错和复用工作流时查阅。

## 快速开始

### 启动 AdsPower AI 服务

macOS:

```bash
cd /Users/fly/Desktop/N8N-main/Adspower/AI/mac
bash 服务管理.command
```

Windows:

```bat
cd Desktop\N8N-main\Adspower\AI\win
start_server.bat
```

默认服务地址：

```text
http://127.0.0.1:8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/
```

### 一键启动 n8n + 本地 API

macOS:

```bash
cd /Users/fly/Desktop/N8N-main
bash scripts/start_n8n_stack.sh
```

Windows:

```bat
cd Desktop\N8N-main
scripts\start_n8n_stack.bat
```

或直接双击：

```text
/Users/fly/Desktop/N8N-main/启动N8N.command
```

这个入口会先检查并启动 `Adspower/AI` 的本地 FastAPI 服务，再检查并启动 n8n，避免你每次手动分两步启动。

注意：这个项目的 n8n Code 节点会读取本地图片、下载文件和调用 HTTP，所以 Windows 和 macOS 启动 n8n 时都需要带同一组内置模块许可：

```text
NODE_FUNCTION_ALLOW_BUILTIN=os,path,fs,http,https,url,child_process
```

macOS LaunchAgent 会读取 `~/.n8n/n8n.env`，避免后台进程读取 Desktop 路径时被 macOS 权限拦截；`runtime/n8n.env` 保留为仓库内参考副本。Windows 启动脚本仍读取 `runtime/n8n.env`。

更完整的接口示例请看：

- [Adspower/AI/README_CN.md](/Users/fly/Desktop/N8N-main/Adspower/AI/README_CN.md)

## 维护建议

- 当前本机实际使用的 n8n 数据目录是 `~/.n8n`，不再保存在这个仓库里。
- 当前根目录 [`.gitignore`](/Users/fly/Desktop/N8N-main/.gitignore) 规则非常少，后续可以补充日志、数据库和系统临时文件忽略项。
- 如果这个仓库后续需要给别人协作使用，建议再补一份环境依赖清单和启动前置条件说明。

## 当前仓库定位

这个仓库更像一个“本地自动化工作台”而不是单一应用项目。它把以下内容放在了一起：

- AdsPower 自动化服务代码
- 技能与文档资料
- 工作流示例

这种结构很适合个人工作台持续迭代；如果后续要团队协作，建议再按“服务代码 / 文档技能 / 工作流示例”拆分仓库。
