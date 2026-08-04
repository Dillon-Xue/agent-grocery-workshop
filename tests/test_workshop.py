from workshop import Workshop


def test_seed_count(root):
    ws = Workshop(root)
    assert len(ws.load_all_parts()) == 23


def test_search_returns_relevant(root):
    ws = Workshop(root)
    res = ws.search_parts("HTTP 请求 requests")
    ids = [p["id"] for p in res]
    assert "part_cod_001" in ids


def test_search_category_filter(root):
    ws = Workshop(root)
    res = ws.search_parts("模板", category="需求分析")
    assert all(p["category"] == "需求分析" for p in res)


def test_resolve_conflicts_keeps_one(root):
    ws = Workshop(root)
    ws.add_part({"id": "c_a", "name": "方案A", "category": "方案设计", "conflicts_with": ["c_b"], "content": "x"})
    ws.add_part({"id": "c_b", "name": "方案B", "category": "方案设计", "conflicts_with": ["c_a"], "content": "y"})
    kept, skipped = ws.resolve_conflicts([ws.get_part("c_a"), ws.get_part("c_b")])
    assert len(kept) == 1
    assert len(skipped) == 1
    assert kept[0]["id"] != skipped[0]["id"]


def test_resolve_dependencies_closure(root):
    ws = Workshop(root)
    ws.add_part({"id": "base", "name": "基础件", "category": "依赖工具", "content": "x"})
    ws.add_part({"id": "mid", "name": "中间件", "category": "代码开发", "depends_on": ["base"], "content": "y"})
    final, added = ws.resolve_dependencies([ws.get_part("mid")])
    ids = {p["id"] for p in final}
    assert "base" in ids and "mid" in ids


def test_usage_counts_and_reverse(root):
    ws = Workshop(root)
    counts = ws.usage_counts()
    assert counts.get("part_cod_001") == 1
    usages = ws.part_usages("part_cod_001")
    assert any(u["generation_id"] == "gen_weekly" for u in usages)


def test_siblings(root):
    ws = Workshop(root)
    ws.add_part({"id": "s1", "name": "邮件读取", "category": "代码开发", "source_skill_id": "skill_mail", "content": "x"})
    ws.add_part({"id": "s2", "name": "邮件解析", "category": "代码开发", "source_skill_id": "skill_mail", "content": "y"})
    sibs = ws.siblings(ws.get_part("s1"))
    assert any(s["id"] == "s2" for s in sibs)
    # 初始零件无 source_skill_id -> 无同源伙伴
    assert ws.siblings(ws.get_part("part_cod_001")) == []


def test_assemble_end_to_end(root):
    ws = Workshop(root)
    req = {
        "name": "HTTP接口数据抓取",
        "scenario": "从REST接口拉取JSON并保存为文件",
        "inputs": "API地址",
        "outputs": "JSON文件",
        "process": "发送HTTP请求解析JSON写入文件",
        "constraints": "本地运行",
    }
    res = ws.assemble(req, top_k=10)
    sel_ids = [p["id"] for p in res["selected"]]
    assert "part_cod_001" in sel_ids
    assert isinstance(res["notes"], str) and res["notes"]
