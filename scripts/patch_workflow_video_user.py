import json
import sqlite3


workflow_id = "13CnpyRAeEwAyv5D"
db_path = r"C:\Users\video\.n8n\database.sqlite"

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT nodes FROM workflow_entity WHERE id = ?", (workflow_id,))
row = cur.fetchone()
if not row:
    raise SystemExit("workflow not found")

nodes = json.loads(row[0])
target_name = "\u914d\u7f6e\u9762\u677f"
updated = False

for node in nodes:
    if node.get("name") != target_name:
        continue
    strings = node.setdefault("parameters", {}).setdefault("values", {}).setdefault("string", [])
    for item in strings:
        if item.get("name") == "videoUserId":
            item["value"] = "={{ $vars.underwater_video_user_id || 'ku07skg' }}"
            updated = True
            break

if not updated:
    raise SystemExit("videoUserId not found")

cur.execute(
    "UPDATE workflow_entity SET nodes = ?, updatedAt = CURRENT_TIMESTAMP WHERE id = ?",
    (json.dumps(nodes, ensure_ascii=False), workflow_id),
)
conn.commit()
conn.close()
print("patched videoUserId fallback to ku07skg")
