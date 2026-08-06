#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成自包含静态 HTML 报告：修复说明 + 5 个真实生成的 Skill 效果展示。
输出：generations/preview.html （不依赖后端，双击即可打开查看）。
"""
import html
import json
import pathlib
import re

ROOT = pathlib.Path("/home/dillon/workbuddy-skills/agent-grocery-workshop")
GEN = ROOT / "generations"
REPORT = GEN / "test_generate_5_skills_report.json"

# ── 读取生成报告 ──
report = json.loads(REPORT.read_text(encoding="utf-8"))

# ── 解析单个 SKILL.md 的 frontmatter ──
def parse_skill(pid):
    p = GEN / pid / "SKILL.md"
    content = p.read_text(encoding="utf-8") if p.exists() else "(未找到 SKILL.md)"
    meta = {"name": pid, "description": "", "tags": []}
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.S)
    if m:
        for line in m.group(1).splitlines():
            if line.startswith("name:"):
                meta["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                meta["description"] = line.split(":", 1)[1].strip()
            elif line.startswith("tags:"):
                t = line.split(":", 1)[1].strip()
                t = t.strip("[]").strip()
                meta["tags"] = [x.strip() for x in t.split(",") if x.strip()]
    return meta, content

skills = []
for item in report:
    meta, content = parse_skill(item["id"])
    skills.append({
        "id": item["id"],
        "name": meta["name"],
        "description": meta["description"],
        "tags": meta["tags"],
        "installed": item.get("installed", False),
        "ok": item.get("ok", False),
        "content": content,
    })

# ── 修复问题数据 ──
fixes = [
    {
        "no": 1,
        "title": "删除 Skill 后列表仍展示 / 报「Skill 不存在」",
        "cause": "handle_skill_delete：当 Skill 目录已被其它方式移除时，直接返回错误，前端不会从列表移除；"
                 "且 send_to_recycle_bin 只支持 Windows PowerShell，在 WSL 服务端运行会抛异常导致删除中断。",
        "fix": "目录已不存在时返回 ok=True, already_removed=True，前端据此同步移除列表项；"
               "send_to_recycle_bin 改为优先 gio trash，其次 trash-put，最后本地回收目录兜底。",
        "verify": "test_delete_fix.py 通过：对真实存在与已移除的 Skill 均返回正确结果。",
        "status": "已修复",
    },
    {
        "no": 2,
        "title": "执行报 401 且错误日志看不到原因",
        "cause": "handle_chat 仅用 except Exception 兜底，HTTP 401 的响应体被吞掉；"
                 "服务未开启文件日志，控制台「日志」面板拿不到任何信息。",
        "fix": "新增文件日志 ~/.workbuddy/logs/agent-grocery-workshop.log；"
               "handle_chat 单独捕获 urllib.error.HTTPError，返回带 HTTP 状态码与响应体的详细错误，"
               "并把请求与错误写入日志。",
        "verify": "test_chat_401_log.py 通过：401 错误信息含状态码，且日志文件中可检索到 /api/chat HTTP 401。",
        "status": "已修复",
    },
    {
        "no": 3,
        "title": "生成 Skill 失败：cannot access local variable 'gdir'",
        "cause": "_run_generation_job 中先构造 gen 字典（引用了 gdir），再调用 record_generation 给 gdir 赋值，"
                 "导致在 gdir 赋值前被引用，抛出 UnboundLocalError；"
                 "另外 fallback 模板把 \\n 写成字面量换行符，生成的 SKILL.md 全挤在一行。",
        "fix": "调整顺序：先算 gdir 再构造 gen；"
               "_build_skill_markdown / _generate_skill_content 中改用真实换行符。",
        "verify": "test_generate_5_skills.py 实际生成 5 个 Skill 全部成功，SKILL.md 换行正常。",
        "status": "已修复",
    },
]

def esc(s):
    return html.escape(str(s))

def skill_cards():
    out = []
    for s in skills:
        tags = " ".join(f'<span class="tag">{esc(t)}</span>' for t in s["tags"]) or '<span class="tag">auto-generated</span>'
        badge = '<span class="badge ok">已生成并安装</span>' if s["installed"] else '<span class="badge">已生成</span>'
        out.append(f"""
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">{esc(s['name'])}</div>
              <div class="card-desc">{esc(s['description'] or '（无描述）')}</div>
            </div>
            {badge}
          </div>
          <div class="card-meta">ID：<code>{esc(s['id'])}</code> &nbsp; 标签：{tags}</div>
          <details>
            <summary>查看完整 SKILL.md</summary>
            <pre>{esc(s['content'])}</pre>
          </details>
        </div>""")
    return "\n".join(out)

def fix_blocks():
    out = []
    for f in fixes:
        out.append(f"""
        <div class="fix">
          <div class="fix-head"><span class="fix-no">问题 {f['no']}</span>
            <span class="fix-title">{esc(f['title'])}</span>
            <span class="badge ok">{esc(f['status'])}</span></div>
          <div class="kv"><b>原因：</b>{esc(f['cause'])}</div>
          <div class="kv"><b>修复：</b>{esc(f['fix'])}</div>
          <div class="kv"><b>验证：</b>{esc(f['verify'])}</div>
        </div>""")
    return "\n".join(out)

html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>agent-grocery-workshop 修复 & 生成实测报告</title>
<style>
  :root {{
    --bg:#f6f8fb; --panel:#fff; --ink:#1f2733; --muted:#6b7785; --line:#e6eaf0;
    --accent:#2f6df0; --ok:#1f9d57; --ok-bg:#e8f7ef; --warn:#d9822b;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:-apple-system,"Segoe UI","Microsoft YaHei",Roboto,Helvetica,Arial,sans-serif;
    line-height:1.6; }}
  header {{ background:linear-gradient(135deg,#2f6df0,#5b8def); color:#fff;
    padding:28px 32px; }}
  header h1 {{ margin:0 0 6px; font-size:22px; }}
  header p {{ margin:0; opacity:.92; font-size:14px; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:24px 20px 60px; }}
  h2 {{ font-size:18px; margin:32px 0 14px; padding-left:10px; border-left:4px solid var(--accent); }}
  .fix {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:16px 18px; margin-bottom:14px; }}
  .fix-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:8px; }}
  .fix-no {{ background:var(--accent); color:#fff; font-size:12px; padding:2px 9px; border-radius:20px; }}
  .fix-title {{ font-weight:600; font-size:15px; }}
  .kv {{ font-size:13.5px; color:#33404f; margin:5px 0; }}
  .kv b {{ color:var(--muted); font-weight:600; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:16px 18px; display:flex; flex-direction:column; }}
  .card-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }}
  .card-title {{ font-size:16px; font-weight:700; }}
  .card-desc {{ font-size:13px; color:var(--muted); margin-top:2px; }}
  .card-meta {{ font-size:12px; color:var(--muted); margin:10px 0; }}
  .card-meta code {{ background:#eef2f7; padding:1px 6px; border-radius:5px; color:#33404f; }}
  .tag {{ display:inline-block; background:#eef2f7; color:#44505f; font-size:11.5px;
    padding:2px 8px; border-radius:20px; margin:2px 4px 2px 0; }}
  .badge {{ font-size:12px; padding:3px 10px; border-radius:20px; white-space:nowrap; }}
  .badge.ok {{ background:var(--ok-bg); color:var(--ok); font-weight:600; }}
  details {{ margin-top:6px; }}
  summary {{ cursor:pointer; font-size:13px; color:var(--accent); user-select:none; }}
  pre {{ background:#0f172a; color:#e2e8f0; padding:14px; border-radius:8px; overflow:auto;
    font-size:12px; line-height:1.5; max-height:420px; white-space:pre-wrap; word-break:break-all; }}
  .verify-box {{ background:var(--ok-bg); border:1px solid #bfe9cf; color:#1d6b41;
    border-radius:10px; padding:14px 18px; font-size:13.5px; }}
  .verify-box code {{ background:#d6f0e0; padding:1px 6px; border-radius:5px; }}
  .note {{ font-size:13px; color:var(--muted); margin-top:10px; }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; padding:24px; }}
</style>
</head>
<body>
<header>
  <h1>WorkBuddy 控制台 · 修复 & 真实生成实测报告</h1>
  <p>本次修复 3 个问题，并真实生成 5 个 Skill 验证效果（测试数据已保留）</p>
</header>
<div class="wrap">

  <h2>一、修复的三个问题</h2>
  {fix_blocks()}

  <h2>二、验证结果</h2>
  <div class="verify-box">
    ✅ <code>python3 -m py_compile scripts/server.py</code> 通过<br>
    ✅ <code>pytest tests -q</code>：19 passed<br>
    ✅ <code>scripts/test_delete_fix.py</code>：删除同步修复通过<br>
    ✅ <code>scripts/test_chat_401_log.py</code>：401 日志修复通过<br>
    ✅ <code>scripts/test_generate_5_skills.py</code>：5 个 Skill 全部生成并安装成功
    <div class="note">提交：<code>45adde1</code> 已 push 到 <code>origin/main</code>。</div>
  </div>

  <h2>三、真实生成的 5 个 Skill 效果</h2>
  <div class="grid">
    {skill_cards()}
  </div>
  <div class="note">
    数据保留位置：<br>
    · 源码侧：<code>/home/dillon/workbuddy-skills/agent-grocery-workshop/generations/&lt;id&gt;/</code><br>
    · WorkBuddy 可见：<code>C:\\Users\\dillon\\.workbuddy\\skills\\&lt;id&gt;\\</code><br>
    · 测试报告：<code>generations/test_generate_5_skills_report.json</code><br>
    · 运行日志：<code>~/.workbuddy/logs/agent-grocery-workshop.log</code>
  </div>

  <h2>四、查看实时控制台（可选）</h2>
  <div class="note">
    如需查看完整交互式控制台（Skill 列表 / 删除 / 执行 / 生成），可启动后端服务：<br>
    <code>cd /home/dillon/workbuddy-skills/agent-grocery-workshop &amp;&amp; python3 scripts/server.py 8765</code><br>
    然后在浏览器打开 <code>http://127.0.0.1:8765/console.html</code>（或经 WSL 端口转发到 Windows 访问）。
  </div>

</div>
<footer>由 WorkBuddy 生成 · agent-grocery-workshop · {len(skills)} 个 Skill 实测</footer>
</body>
</html>"""

out_path = GEN / "preview.html"
out_path.write_text(html_doc, encoding="utf-8")
print("written:", out_path, "size:", out_path.stat().st_size)
print("skills:", [s["name"] for s in skills])
