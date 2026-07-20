# -*- coding: utf-8 -*-
"""
🧪 Google FX 分层拆分 — 导入面回归检查
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
静态校验：google_fx.py / google_fx_helpers.py / google_fx_video.py /
google_fx_image.py / google_fx_task.py / app.py 在每一步搬移后仍能正常
import，且 app.py 与 task_queue.py 实际依赖的模块级名字仍然可解析。

不需要 AdsPower / 真实浏览器，纯静态 import 检查。
用法（从 Adspower/AI/core 目录下运行）:
    python3 ../tools/fx_import_surface_check.py
"""

import importlib
import os
import sys

# 必须从 Adspower/AI/core 目录下运行（app.py / services/* 都用不带包前缀的裸导入，
# 依赖 core/ 本身在 sys.path 上，这是本仓库现有的运行约定，不是本脚本引入的新假设）。
sys.path.insert(0, os.getcwd())

# module_path -> 必须仍可从该模块解析到的属性名列表
# 依据: app.py 用 _load_service_attr("services.google_fx", name) 动态取属性；
#       google_fx_task.py 用 `from services.google_fx import ...` 静态导入。
REQUIRED_SURFACE = {
    "services.google_fx": [
        "_generate_video_google_fx",
        "_generate_videos_batch_google_fx",
        "_generate_images_batch_google_fx",
    ],
    "services.google_fx_task": [
        "run_google_fx_task",
    ],
}


def main():
    failures = []

    for mod_name, required_attrs in REQUIRED_SURFACE.items():
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            failures.append(f"❌ import {mod_name} 失败: {type(e).__name__}: {e}")
            continue
        for attr in required_attrs:
            if not hasattr(mod, attr):
                failures.append(f"❌ {mod_name}.{attr} 缺失")

    # 额外确认 app.py 本身可以被完整 import（触发路由注册等模块级副作用）
    try:
        importlib.import_module("app")
    except Exception as e:
        failures.append(f"❌ import app 失败: {type(e).__name__}: {e}")

    if failures:
        print("\n".join(failures))
        print(f"\n{len(failures)} 项检查未通过")
        sys.exit(1)

    print("✅ 导入面检查全部通过 (services.google_fx / google_fx_task / app 均可正常 import)")


if __name__ == "__main__":
    main()
