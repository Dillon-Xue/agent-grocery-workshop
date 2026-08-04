"""端到端集成测试：澄清需求 -> 检索组装 -> 落盘生成 -> 拆解回填 -> 解剖图。

验证整条链路在 seed 数据上能闭环跑通，且 generate_shop 产出的 HTML
确实携带数据、内嵌 IIFE 能被 Node 解析（不再发"解析不过的 JS"）。
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from workshop import Workshop  # noqa
from dismantle import parse_skill_to_candidates  # noqa


REQUIREMENT = {
    "name": "GitHub趋势周报生成器",
    "scenario": "每日抓取 GitHub Trending 仓库并生成中文周报",
    "inputs": "GitHub Trending 网页 / API 地址",
    "outputs": "Markdown 周报文件",
    "process": "发送 HTTP 请求抓取页面、解析 JSON、写入本地文件、渲染报告",
    "constraints": "本地运行、无需联网鉴权",
}


def _extract_data_block(html: str) -> dict:
    m = re.search(
        r'<script type="application/json" id="__data">([\s\S]*?)</script>', html
    )
    assert m, "应存在 __data JSON 注入块"
    return json.loads(m.group(1))


def _check_iife_syntax(html: str) -> None:
    iife = re.search(r"<script>([\s\S]*?)</script>", html)
    assert iife, "应存在内嵌 IIFE 脚本块"
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用，跳过 IIFE 语法检查")
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(iife.group(1))
        path = f.name
    try:
        proc = subprocess.run(
            [node, "--check", path], capture_output=True, text=True
        )
        assert proc.returncode == 0, f"内嵌 IIFE 语法错误: {proc.stderr}"
    finally:
        os.unlink(path)


def test_end_to_end_pipeline(root):
    ws = Workshop(root)
    before = len(ws.load_all_parts())

    # 1) 检索组装
    res = ws.assemble(REQUIREMENT, top_k=10)
    sel_ids = [p["id"] for p in res["selected"]]
    assert sel_ids, "组装应至少选出一个零件"

    # 2) 撰写新 SKILL.md 并落盘生成记录
    gid = "gen_trending"
    skill_md = (
        "---\n"
        "name: GitHub趋势周报生成器\n"
        "description: 抓取 GitHub Trending 并生成中文周报\n"
        "---\n"
        "# GitHub趋势周报生成器\n\n"
        "每日自动汇总热门仓库。\n\n"
        "## 抓取趋势\n"
        "使用 HTTP 请求抓取 GitHub Trending 页面，解析返回的 JSON 数据。\n\n"
        "## 生成报告\n"
        "把解析结果渲染为 Markdown 周报并写入本地文件。\n"
    )
    ws.record_generation(
        {
            "id": gid,
            "name": REQUIREMENT["name"],
            "initial_query": REQUIREMENT["scenario"],
            "created_at": "2026-07-30",
            "used_part_ids": sel_ids,
            "auto_dismantled": True,
            "assembly_notes": res["notes"],
        },
        skill_content=skill_md,
    )

    # 3) 自动拆解回填
    gdir = os.path.join(ws.generations_dir, gid)
    cands = parse_skill_to_candidates(os.path.join(gdir, "SKILL.md"))
    assert cands, "拆解应产出候选零件"
    for i, c in enumerate(cands):
        c["id"] = f"auto_{i:02d}_{gid}"
        c["source_type"] = "auto_generated"
        c["source_skill_id"] = gid
        c["source_skill_name"] = REQUIREMENT["name"]
        ws.add_part(c)
    after = len(ws.load_all_parts())
    assert after == before + len(cands), "回填后零件数应增加候选数"

    # 4) 反向关联 / 同源 校验
    assert ws.part_usages(sel_ids[0]), "选中件应被 gen_trending 使用"
    new_part = ws.get_part(cands[0]["id"])
    assert new_part["source_skill_id"] == gid

    # 5) 解剖图：数据闭环 + JS 可解析
    import generate_shop

    html = generate_shop.render(root)
    data = _extract_data_block(html)
    assert gid in [g["id"] for g in data["workshop"]["generations"]]
    assert new_part["id"] in data["workshop"]["parts_by_id"]
    _check_iife_syntax(html)
