"""轻量 slug 生成器，优先使用 pypinyin 得到中文拼音 slug，未安装时回退到 ASCII。"""
from __future__ import annotations

import re
import uuid


def make_slug(name: str, fallback: str = "skill") -> str:
    """把名称转成 kebab-case 英文 slug。

    - 若安装了 pypinyin，中文字符会自动转拼音。
    - 否则保留 ASCII 字母/数字/空格/下划线，非 ASCII 字符移除。
    - 结果为空时 fallback 为 ``skill-<hex>``，保证合法且唯一。
    """
    base = ""
    try:
        from pypinyin import lazy_pinyin  # type: ignore
        base = " ".join(lazy_pinyin(name or ""))
    except Exception:
        base = re.sub(r"[^a-zA-Z0-9\s_-]", " ", name or "")

    slug = re.sub(r"[\s_]+", "-", base).lower().strip("-")
    slug = re.sub(r"-+", "-", slug)
    if len(slug) < 2:
        slug = f"{fallback}-{uuid.uuid4().hex[:6]}"
    return slug
