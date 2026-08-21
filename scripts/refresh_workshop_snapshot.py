#!/usr/bin/env python3
"""轻量刷新：仅更新 console.html / console_data.json 中的 workshop 数据快照。"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_console import scan_workshop

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "scripts" / "console.html"
JSON = ROOT / "scripts" / "console_data.json"

print("[refresh_workshop_snapshot] scanning workshop...")
workshop = scan_workshop()
print("  parts=%s, categories=%s, generations=%s" % (
    workshop["stats"]["parts"],
    workshop["stats"]["categories"],
    workshop["stats"]["generations"],
))

# 更新 console_data.json
if JSON.exists():
    data = json.load(open(JSON, encoding="utf-8"))
else:
    data = {}
data["workshop"] = workshop
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
emb["workshop"] = workshop
emb["generated_at"] = data["generated_at"]
new_json = json.dumps(emb, ensure_ascii=False, separators=(",", ":"))
html2 = pat.sub(lambda x: x.group(1) + new_json + x.group(3), html)
with open(HTML, "w", encoding="utf-8") as f:
    f.write(html2)
print("  updated %s" % HTML)
