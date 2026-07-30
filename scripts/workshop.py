"""零件杂货铺 核心库。

职责：零件的加载/保存/检索、冲突二选一、依赖闭包补全、
使用热度统计、反向关联（被哪些 Skill 使用）、同源伙伴列表、组装。

纯逻辑，不调用任何 LLM，可在离线环境单测。
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

# 大类 -> 存储子目录（ASCII，避免跨平台编码问题；中文类别写在零件 JSON 的 category 字段）
CATEGORY_DIR = {
    "需求分析": "requirements",
    "方案设计": "design",
    "代码开发": "coding",
    "测试用例": "testing",
    "依赖工具": "tools",
    "参考文档": "reference",
}

CATEGORY_ORDER = ["需求分析", "方案设计", "代码开发", "测试用例", "依赖工具", "参考文档"]


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class Workshop:
    def __init__(self, root: str):
        self.root = root
        self.library_dir = os.path.join(root, "library")
        self.generations_dir = os.path.join(root, "generations")

    # ---------------- 零件持久化 ----------------
    def _iter_part_files(self):
        if not os.path.isdir(self.library_dir):
            return
        for dirpath, _, filenames in os.walk(self.library_dir):
            for fn in filenames:
                if fn.endswith(".json"):
                    yield os.path.join(dirpath, fn)

    def load_all_parts(self) -> list:
        parts = []
        for p in self._iter_part_files():
            try:
                parts.append(_load_json(p))
            except Exception:
                continue
        return parts

    def get_part(self, part_id: str) -> Optional[dict]:
        for p in self._iter_part_files():
            try:
                d = _load_json(p)
            except Exception:
                continue
            if d.get("id") == part_id:
                return d
        return None

    def save_part(self, part: dict) -> str:
        cat = part.get("category")
        sub = CATEGORY_DIR.get(cat, "reference")
        target_dir = os.path.join(self.library_dir, sub)
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, f"{part['id']}.json")
        # 清理其它类别目录下可能存在的同名旧文件（类别被改时）
        for other in CATEGORY_DIR.values():
            if other == sub:
                continue
            stale = os.path.join(self.library_dir, other, f"{part['id']}.json")
            if os.path.isfile(stale):
                os.remove(stale)
        _save_json(target, part)
        return target

    def add_part(self, part: dict) -> str:
        part.setdefault("version", "v1.0")
        part.setdefault("source_type", "initial")
        part.setdefault("content_format", "text")
        part.setdefault("depends_on", [])
        part.setdefault("conflicts_with", [])
        return self.save_part(part)

    # ---------------- 检索 ----------------
    @staticmethod
    def _tokenize(text):
        text = (text or "").lower()
        tokens = re.findall(r"[a-z0-9_]+", text)
        for m in re.finditer(r"[一-鿿]+", text):
            run = m.group(0)
            if len(run) == 1:
                tokens.append(run)
            else:
                for i in range(len(run) - 1):
                    tokens.append(run[i:i + 2])
        return tokens

    def _score(self, part: dict, query: str) -> int:
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return 1
        blob = " ".join(
            str(part.get(k, "")) for k in ("name", "description", "category", "sub_category", "type", "content")
        ).lower()
        score = 0
        for t in q_tokens:
            if t and t in blob:
                score += 1
        name = str(part.get("name", "")).lower()
        for t in q_tokens:
            if t and t in name:
                score += 2
        return score

    def search_parts(self, query: str, top_k: int = 10, category: Optional[str] = None) -> list:
        scored = []
        for part in self.load_all_parts():
            if category and part.get("category") != category:
                continue
            s = self._score(part, query)
            if s > 0:
                scored.append((s, part))
        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored[:top_k]]

    # ---------------- 冲突检测（互斥零件二选一） ----------------
    def resolve_conflicts(self, parts: list) -> tuple:
        conflict_map = {p["id"]: set(p.get("conflicts_with") or []) for p in parts}
        kept, skipped = [], []
        kept_ids = set()
        skipped_ids = set()
        for p in parts:
            pid = p["id"]
            if pid in kept_ids or pid in skipped_ids:
                continue
            if conflict_map[pid] & kept_ids:
                skipped.append(p)
                skipped_ids.add(pid)
                continue
            kept.append(p)
            kept_ids.add(pid)
        # 把与已保留零件互斥、但还没被跳过的零件也标记为跳过
        for p in parts:
            pid = p["id"]
            if pid in kept_ids or pid in skipped_ids:
                continue
            if conflict_map[pid] & kept_ids:
                skipped.append(p)
                skipped_ids.add(pid)
        return kept, skipped

    # ---------------- 依赖补全（闭包） ----------------
    def resolve_dependencies(self, parts: list) -> tuple:
        all_parts = {p["id"]: p for p in self.load_all_parts()}
        selected = {p["id"]: p for p in parts}
        queue = [p["id"] for p in parts]
        added = []
        while queue:
            cid = queue.pop(0)
            part = selected.get(cid) or all_parts.get(cid)
            if not part:
                continue
            for dep in part.get("depends_on") or []:
                if dep not in selected and dep in all_parts:
                    selected[dep] = all_parts[dep]
                    added.append(dep)
                    queue.append(dep)
        return list(selected.values()), added

    # ---------------- 生成记录 / 反向关联 ----------------
    def load_generations(self) -> list:
        gens = []
        if not os.path.isdir(self.generations_dir):
            return gens
        for name in os.listdir(self.generations_dir):
            mpath = os.path.join(self.generations_dir, name, "manifest.json")
            if os.path.isfile(mpath):
                try:
                    gens.append(_load_json(mpath))
                except Exception:
                    continue
        return gens

    def usage_counts(self) -> dict:
        counts = {}
        for g in self.load_generations():
            for pid in g.get("used_part_ids") or []:
                counts[pid] = counts.get(pid, 0) + 1
        return counts

    def part_usages(self, part_id: str) -> list:
        result = []
        for g in self.load_generations():
            if part_id in (g.get("used_part_ids") or []):
                result.append({
                    "generation_id": g.get("id"),
                    "name": g.get("name") or g.get("initial_query"),
                    "created_at": g.get("created_at"),
                })
        return result

    def siblings(self, part: dict) -> list:
        sid = part.get("source_skill_id")
        if not sid:
            return []
        return [
            p
            for p in self.load_all_parts()
            if p.get("id") != part.get("id") and p.get("source_skill_id") == sid
        ]

    # ---------------- 组装 ----------------
    @staticmethod
    def _requirements_to_query(requirements: dict) -> str:
        fields = ("name", "scenario", "inputs", "outputs", "process", "constraints")
        return " ".join(str(requirements.get(f, "")) for f in fields if requirements.get(f))

    def assemble(self, requirements: dict, top_k: int = 10) -> dict:
        query = self._requirements_to_query(requirements)
        candidates = self.search_parts(query, top_k=top_k)
        resolved, skipped_conflicts = self.resolve_conflicts(candidates)
        final, added_deps = self.resolve_dependencies(resolved)
        notes = self._assembly_notes(final, requirements, added_deps, skipped_conflicts)
        return {
            "candidates": candidates,
            "selected": final,
            "skipped_conflicts": skipped_conflicts,
            "added_dependencies": added_deps,
            "notes": notes,
        }

    @staticmethod
    def _assembly_notes(final, requirements, added_deps, skipped_conflicts) -> str:
        lines = [f"根据需求《{requirements.get('name', '未命名')}》检索到 {len(final)} 个匹配零件。"]
        if added_deps:
            lines.append(f"为补齐依赖，自动追加 {len(added_deps)} 个零件：{', '.join(added_deps)}。")
        if skipped_conflicts:
            lines.append(f"检测到互斥，已跳过 {len(skipped_conflicts)} 个冲突零件：{', '.join(p['id'] for p in skipped_conflicts)}。")
        if not skipped_conflicts and not added_deps:
            lines.append("无冲突、无额外依赖，零件可直接组装。")
        return "\n".join(lines)

    # ---------------- 生成记录落盘 ----------------
    def record_generation(self, generation: dict, skill_content: str = "") -> str:
        gid = generation.get("id") or generation.get("name") or "gen"
        gdir = os.path.join(self.generations_dir, gid)
        os.makedirs(gdir, exist_ok=True)
        _save_json(os.path.join(gdir, "manifest.json"), generation)
        if skill_content:
            with open(os.path.join(gdir, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write(skill_content)
        return gdir
