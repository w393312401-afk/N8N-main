# Flow2API 可用模型说明

更新时间：2026-06-07

本说明书基于本机 Flow2API 当前接口结果生成：

```bash
curl -sS -H "Authorization: Bearer <FLOW2API_API_KEY>" \
  http://localhost:8080/v1/models
```

当前接口返回模型总数：191。

注意：`/v1/models` 表示 Flow2API 当前代码暴露的模型 ID；实际能否生成，还取决于 Token 是否活跃、Token 是否具备对应模型权限，以及上游服务当时是否可用。

## n8n 中在哪里填写

工作流：`1Ukwp7HPeCTi7KVS`，名称：`已有首尾帧-Flow2API - Notion触发`

默认视频模型在 `统一配置` 节点：

```js
videoModel: 'veo_3_1_i2v_s_fast_portrait_fl'
```

Notion Prompt JSON 可以覆盖默认值：

```json
{
  "video": {
    "model": "veo_3_1_i2v_s_fast_portrait_fl"
  }
}
```

或：

```json
{
  "videoModel": "veo_3_1_i2v_s_fast_portrait_fl"
}
```

最终请求发送前，`Flow API 视频生成` 节点会根据首帧方向自动选择横屏/竖屏后缀。已有首尾帧工作流优先使用 `i2v` 或 `interpolation` 类型模型。

## 常用选择

- 已有首尾帧、竖屏、速度优先：`veo_3_1_i2v_s_fast_portrait_fl`
- 已有首尾帧、横屏、速度优先：`veo_3_1_i2v_s_fast_fl`
- 已有首尾帧、竖屏、Omni 10 秒：`gemini_omni_flash_i2v_10s_portrait`
- 已有首尾帧、横屏、Omni 10 秒：`gemini_omni_flash_i2v_10s_landscape`
- 文生视频、竖屏、Omni 10 秒：`gemini_omni_flash_t2v_10s_portrait`
- 视频转视频、竖屏、Omni 10 秒：`gemini_omni_flash_v2v_10s_portrait`

## 图片模型

### Gemini 3.0 Pro Image

```text
gemini-3.0-pro-image-four-three
gemini-3.0-pro-image-four-three-2k
gemini-3.0-pro-image-four-three-4k
gemini-3.0-pro-image-landscape
gemini-3.0-pro-image-landscape-2k
gemini-3.0-pro-image-landscape-4k
gemini-3.0-pro-image-portrait
gemini-3.0-pro-image-portrait-2k
gemini-3.0-pro-image-portrait-4k
gemini-3.0-pro-image-square
gemini-3.0-pro-image-square-2k
gemini-3.0-pro-image-square-4k
gemini-3.0-pro-image-three-four
gemini-3.0-pro-image-three-four-2k
gemini-3.0-pro-image-three-four-4k
```

### Gemini 3.1 Flash Image

```text
gemini-3.1-flash-image-four-three
gemini-3.1-flash-image-four-three-2k
gemini-3.1-flash-image-four-three-4k
gemini-3.1-flash-image-landscape
gemini-3.1-flash-image-landscape-2k
gemini-3.1-flash-image-landscape-4k
gemini-3.1-flash-image-portrait
gemini-3.1-flash-image-portrait-2k
gemini-3.1-flash-image-portrait-4k
gemini-3.1-flash-image-square
gemini-3.1-flash-image-square-2k
gemini-3.1-flash-image-square-4k
gemini-3.1-flash-image-three-four
gemini-3.1-flash-image-three-four-2k
gemini-3.1-flash-image-three-four-4k
```

### Imagen

```text
imagen-4.0-generate-preview-landscape
imagen-4.0-generate-preview-portrait
```

## 最新 Omni 视频模型

当前本机 Flow2API 已暴露 `gemini_omni_flash_*` 系列，覆盖 `t2v`、`i2v`、`v2v`，时长为 4s、6s、8s、10s，方向为 landscape/portrait。

```text
gemini_omni_flash_i2v_10s_landscape
gemini_omni_flash_i2v_10s_portrait
gemini_omni_flash_i2v_4s_landscape
gemini_omni_flash_i2v_4s_portrait
gemini_omni_flash_i2v_6s_landscape
gemini_omni_flash_i2v_6s_portrait
gemini_omni_flash_i2v_8s_landscape
gemini_omni_flash_i2v_8s_portrait
gemini_omni_flash_t2v_10s_landscape
gemini_omni_flash_t2v_10s_portrait
gemini_omni_flash_t2v_4s_landscape
gemini_omni_flash_t2v_4s_portrait
gemini_omni_flash_t2v_6s_landscape
gemini_omni_flash_t2v_6s_portrait
gemini_omni_flash_t2v_8s_landscape
gemini_omni_flash_t2v_8s_portrait
gemini_omni_flash_v2v_10s_landscape
gemini_omni_flash_v2v_10s_portrait
gemini_omni_flash_v2v_4s_landscape
gemini_omni_flash_v2v_4s_portrait
gemini_omni_flash_v2v_6s_landscape
gemini_omni_flash_v2v_6s_portrait
gemini_omni_flash_v2v_8s_landscape
gemini_omni_flash_v2v_8s_portrait
```

## Veo 3.1 T2V 模型

T2V 是 text-to-video，适合纯文本生成视频，不适合当前“已有首尾帧”工作流作为首选。

```text
veo_3_1_t2v_1080p
veo_3_1_t2v_4k
veo_3_1_t2v_4s
veo_3_1_t2v_4s_1080p
veo_3_1_t2v_4s_4k
veo_3_1_t2v_6s
veo_3_1_t2v_6s_1080p
veo_3_1_t2v_6s_4k
veo_3_1_t2v_fast_1080p
veo_3_1_t2v_fast_4k
veo_3_1_t2v_fast_4s
veo_3_1_t2v_fast_6s
veo_3_1_t2v_fast_landscape
veo_3_1_t2v_fast_landscape_4s
veo_3_1_t2v_fast_landscape_6s
veo_3_1_t2v_fast_portrait
veo_3_1_t2v_fast_portrait_1080p
veo_3_1_t2v_fast_portrait_4k
veo_3_1_t2v_fast_portrait_4s
veo_3_1_t2v_fast_portrait_6s
veo_3_1_t2v_fast_portrait_ultra
veo_3_1_t2v_fast_portrait_ultra_1080p
veo_3_1_t2v_fast_portrait_ultra_4k
veo_3_1_t2v_fast_portrait_ultra_relaxed
veo_3_1_t2v_fast_ultra
veo_3_1_t2v_fast_ultra_1080p
veo_3_1_t2v_fast_ultra_4k
veo_3_1_t2v_fast_ultra_relaxed
veo_3_1_t2v_landscape
veo_3_1_t2v_landscape_1080p
veo_3_1_t2v_landscape_4k
veo_3_1_t2v_landscape_4s
veo_3_1_t2v_landscape_4s_1080p
veo_3_1_t2v_landscape_4s_4k
veo_3_1_t2v_landscape_6s
veo_3_1_t2v_landscape_6s_1080p
veo_3_1_t2v_landscape_6s_4k
veo_3_1_t2v_lite_4s_landscape
veo_3_1_t2v_lite_4s_portrait
veo_3_1_t2v_lite_6s_landscape
veo_3_1_t2v_lite_6s_portrait
veo_3_1_t2v_lite_landscape
veo_3_1_t2v_lite_landscape_4s
veo_3_1_t2v_lite_landscape_6s
veo_3_1_t2v_lite_portrait
veo_3_1_t2v_lite_portrait_4s
veo_3_1_t2v_lite_portrait_6s
veo_3_1_t2v_portrait
veo_3_1_t2v_portrait_1080p
veo_3_1_t2v_portrait_4k
veo_3_1_t2v_portrait_4s
veo_3_1_t2v_portrait_4s_1080p
veo_3_1_t2v_portrait_4s_4k
veo_3_1_t2v_portrait_6s
veo_3_1_t2v_portrait_6s_1080p
veo_3_1_t2v_portrait_6s_4k
```

## Veo 3.1 I2V 模型

I2V 是 image-to-video，适合当前图片到视频流程。带 `_fl` 的模型用于 first/last frame 场景。

```text
veo_3_1_i2v_lite_4s_landscape
veo_3_1_i2v_lite_4s_portrait
veo_3_1_i2v_lite_6s_landscape
veo_3_1_i2v_lite_6s_portrait
veo_3_1_i2v_lite_landscape
veo_3_1_i2v_lite_landscape_4s
veo_3_1_i2v_lite_landscape_6s
veo_3_1_i2v_lite_portrait
veo_3_1_i2v_lite_portrait_4s
veo_3_1_i2v_lite_portrait_6s
veo_3_1_i2v_s_1080p
veo_3_1_i2v_s_4k
veo_3_1_i2v_s_4s
veo_3_1_i2v_s_4s_1080p
veo_3_1_i2v_s_4s_4k
veo_3_1_i2v_s_6s
veo_3_1_i2v_s_6s_1080p
veo_3_1_i2v_s_6s_4k
veo_3_1_i2v_s_fast_4s_fl
veo_3_1_i2v_s_fast_6s_fl
veo_3_1_i2v_s_fast_fl
veo_3_1_i2v_s_fast_landscape_4s_fl
veo_3_1_i2v_s_fast_landscape_6s_fl
veo_3_1_i2v_s_fast_portrait_4s_fl
veo_3_1_i2v_s_fast_portrait_6s_fl
veo_3_1_i2v_s_fast_portrait_fl
veo_3_1_i2v_s_fast_portrait_ultra_fl
veo_3_1_i2v_s_fast_portrait_ultra_fl_1080p
veo_3_1_i2v_s_fast_portrait_ultra_fl_4k
veo_3_1_i2v_s_fast_portrait_ultra_relaxed
veo_3_1_i2v_s_fast_ultra_fl
veo_3_1_i2v_s_fast_ultra_fl_1080p
veo_3_1_i2v_s_fast_ultra_fl_4k
veo_3_1_i2v_s_fast_ultra_relaxed
veo_3_1_i2v_s_landscape
veo_3_1_i2v_s_landscape_1080p
veo_3_1_i2v_s_landscape_4k
veo_3_1_i2v_s_landscape_4s
veo_3_1_i2v_s_landscape_4s_1080p
veo_3_1_i2v_s_landscape_4s_4k
veo_3_1_i2v_s_landscape_6s
veo_3_1_i2v_s_landscape_6s_1080p
veo_3_1_i2v_s_landscape_6s_4k
veo_3_1_i2v_s_portrait
veo_3_1_i2v_s_portrait_1080p
veo_3_1_i2v_s_portrait_4k
veo_3_1_i2v_s_portrait_4s
veo_3_1_i2v_s_portrait_4s_1080p
veo_3_1_i2v_s_portrait_4s_4k
veo_3_1_i2v_s_portrait_6s
veo_3_1_i2v_s_portrait_6s_1080p
veo_3_1_i2v_s_portrait_6s_4k
```

## Veo 3.1 Interpolation 模型

Interpolation 适合首尾帧插帧/过渡场景。

```text
veo_3_1_interpolation_lite_4s_landscape
veo_3_1_interpolation_lite_4s_portrait
veo_3_1_interpolation_lite_6s_landscape
veo_3_1_interpolation_lite_6s_portrait
veo_3_1_interpolation_lite_landscape
veo_3_1_interpolation_lite_landscape_4s
veo_3_1_interpolation_lite_landscape_6s
veo_3_1_interpolation_lite_portrait
veo_3_1_interpolation_lite_portrait_4s
veo_3_1_interpolation_lite_portrait_6s
```

## Veo 3.1 R2V 模型

R2V 是 reference-to-video 类型，通常用于带参考素材的视频生成。

```text
veo_3_1_r2v_fast
veo_3_1_r2v_fast_landscape
veo_3_1_r2v_fast_landscape_ultra
veo_3_1_r2v_fast_landscape_ultra_1080p
veo_3_1_r2v_fast_landscape_ultra_4k
veo_3_1_r2v_fast_landscape_ultra_relaxed
veo_3_1_r2v_fast_portrait
veo_3_1_r2v_fast_portrait_ultra
veo_3_1_r2v_fast_portrait_ultra_1080p
veo_3_1_r2v_fast_portrait_ultra_4k
veo_3_1_r2v_fast_portrait_ultra_relaxed
veo_3_1_r2v_fast_ultra
veo_3_1_r2v_fast_ultra_1080p
veo_3_1_r2v_fast_ultra_4k
veo_3_1_r2v_fast_ultra_relaxed
```

## Veo 3.1 Extend 模型

Extend 用于视频续写。

```text
veo_3_1_extend
veo_3_1_extend_portrait
```

## 源码位置

Flow2API 模型配置表：

```text
/Users/fly/.gemini/antigravity-ide/scratch/flow2api/src/services/generation_handler.py
```

模型别名与横竖屏解析：

```text
/Users/fly/.gemini/antigravity-ide/scratch/flow2api/src/core/model_resolver.py
```

重新生成本说明书时，建议优先用 `/v1/models` 接口，因为它反映当前正在运行的 Flow2API 进程，而不是磁盘上某个旧 checkout 的静态文件。
