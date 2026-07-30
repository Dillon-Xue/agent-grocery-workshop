"""组装 CLI：根据需求文档从零件库检索匹配、冲突二选一、依赖补全。

AI 撰写最终 Skill 正文由 agent 运行时完成；本脚本输出确定性的
零件选用结果（selected / skipped / added），供 agent 拼装使用。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workshop import Workshop  # noqa


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: python assemble.py <skill-root> <requirements.json> [top_k]")
        return 1
    root = sys.argv[1]
    req_path = sys.argv[2]
    top_k = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    with open(req_path, "r", encoding="utf-8") as f:
        requirements = json.load(f)
    ws = Workshop(root)
    result = ws.assemble(requirements, top_k=top_k)
    print(json.dumps({
        "selected_ids": [p["id"] for p in result["selected"]],
        "skipped_conflicts": result["skipped_conflicts"],
        "added_dependencies": result["added_dependencies"],
        "notes": result["notes"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
