from dismantle import parse_skill_to_candidates, CATEGORY_KEYWORDS

FIXTURE = """---
name: 邮件助手
description: 汇总邮件
---
# 邮件助手

简介文字。

## 读取邮件
使用 IMAP 协议读取邮件内容，支持 SSL 连接。

## 单元测试
编写 pytest 用例验证读取逻辑是否正确。
"""


def test_parse_skill(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text(FIXTURE, encoding="utf-8")
    cands = parse_skill_to_candidates(str(p))
    names = [c["name"] for c in cands]
    assert "读取邮件" in names
    assert "单元测试" in names
    by_name = {c["name"]: c for c in cands}
    assert by_name["单元测试"]["category"] == "测试用例"
    assert by_name["读取邮件"]["category"] in CATEGORY_KEYWORDS
    assert by_name["读取邮件"]["content"]
    assert by_name["读取邮件"]["source_skill_name"] == "邮件助手"
