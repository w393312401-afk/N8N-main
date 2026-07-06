# Yunwu Cloud API 调用文档：Gemini 图片与 Veo 3.1 Fast 首尾帧视频

本文档只记录云雾云端接口调用。

## 1. 鉴权

云雾 API Key 使用 Bearer Token：

```http
Authorization: Bearer <YUNWU_API_KEY>
```

Gemini 图片接口当前同时传 `x-goog-api-key` 和 URL query `key`：

```http
x-goog-api-key: <YUNWU_API_KEY>
```

```text
?key=<YUNWU_API_KEY>
```

## 2. Gemini 图片生成

接口：

```http
POST https://yunwu.ai/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key=<YUNWU_API_KEY>
```

Headers：

```http
Accept: application/json
Content-Type: application/json
Authorization: Bearer <YUNWU_API_KEY>
x-goog-api-key: <YUNWU_API_KEY>
```

Body：

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "Generate an image of a compact mountain cabin at sunrise."
        }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["IMAGE"],
    "imageConfig": {
      "aspectRatio": "9:16",
      "imageSize": "1K"
    }
  }
}
```

PowerShell curl.exe 示例：

```powershell
$body = @'
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "Generate an image of a compact mountain cabin at sunrise."
        }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["IMAGE"],
    "imageConfig": {
      "aspectRatio": "9:16",
      "imageSize": "1K"
    }
  }
}
'@

curl.exe -X POST "https://yunwu.ai/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key=$env:YUNWU_API_KEY" `
  -H "Accept: application/json" `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer $env:YUNWU_API_KEY" `
  -H "x-goog-api-key: $env:YUNWU_API_KEY" `
  -d $body
```

支持参数：

```text
aspectRatio: 1:1, 1:4, 4:1, 3:2, 2:3, 16:9, 9:16, 4:3, 3:4, 21:9
imageSize: 512, 1K, 2K, 4K
```

当前约束：

```text
prompt 最大 2500 字符
Gemini 当前一次只返回 1 张图
```

## 3. Gemini 图片编辑 / 图生图

图片编辑仍调用同一个 `generateContent` 接口，只是在 `parts` 里追加 `inline_data`。

接口：

```http
POST https://yunwu.ai/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key=<YUNWU_API_KEY>
```

Headers：

```http
Accept: application/json
Content-Type: application/json
Authorization: Bearer <YUNWU_API_KEY>
x-goog-api-key: <YUNWU_API_KEY>
```

Body：

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "Turn this reference image into a clean product-style studio shot."
        },
        {
          "inline_data": {
            "mime_type": "image/png",
            "data": "<BASE64_IMAGE_DATA>"
          }
        }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["IMAGE"],
    "imageConfig": {
      "aspectRatio": "9:16",
      "imageSize": "1K"
    }
  }
}
```

PowerShell curl.exe 示例：

```powershell
$imageBase64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\to\reference.png"))
$body = @{
  contents = @(
    @{
      role = "user"
      parts = @(
        @{
          text = "Turn this reference image into a clean product-style studio shot."
        },
        @{
          inline_data = @{
            mime_type = "image/png"
            data = $imageBase64
          }
        }
      )
    }
  )
  generationConfig = @{
    responseModalities = @("IMAGE")
    imageConfig = @{
      aspectRatio = "9:16"
      imageSize = "1K"
    }
  }
} | ConvertTo-Json -Depth 20

curl.exe -X POST "https://yunwu.ai/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key=$env:YUNWU_API_KEY" `
  -H "Accept: application/json" `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer $env:YUNWU_API_KEY" `
  -H "x-goog-api-key: $env:YUNWU_API_KEY" `
  -d $body
```

## 4. Veo 3.1 Fast 首尾帧视频创建

接口：

```http
POST https://yunwu.ai/v1/videos
```

Headers：

```http
Accept: application/json
Authorization: Bearer <YUNWU_API_KEY>
```

Form fields：

```text
model=veo_3_1-fast
prompt=Use the provided first frame and last frame as exact composition anchors. Animate a smooth restoration timelapse between them.
seconds=8
size=9x16
watermark=false
input_reference=@first-frame.png
input_reference=@last-frame.png
```

PowerShell curl.exe 示例：

```powershell
curl.exe -X POST "https://yunwu.ai/v1/videos" `
  -H "Accept: application/json" `
  -H "Authorization: Bearer $env:YUNWU_API_KEY" `
  -F "model=veo_3_1-fast" `
  -F "prompt=Use the provided first frame and last frame as exact composition anchors. Animate a smooth restoration timelapse between them." `
  -F "seconds=8" `
  -F "size=9x16" `
  -F "watermark=false" `
  -F "input_reference=@C:\path\to\first-frame.png" `
  -F "input_reference=@C:\path\to\last-frame.png"
```

如云雾当前渠道要求数组字段，可把两张参考图字段名改成：

```text
input_reference[]=@first-frame.png
input_reference[]=@last-frame.png
```

支持参数：

```text
model: veo_3_1, veo_3_1-fast
seconds: 4, 8, 12
size: 16x9, 9x16, 1280x720, 720x1280
watermark: true, false
```

首尾帧规则：

```text
第一张 input_reference 是首帧
第二张 input_reference 是尾帧
尾帧不能单独上传，必须同时提供首帧
图片格式建议使用 PNG / JPG / JPEG / WEBP
单张参考图小于 25MB
```

## 5. Veo 任务查询

创建视频任务成功后，响应里会返回视频任务 `id`。

接口：

```http
GET https://yunwu.ai/v1/videos/{video_id}
```

Headers：

```http
Accept: application/json
Authorization: Bearer <YUNWU_API_KEY>
```

PowerShell curl.exe 示例：

```powershell
curl.exe -X GET "https://yunwu.ai/v1/videos/<VIDEO_ID>" `
  -H "Accept: application/json" `
  -H "Authorization: Bearer $env:YUNWU_API_KEY"
```

成功状态：

```text
completed, succeeded
```

失败状态：

```text
failed, cancelled, canceled, expired
```

## 6. Veo 成片下载

接口：

```http
GET https://yunwu.ai/v1/videos/{video_id}/content
```

Headers：

```http
Authorization: Bearer <YUNWU_API_KEY>
```

PowerShell curl.exe 示例：

```powershell
curl.exe -L -X GET "https://yunwu.ai/v1/videos/<VIDEO_ID>/content" `
  -H "Authorization: Bearer $env:YUNWU_API_KEY" `
  -o "veo-output.mp4"
```

## 7. 错误响应

云端错误通常会通过 HTTP 状态码和 JSON body 返回。排查时优先保留原始响应。

常见形态：

```json
{
  "error": {
    "message": "原始错误信息",
    "type": "error_type",
    "code": "error_code"
  }
}
```

也可能是：

```json
{
  "message": "原始错误信息",
  "status": "failed"
}
```
