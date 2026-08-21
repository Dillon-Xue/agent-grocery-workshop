#!/usr/bin/env python3
"""轻量刷新：仅更新 console.html / console_data.json 中的 storage 数据快照。

使用 du + bash 快速扫描跨文件系统目录（WSL /mnt/c 挂载的 Windows .workbuddy）。
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_console import STORAGE_CATEGORIES, size_human

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "scripts" / "console.html"
JSON = ROOT / "scripts" / "console_data.json"


def quick_scan(path, timeout=60):
    """返回 (size_bytes, file_count)。"""
    if not os.path.isdir(path):
        return 0, 0
    size_bytes = 0
    try:
        r = subprocess.run(
            ["du", "-sb", path],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode == 0:
            size_bytes = int(r.stdout.split()[0])
    except Exception as e:
        print("  du error for %s: %s" % (path, e))
    file_count = 0
    try:
        cmd = 'find "%s" -type f 2>/dev/null | wc -l' % path.replace('"', '\\"')
        r = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode == 0:
            file_count = int(r.stdout.strip() or 0)
    except Exception as e:
        print("  find error for %s: %s" % (path, e))
    return size_bytes, file_count


print("[refresh_storage_snapshot] scanning storage...")
cats = []
safe_b = cautious_b = skill_b = never_b = 0
for c in STORAGE_CATEGORIES:
    timeout = 120 if c["risk"] == "never" else 60
    sz, cnt = quick_scan(c["path"], timeout=timeout)
    cats.append({
        **c,
        "size_bytes": sz,
        "size_human": size_human(sz),
        "file_count": cnt,
    })
    if c["risk"] == "safe":
        safe_b += sz
    elif c["risk"] == "cautious":
        cautious_b += sz
    elif c["risk"] == "skill":
        skill_b += sz
    else:
        never_b += sz
    print("  %s: %s (%s files)" % (c["name"], size_human(sz), cnt))

total_b = safe_b + cautious_b + skill_b + never_b
summary = {
    "safe_total": size_human(safe_b), "safe_bytes": safe_b,
    "cautious_total": size_human(cautious_b), "cautious_bytes": cautious_b,
    "skill_total": size_human(skill_b), "skill_bytes": skill_b,
    "never_total": size_human(never_b), "never_bytes": never_b,
    "total_bytes": total_b, "total_human": size_human(total_b),
}
print("  total: %s" % size_human(total_b))

# 更新 console_data.json
if JSON.exists():
    data = json.load(open(JSON, encoding="utf-8"))
else:
    data = {}
data["storage"] = {"categories": cats, "summary": summary}
data["overview"] = data.get("overview", {})
data["overview"]["total_storage_bytes"] = total_b
data["overview"]["total_storage"] = summary["total_human"]
data["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
with open(JSON, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("  updated %s" % JSON)

# 更新 console.html 中的 EMBEDDED_DATA
html = open(HTML, encoding="utf-8").read()
pat = re.compile(r"(const EMBEDDED_DATA = )(.*?)(;/\*__WB_DATA_END__\*/)", re.S)
m = pat.search(html)
if not m:
    print("  EMBEDDED_DATA anchor not found")
    sys.exit(1)
emb = json.loads(m.group(2))
emb["storage"] = {"categories": cats, "summary": summary}
emb["overview"] = emb.get("overview", {})
emb["overview"]["total_storage_bytes"] = total_b
emb["overview"]["total_storage"] = summary["total_human"]
emb["generated_at"] = data["generated_at"]
new_json = json.dumps(emb, ensure_ascii=False, separators=(",", ":"))
html2 = pat.sub(lambda x: x.group(1) + new_json + x.group(3), html)
with open(HTML, "w", encoding="utf-8") as f:
    f.write(html2)
print("  updated %s" % HTML)
