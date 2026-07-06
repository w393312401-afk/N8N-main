# 🛠️ 独立辅助工具说明

> 本目录面向进阶用户，所有工具均为独立脚本，不依赖运行中的主服务（除 `test_api.py`）。

---

## 工具列表

### 📡 `watcher.py` — 跨沙盒 IPC 任务监听器

**用途**：当 AI 助手（运行于沙盒中）无法直接调用 `127.0.0.1` 时，通过写文件 → 监听文件的方式实现跨沙盒通信。

```bash
# 启动监听（需先编辑脚本顶部的 WATCH_DIR 和 API_URL）
python3 watcher.py
```

工作流程：
1. AI 助手将 JSON 任务文件写入 `WATCH_DIR`
2. `watcher.py` 检测到新文件后，转发至本地 API
3. 转发完成后删除任务文件

---

### 🖥️ `ads_env_manager.py` — AdsPower 多环境交互管理器

**用途**：以终端 TUI 界面查看和管理 AdsPower 所有浏览器环境（批量启动/停止/查询）。

```bash
python3 ads_env_manager.py
```

---

### 🧪 `test_api.py` — API 集成测试

**用途**：验证服务所有接口是否正常响应，需要服务已启动。

```bash
# 通过 mac/run_test.sh 运行（推荐）
bash ../mac/run_test.sh

# 或直接运行
python3 test_api.py
```
