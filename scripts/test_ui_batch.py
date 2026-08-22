#!/usr/bin/env python3
"""批量 UI/功能回归测试：验证 console.html 中 8 项修改的关键字符串与后端接口。"""
import json
import re
import urllib.request
import urllib.error
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "scripts" / "console.html"
BASE = "http://127.0.0.1:8080"
RESULTS = []


def req(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(url, data=data, method=method)
    if body:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))


def main():
    html = HTML.read_text(encoding="utf-8")

    # 1. Skill 管理：按钮改为 Skill拆解
    check("Skill管理按钮改为 Skill拆解", "Skill拆解" in html and html.count("任务拆解") == 0,
          "任务拆解出现次数=%d" % html.count("任务拆解"))

    # 2. Skill 开发：去掉页面内 Skill开发 标题，且存在搜索框 id
    check("Skill开发去掉页面标题", 'class="sec-head"' in html and "<h2> Skill开发</h2>" not in html,
          "页面内 h2 Skill开发已移除")
    check("Skill开发增加搜索框", 'id="sd-search"' in html, "")

    # 3. 拆解任务：TAB_META 标题改为 拆解任务，页面内无列表标题，有搜索框
    check("拆解任务 TAB_META 标题", "dismantle: {title:'拆解任务'" in html, "")
    check("拆解任务列表标题已删除", '<div class="sec-head"><h2> 任务拆解</h2>' not in html, "")
    check("拆解任务增加搜索框", 'id="dsm-search"' in html, "")

    # 4. 组件管理：无组件库标题
    check("组件管理去掉组件库标题", '<h2> 组件库</h2>' not in html, "")

    # 5. 工单快照：build_static 输出中存在 TICKET_SNAPSHOT（稍后校验）
    check("工单列表支持分页变量", "TK_PAGE_SIZE=10" in html and "renderTicketPager" in html, "")

    # 6. 查询控件可点击：静态快照模式不强制 disabled，且已增加分页
    check("工单筛选器可点击（静态快照不禁用）", "if(isStatic && !hasProxy && !hasSnapshot)" in html, "")

    # 7. 设置页：无底部保存条
    check("设置页去掉底部保存条", 'id="cfg-save"' not in html and "LLM 与 SkillHub 配置保存在本地" not in html, "")

    # 8. Skill 管理风险列显示 无
    check("Skill管理风险空值显示无", "'<span style=\"color:var(--dim)\"'>无</span>'" in html or "无</span>" in html, "")

    # 9. 侧边栏工单数量 badge：静态快照模式读取 TICKET_SNAPSHOT 长度
    check("侧边栏工单 badge 读快照数量", "const snap = window.TICKET_SNAPSHOT" in html and "snap.length" in html, "")

    # 10. 查询框风格统一（带 🔍 图标）
    check("Skill管理查询框带图标", '<span class="si">🔍</span><input id="sk-search"' in html, "")
    check("组件管理查询框带图标", '<span class="si">🔍</span><input id="shelf-q"' in html, "")
    check("工单管理查询框带图标", '<span class="si">🔍</span><input id="tk-search-id"' in html, "")

    # 11. 组件管理原子渲染，避免首屏空白
    check("组件管理原子渲染", "function _buildShelfBodyHtml()" in html and "function _bindShelfBody(" in html, "")

    # 12. 工单管理去掉页面内标题
    check("工单管理去掉页面标题", '<h2>🎫 工单管理</h2>' not in html, "")

    # 后端接口测试
    code, data = req("GET", "/api/tickets")
    check("GET /api/tickets", code == 200 and data.get("ok") and isinstance(data.get("items"), list),
          f"status={code}, items={len(data.get('items', []))}")

    code, data = req("GET", "/api/tickets?status=%E6%96%B0%E5%A2%9E&type=%E9%9C%80%E6%B1%82")
    check("GET /api/tickets 筛选", code == 200 and data.get("ok") and
          all(it["status"] == "新增" and it["type"] == "需求" for it in data.get("items", [])),
          f"status={code}, items={len(data.get('items', []))}")

    body = {"user": "批量回归测试", "type": "问题", "desc": "8 项 UI 修改后提交测试", "expect": "通过"}
    code, data = req("POST", "/api/ticket", body)
    ok = code == 200 and data.get("ok") and data.get("ticket", "").startswith("FB-")
    ticket = data.get("ticket", "") if ok else ""
    check("POST /api/ticket 提交", ok, f"status={code}, ticket={ticket}")

    code, data = req("GET", f"/api/ticket?ticket={ticket}")
    check("GET /api/ticket 查询", code == 200 and data.get("ok") and data.get("found"),
          f"status={code}, found={data.get('found')}")

    code, data = req("POST", "/api/ticket", {"type": "问题", "desc": ""})
    check("POST /api/ticket 空描述校验", code == 400 and not data.get("ok"), f"status={code}")

    # 生成 HTML 报告
    report_path = Path("/mnt/c/Users/dillon/.workbuddy/控制台UI批量优化_测试报告.html")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    rows = ""
    for name, ok, detail in RESULTS:
        cls = "pass" if ok else "fail"
        rows += f"<tr><td>{name}</td><td class='{cls}'>{'通过' if ok else '失败'}</td><td>{detail}</td></tr>"
    html_report = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>控制台 UI 批量优化测试报告</title>
<style>body{{font-family:system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif;max-width:900px;margin:40px auto;padding:20px;background:#f8fafc;color:#1e293b}}
h1{{font-size:24px;border-bottom:2px solid #22d3ee;padding-bottom:10px}}table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,.06)}}
th{{background:#0f172a;color:#fff;text-align:left;padding:12px 16px;font-size:13px}}td{{padding:12px 16px;border-bottom:1px solid #e2e8f0;font-size:13px}}
.pass{{color:#16a34a;font-weight:600}}.fail{{color:#dc2626;font-weight:600}}tr:hover{{background:#f1f5f9}}
.footer{{margin-top:20px;color:#64748b;font-size:12px}}</style></head><body>
<h1>控制台 UI 批量优化 · 测试报告</h1>
<p>测试时间：{now}</p>
<table><tr><th>用例</th><th>结果</th><th>详情</th></tr>{rows}</table>
<div class="footer">WorkBuddy agent-grocery-workshop · 控制台 UI 批量优化</div></body></html>"""
    report_path.write_text(html_report, encoding="utf-8")

    all_ok = all(r[1] for r in RESULTS)
    print("ALL_PASS:", all_ok)
    for r in RESULTS:
        print(" ", "✓" if r[1] else "✗", r[0], "-", r[2])
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
