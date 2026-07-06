# Yunwu 图像生成调用页

这是一个不依赖 Node 的桌面本地工具：用 FastAPI 提供静态页面和本地代理，浏览器通过本地服务调用 Yunwu 图像接口。

## 运行要求

- Python 3.10+
- 已安装：`fastapi`、`uvicorn`、`requests`

## 最简单的启动方式

Windows 直接双击：

```text
C:\Users\FLY\Desktop\yunwu-image-edit-demo\Launch Yunwu Image Edit Demo.bat
```

macOS 直接双击：

```text
/Users/fly/Desktop/yunwu-image-edit-demo/Launch Yunwu Image Edit Demo.command
```

启动器会自动做这些事：

- 如果本机已有正在运行的服务，直接打开浏览器。
- 如果没有保存 API Key，会弹窗要求输入。
- 你可以选择把 API Key 保存到本地 `.launcher_config.json`。
- 服务就绪后自动打开 `http://127.0.0.1:8000`。
- Win 和 mac 共享同一个 `launcher.py`、同一份配置和同一套静态资源；平台差异只在外层启动脚本。

## 当前支持的模型

- `gpt-image-2-all`
  - 提供方：Yunwu
  - 文生图：`POST https://yunwu.ai/v1/images/generations`
  - 图生图：`POST https://yunwu.ai/v1/images/edits`
- `gemini-3.1-flash-image-preview`
  - 提供方：Yunwu
  - 文生图 / 图生图：`POST https://yunwu.ai/v1beta/models/{model}:generateContent?key=...`
  - 同时发送 `Authorization: Bearer ...`
- `veo_3_1`
  - 提供方：Yunwu
  - 创建视频：`POST https://yunwu.ai/v1/videos`
  - 查询任务：`GET https://yunwu.ai/v1/videos/{video_id}`
  - 下载成片：`GET https://yunwu.ai/v1/videos/{video_id}/content`
- `veo_3_1-fast`
  - 提供方：Yunwu
  - 与 `veo_3_1` 使用同一套视频接口

## API Key 与保存目录

- 后端优先读取 `YUNWU_API_KEY`
- 兼容旧环境变量 `IMAGE_API_KEY`
- 前端“更改密钥”保存的是统一的 `api_key`
- 保存目录按平台分别存储在 `save_dir_by_platform` 里，避免 mac 误用 Windows 路径

## 前端可在线修改的设置

- API Key
  - 前端提供“更改密钥”入口
  - 保存后会立即更新当前服务
  - 可选写回 `.launcher_config.json`
- 保存路径
  - 前端提供“设置保存路径”入口
  - 保存后后续生成文件会自动落盘到该目录
  - 可选写回 `.launcher_config.json`

## 自动保存行为

- 成功响应中如果包含可解析的媒体结果，代理会自动保存到当前设置的保存路径
- 如果上游只返回远程 `url`，本地代理还会继续下载媒体文件后再落盘；若当前网络环境拦截了媒体 CDN，页面预览仍可用，但自动保存会失败
- 当前已支持自动保存这些结果形态：
  - `url`
  - `image_url`
  - `video_url`
  - `file_url`
  - `b64_json`
  - `b64`
  - Gemini `inlineData`
  - Gemini `inline_data`
- 当前界面仍然只生成图片，不提供单独的视频生成流程

## 本地接口

- `GET /api/health`
- `POST /api/settings/api-key`
- `POST /api/settings/save-dir`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/events`
- `POST /api/video-create`
  - 接收 `multipart/form-data`
  - 本地代理会先创建视频任务，再自动轮询状态，完成后自动下载视频到本地保存目录
- `POST /api/image-generate`
  - 接收 `application/json`
  - 立即返回 `202` 与任务信息
- `POST /api/image-edit`
  - 接收 `multipart/form-data`
  - `gpt-image-2-all` 与 Gemini 都使用本地文件上传

## 当前前端行为

- 支持三种工作模式：
  - 文生图
  - 图生图
  - 视频
- 支持在 `gpt-image-2-all` 和 `gemini-3.1-flash-image-preview` 之间切换
- 模型切换时参数区联动变化：
  - `gpt-image-2-all` 显示 `n + size`
  - `gemini-3.1-flash-image-preview` 显示 `aspectRatio + imageSize`
- 视频模式下：
  - 使用 `veo_3_1 / veo_3_1-fast`
  - 允许 0 图文生视频
  - 允许 1 张图作为首帧 / 参考图
  - 允许 2 张图作为首尾帧
  - 本地代理会按 `input_reference` / `input_reference[]` 以及 `-fl` 模型别名做兼容回退
  - 本地代理会自动轮询视频任务状态
  - 任务完成后自动下载成片并写入历史记录
- 默认模型是 `gpt-image-2-all`
- 图生图模式下：
  - 两个模型都继续使用本地参考图
  - `gpt-image-2-all` 额外支持蒙版
- 支持并发提交多个任务
- 历史记录会显示最近批次总生成时长
- 历史记录会同时显示图片和视频
- 任务完成后：
  - 页面展示可预览图片
  - 页面展示可预览视频
  - 页面展示自动保存的本地文件路径
  - 页面展示自动保存失败的详细原因
  - 页面展示历史记录面板
  - 原始 JSON 始终可展开查看

## 已知限制

- 当前全局只有一把活动中的 API Key
- 如果 mac 上只有系统自带 `Python 3.9`，启动器会直接拒绝启动；这不是 bug，是版本不满足运行条件
