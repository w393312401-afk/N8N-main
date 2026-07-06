# -*- coding: utf-8 -*-
"""Small local manifest helpers for media generation recovery."""

import json
import os
import time
from typing import Any, Dict, Optional


MANIFEST_NAME = "video_manifest.json"


def manifest_path(output_dir: str) -> str:
    return os.path.join(os.path.abspath(output_dir), MANIFEST_NAME)


def read_manifest(output_dir: str) -> Dict[str, Any]:
    path = manifest_path(output_dir)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def write_manifest(output_dir: str, updates: Dict[str, Any]) -> str:
    os.makedirs(output_dir, exist_ok=True)
    current = read_manifest(output_dir)
    current.update(updates)
    current["manifest_path"] = manifest_path(output_dir)
    current["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    path = manifest_path(output_dir)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
    return path


def append_event(output_dir: str, event: Dict[str, Any]) -> str:
    current = read_manifest(output_dir)
    events = current.get("events")
    if not isinstance(events, list):
        events = []
    payload = dict(event)
    payload["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    events.append(payload)
    return write_manifest(output_dir, {"events": events[-50:]})


def build_manifest_response(output_dir: str, include_files: bool = True) -> Dict[str, Any]:
    data = read_manifest(output_dir)
    data.setdefault("output_dir", os.path.abspath(output_dir))
    data.setdefault("manifest_path", manifest_path(output_dir))
    data["exists"] = os.path.exists(data["manifest_path"])
    if include_files:
        data["local_mp4_files"] = sorted(
            os.path.join(os.path.abspath(output_dir), name)
            for name in os.listdir(output_dir)
            if name.lower().endswith(".mp4")
        ) if os.path.isdir(output_dir) else []
    return data
