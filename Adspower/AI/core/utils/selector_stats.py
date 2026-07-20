# -*- coding: utf-8 -*-
"""
📊 选择器命中层级统计
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
多级 fallback 选择器每次命中时记录"第几层命中"。主选择器开始失效时
（命中层级整体后移、miss 增多），可以在流程还没坏的时候提前发现 UI 变化，
而不是等所有兜底都挂了才整体失败。

数据落盘 runtime/selector_stats.json，由烟雾测试与人工排查读取。
统计写入绝不允许影响主流程：所有异常一律吞掉。
"""

import json
import os
import threading
import time

_LOCK = threading.Lock()
_STATS = None


def stats_file_path():
    override = os.environ.get("ADSPWR_SELECTOR_STATS_FILE", "").strip()
    if override:
        return override
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "runtime", "selector_stats.json")


def _load():
    global _STATS
    if _STATS is not None:
        return _STATS
    try:
        with open(stats_file_path(), "r", encoding="utf-8") as f:
            _STATS = json.load(f)
        if not isinstance(_STATS, dict):
            _STATS = {}
    except Exception:
        _STATS = {}
    return _STATS


def _persist(stats):
    path = stats_file_path()
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def record_hit(family, index, selector="", total=0):
    """记录一次选择器族的命中情况。

    family:   选择器族名（如 'orientation_tab'），未提供时调用方一般用首个选择器
    index:    命中的层级序号，0 = 主选择器；-1 = 全部未命中
    selector: 实际命中的选择器字符串
    total:    该族的总层数
    """
    try:
        with _LOCK:
            stats = _load()
            entry = stats.setdefault(str(family)[:120], {"hits": {}, "miss": 0})
            if index < 0:
                entry["miss"] = entry.get("miss", 0) + 1
            else:
                key = str(index)
                entry.setdefault("hits", {})[key] = entry["hits"].get(key, 0) + 1
                if selector:
                    entry["last_selector"] = str(selector)[:200]
            if total:
                entry["total_layers"] = total
            entry["last_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _persist(stats)
    except Exception:
        pass


def summarize():
    """返回统计摘要：主选择器命中率下降或 miss 偏高的族排在前面。"""
    try:
        with _LOCK:
            stats = json.loads(json.dumps(_load()))
    except Exception:
        return []
    rows = []
    for family, entry in stats.items():
        hits = entry.get("hits", {}) or {}
        total_hits = sum(hits.values())
        primary = hits.get("0", 0)
        miss = entry.get("miss", 0)
        rows.append({
            "family": family,
            "total_hits": total_hits,
            "primary_ratio": (primary / total_hits) if total_hits else 0.0,
            "miss": miss,
            "last_at": entry.get("last_at", ""),
            "last_selector": entry.get("last_selector", ""),
        })
    rows.sort(key=lambda r: (r["primary_ratio"], -r["miss"]))
    return rows
