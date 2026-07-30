"""拆解引擎（机械解析部分）。

AI 语义归类由 agent 运行时完成；本模块提供确定性的结构化解析：
把 SKILL.md 按 `## ` 章节拆成候选零件，供 agent 审核后回填入库。
"""
from __future__ import annotations

import os
import re
import sys

CATEGORY_KEYWORDS = {
    "代码开发": ["代码", "code", "python", "函数", "实现", "脚本", "api", "调用", "def ", "import "],
    "测试用例": ["测试", "test", "用例", "断言", "pytest", "assert"],
    "需求分析": ["需求", "场景", "痛点", "目标", "用户", "澄清"],
    "方案设计": ["方案", "设计", "架构", "选型", "流程", "模块"],
    "依赖工具": ["依赖", "工具", "配置", "环境", "venv", "docker", "git"],
    "参考文档": ["参考", "规范", "标准", "最佳实践", "文档", "指南"],
}


def guess_category(text: str) -> str:
    low = text.lower()
    best, best_score = "参考文档", 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        score = sum(1 for k in kws if k.lower() in low)
        if score > best_score:
            best, best_score = cat, score
    return best


def parse_skill_to_candidates(skill_md_path: str) -> list:
    """把 SKILL.md 按 `## ` 章节拆成候选零件。"""
    with open(skill_md_path, "r", encoding="utf-8") as f:
        text = f.read()

    fm = {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    body = text[m.end():] if m else text

    matches = list(re.finditer(r"^##\s+(.+)$", body, re.M))
    candidates = []
    skill_name = fm.get("name") or os.path.basename(os.path.dirname(os.path.abspath(skill_md_path)))
    for i, mm in enumerate(matches):
        title = mm.group(1).strip()
        start = mm.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        if not title or not content:
            continue
        combined = f"{title} {content}"
        cat = guess_category(combined)
        if cat in ("需求分析", "方案设计"):
            ptype = "Prompt片段"
        elif cat == "代码开发":
            ptype = "Python代码片段"
        else:
            ptype = "流程规范"
        candidates.append({
            "name": title,
            "description": (content[:80] + "…") if len(content) > 80 else content,
            "category": cat,
            "sub_category": skill_name,
            "type": ptype,
            "content": content,
            "content_format": "markdown",
            "source_type": "dismantled",
            "source_skill_name": skill_name,
            "metadata": {"from_skill": skill_name},
        })
    return candidates


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python dismantle.py <skill.md 路径>")
        return 1
    path = sys.argv[1]
    cands = parse_skill_to_candidates(path)
    print(f"拆出 {len(cands)} 个候选零件：")
    for c in cands:
        print(f"  - [{c['category']}] {c['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
