#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工单列表改造 HTTP 接口测试"""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"


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


def main():
    results = []

    code, data = req("GET", "/api/tickets")
    ok = code == 200 and data.get("ok") and isinstance(data.get("items"), list)
    results.append(("GET /api/tickets 无筛选", ok, "status=" + str(code) + ", items=" + str(len(data.get("items", [])))))

    code, data = req("GET", "/api/tickets?status=%E6%96%B0%E5%A2%9E")
    ok = code == 200 and data.get("ok")
    results.append(("GET /api/tickets?status=新增", ok, "status=" + str(code) + ", items=" + str(len(data.get("items", [])))))

    code, data = req("GET", "/api/tickets?status=%E6%96%B0%E5%A2%9E&type=%E9%9C%80%E6%B1%82")
    ok = code == 200 and data.get("ok") and all(it["status"] == "新增" and it["type"] == "需求" for it in data.get("items", []))
    results.append(("GET /api/tickets?status=新增&type=需求", ok, "status=" + str(code) + ", items=" + str(len(data.get("items", [])))))

    body = {"user": "验收测试", "type": "问题", "desc": "弹窗提交测试", "expect": "通过"}
    code, data = req("POST", "/api/ticket", body)
    ok = code == 200 and data.get("ok") and data.get("ticket", "").startswith("FB-")
    ticket = data.get("ticket", "") if ok else ""
    results.append(("POST /api/ticket 提交工单", ok, "status=" + str(code) + ", ticket=" + ticket))

    code, data = req("GET", "/api/ticket?ticket=" + ticket)
    ok = code == 200 and data.get("ok") and data.get("found") and data["fields"]["desc"] == body["desc"]
    results.append(("GET /api/ticket 查询", ok, "status=" + str(code) + ", found=" + str(data.get("found"))))

    code, data = req("POST", "/api/ticket", {"type": "问题", "desc": ""})
    ok = code == 400 and not data.get("ok")
    results.append(("POST /api/ticket 空描述校验", ok, "status=" + str(code)))

    code, data = req("GET", "/api/tickets")
    ok = code == 200 and any(it["ticket"] == ticket for it in data.get("items", []))
    results.append(("列表包含新提交工单", ok, "contains=" + ticket))

    report_path = "/mnt/c/Users/dillon/.workbuddy/工单列表改造_测试报告.html"
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    rows = ""
    for name, ok, detail in results:
        cls = "pass" if ok else "fail"
        rows += "<tr><td>" + name + "</td><td class=\"" + cls + "\">" + ("通过" if ok else "失败") + "</td><td>" + detail + "</td></tr>"

    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>工单列表改造测试报告</title>'
        '<style>body{font-family:system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif;max-width:900px;margin:40px auto;padding:20px;background:#f8fafc;color:#1e293b}'
        'h1{font-size:24px;border-bottom:2px solid #22d3ee;padding-bottom:10px}table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,.06)}'
        'th{background:#0f172a;color:#fff;text-align:left;padding:12px 16px;font-size:13px}td{padding:12px 16px;border-bottom:1px solid #e2e8f0;font-size:13px}'
        '.pass{color:#16a34a;font-weight:600}.fail{color:#dc2626;font-weight:600}tr:hover{background:#f1f5f9}'
        '.footer{margin-top:20px;color:#64748b;font-size:12px}</style></head><body>'
        '<h1>工单管理列表改造 · 测试报告</h1>'
        '<p>测试时间：' + now + '</p>'
        '<table><tr><th>用例</th><th>结果</th><th>详情</th></tr>' + rows + '</table>'
        '<div class="footer">WorkBuddy agent-grocery-workshop · 飞书多维表格工单管理</div></body></html>'
    )
    open(report_path, "w", encoding="utf-8").write(html)

    all_ok = all(r[1] for r in results)
    print("ALL_PASS:", all_ok)
    for r in results:
        print("  ", "✓" if r[1] else "✗", r[0], "-", r[2])
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
