# -*- coding: utf-8 -*-
"""
🧩 FFmpeg 视频合并服务
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
使用 FFmpeg 合并多个视频片段。
"""

import os
import subprocess

from config import OUTPUT_DIR
from models import MergeRequest
from utils.logger import log
from services.manifest import append_event, read_manifest, write_manifest


def _has_audio(video_path) -> bool:
    """使用 ffprobe 检测视频文件是否包含音频流"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            video_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        return "audio" in res.stdout.lower()
    except Exception:
        return False


def _get_atempo_filter(speed: float) -> str:
    """生成合法的 FFmpeg atempo 滤镜链 (解决 atempo 限制在 [0.5, 2.0] 之间的限制)"""
    filters = []
    temp = speed
    while temp > 2.0:
        filters.append("atempo=2.0")
        temp /= 2.0
    while temp < 0.5:
        filters.append("atempo=0.5")
        temp /= 0.5
    if temp != 1.0:
        filters.append(f"atempo={temp}")
    return ",".join(filters)


async def merge_videos_logic(request: MergeRequest):
    log(f"🎬 收到视频合并请求: {len(request.video_paths)} 个片段, speed={request.speed}", "VideoMerge")
    
    # 1. 验证输入
    if not request.video_paths:
        log("🎬 视频合并请求：未提供视频文件路径，跳过合并操作", "VideoMerge")
        return {"status": "success", "skipped": True, "message": "No video paths provided"}
        
    valid_paths = []
    for path in request.video_paths:
        if path.startswith("http"):
            log(f"⚠️ 跳过远程路径 (需先下载): {path}", "Warning")
            continue
            
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            valid_paths.append(abs_path)
        else:
            log(f"⚠️ 文件不存在，跳过: {abs_path}", "Warning")
            
    if len(valid_paths) < 1:
        return {"status": "error", "message": "No valid local video files found"}

    # 单文件无需合并，但如果需要调速，仍然需要处理
    speed = request.speed if request.speed > 0 else 1.0
    if len(valid_paths) == 1 and speed == 1.0:
        log(f"✅ 仅一个视频且无需调速，直接返回: {valid_paths[0]}", "VideoMerge")
        return {"status": "success", "output_path": valid_paths[0], "url": valid_paths[0], "skipped": True}

    # 2. 确定输出目录
    out_dir = request.output_dir.strip() if request.output_dir else ""
    if not out_dir:
        out_dir = os.path.dirname(valid_paths[0]) or OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    # 3. 创建 concat 文件列表
    import time as _time
    ts = int(_time.time() * 1000)
    list_path = os.path.join(out_dir, f"ffmpeg_concat_{ts}.txt")
    list_content = ""
    for path in valid_paths:
        safe_path = path.replace("'", "'\\''") 
        list_content += f"file '{safe_path}'\n"
    
    try:
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(list_content)
    except Exception as e:
        return {"status": "error", "message": f"Failed to write list file: {str(e)}"}
        
    # 4. 准备输出路径
    filename = request.output_filename
    if not filename.endswith(".mp4"):
        filename += ".mp4"
    # 确保文件名唯一
    base, ext = os.path.splitext(filename)
    output_path = os.path.join(out_dir, f"{base}_{ts}{ext}")
    
    # 5. 调用 FFmpeg
    def _run_ffmpeg(cmd_args):
        return subprocess.run(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )
    
    try:
        run_reencode = True
        result = None
        
        # 只有在不需要调速（speed == 1.0）时，才尝试快速的 copy 模式
        if speed == 1.0:
            log(f"⚙️ 尝试 copy 模式合并...", "VideoMerge")
            cmd_copy = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                output_path,
            ]
            result = _run_ffmpeg(cmd_copy)
            if result.returncode == 0:
                run_reencode = False
            else:
                log(f"⚠️ copy 模式失败，回退 re-encode: {result.stderr[:300]}", "VideoMerge")
        
        if run_reencode:
            log(f"⚙️ 开始 re-encode 模式合并 (speed={speed})...", "VideoMerge")
            vf_filter = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1"
            if speed != 1.0:
                vf_filter += f",setpts={1.0 / speed}*PTS"
                
            cmd_reencode = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-vf", vf_filter,
                "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            ]
            
            # 检测输入视频是否含有音频流
            has_audio = _has_audio(valid_paths[0])
            if has_audio:
                if speed != 1.0:
                    af_filter = _get_atempo_filter(speed)
                    cmd_reencode.extend(["-af", af_filter])
                cmd_reencode.extend(["-c:a", "aac", "-b:a", "192k"])
            else:
                cmd_reencode.append("-an")  # 无音频流则不生成音频轨道
                
            cmd_reencode.extend(["-movflags", "+faststart", output_path])
            result = _run_ffmpeg(cmd_reencode)
            
            if result.returncode != 0:
                log(f"❌ FFmpeg 合并失败:\n{result.stderr}", "Error")
                _cleanup(list_path)
                return {"status": "error", "message": "FFmpeg merge failed", "details": result.stderr[:1000]}
        
        # 验证输出文件
        if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
            _cleanup(list_path)
            return {"status": "error", "message": "FFmpeg produced empty or missing output file"}
        
        _cleanup(list_path)
        log(f"✅ 视频合并成功: {output_path} ({os.path.getsize(output_path)} bytes)", "VideoMerge")
        manifest_file = ""
        try:
            existing = read_manifest(out_dir)
            manifest_file = write_manifest(out_dir, {
                "output_dir": os.path.abspath(out_dir),
                "kind": existing.get("kind") or "video_batch",
                "status": "merged",
                "merged_video_path": output_path,
                "merged_size": os.path.getsize(output_path),
                "merge_input_paths": valid_paths,
            })
            append_event(out_dir, {
                "type": "merge",
                "status": "success",
                "output_path": output_path,
                "input_count": len(valid_paths),
            })
            log(f"🧾 合并 manifest 已更新: {manifest_file}", "VideoMerge")
        except Exception as manifest_err:
            log(f"⚠️ 合并 manifest 写入失败: {type(manifest_err).__name__}: {manifest_err}", "VideoMerge")
        return {"status": "success", "output_path": output_path, "url": output_path, "manifest_path": manifest_file}
        
    except FileNotFoundError:
        _cleanup(list_path)
        log("❌ 未找到 ffmpeg 命令，请确保已安装 FFmpeg 并添加到 PATH", "Error")
        return {"status": "error", "message": "FFmpeg not installed or not in PATH"}
    except subprocess.TimeoutExpired:
        _cleanup(list_path)
        log("❌ FFmpeg 合并超时 (>600s)", "Error")
        return {"status": "error", "message": "FFmpeg merge timed out (>600s)"}
    except Exception as e:
        _cleanup(list_path)
        log(f"❌ 合并过程异常: {str(e)}", "Error")
        return {"status": "error", "message": str(e)}


def _cleanup(path):
    """安全删除临时文件"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
