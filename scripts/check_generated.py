#!/usr/bin/env python3
from pathlib import Path
for d in ["每日早安问候", "json_格式化助手", "会议纪要提炼", "代码注释生成器", "旅行清单打包"]:
    p = Path("generations") / d / "SKILL.md"
    raw = p.read_bytes()
    has_literal = b"\\n" in raw
    has_newline = b"\n" in raw
    lines = len(p.read_text(encoding="utf-8").splitlines())
    print(f"{d}: literal_backslash_n={has_literal}, actual_newline={has_newline}, lines={lines}")
