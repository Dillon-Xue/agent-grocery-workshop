"""解剖图生成器 v2 — 稳健版：零件库 + 生成记录 → 自包含 HTML。

数据通过 <script type="application/json"> 注入，浏览器原生 JSON 解析。
JS 有完整 try/catch 错误边界。零服务、零端口、离线可用。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workshop import Workshop, CATEGORY_ORDER  # noqa


def build_data(root: str) -> dict:
    ws = Workshop(root)
    parts = ws.load_all_parts()
    counts = ws.usage_counts()
    enriched = []
    for p in parts:
        pid = p["id"]
        enriched.append({
            **p,
            "usage_count": counts.get(pid, 0),
            "usages": ws.part_usages(pid),
            "siblings": [
                {"id": s["id"], "name": s["name"], "category": s["category"], "sub_category": s.get("sub_category")}
                for s in ws.siblings(p)
            ],
        })
    categories = []
    for cat in CATEGORY_ORDER:
        cat_parts = [p for p in enriched if p.get("category") == cat]
        subs = {}
        for p in cat_parts:
            sub = p.get("sub_category") or "\u672a\u5206\u7c7b"
            subs.setdefault(sub, []).append(p)
        categories.append({"name": cat, "count": len(cat_parts), "subs": subs})
    gen_view = []
    for g in ws.load_generations():
        gen_view.append({
            "id": g.get("id"),
            "name": g.get("name") or g.get("initial_query"),
            "created_at": g.get("created_at"),
            "used_part_ids": g.get("used_part_ids", []),
            "notes": g.get("assembly_notes") or g.get("notes", ""),
            "auto_dismantled": g.get("auto_dismantled", False),
        })
    return {
        "stats": {"parts": len(enriched), "generations": len(gen_view), "categories": len(categories)},
        "categories": categories,
        "generations": gen_view,
        "parts_by_id": {p["id"]: p for p in enriched},
    }


# Template uses a placeholder; we inject JSON after.
TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>零件杂货铺 · 解剖图</title>
<style>
  :root{
    --bg:#050a14; --bg2:#080e1c;
    --panel:rgba(0,212,255,.04); --panel2:rgba(0,212,255,.02);
    --solid:#0c1428; --border:rgba(0,212,255,.12);
    --text:#e0f4ff; --text2:#8ba4c4; --muted:#4a6a8a;
    --accent:#00d4ff; --accent2:#00ffa3;
    --good:#00e676; --warn:#ffab00; --bad:#ff4081;
    --c0:#00d4ff; --c1:#a855f7; --c2:#00e676; --c3:#ffab00; --c4:#ff4081; --c5:#ff6e40;
    --r:14px; --r2:10px;
    --glow:0 0 30px rgba(0,212,255,.08);
  }
  @media(prefers-color-scheme:no-preference){
    :root{--bg:#f5f7fa;--bg2:#fff;--panel:rgba(0,0,0,.03);--panel2:rgba(0,0,0,.02);
      --solid:#fff;--border:rgba(0,0,0,.08);--text:#1a2332;--text2:#556677;--muted:#99aab8;
      --accent:#0891b2;--accent2:#059669;--c0:#0891b2;--c1:#7c3aed;--c2:#059669;--c3:#d97706;--c4:#db2777;--c5:#ea580c;
      --glow:0 0 20px rgba(0,0,0,.04);}
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    background:var(--bg);color:var(--text);min-height:100vh;line-height:1.55;
    background-image:radial-gradient(ellipse at 20% 0%,rgba(0,212,255,.06) 0%,transparent 50%),
      radial-gradient(ellipse at 80% 100%,rgba(168,85,247,.05) 0%,transparent 50%);
  }
  .header{padding:28px 32px 18px;display:flex;align-items:center;gap:16px}
  .logo{width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,var(--c0),var(--c1));
    display:grid;place-items:center;font-size:26px;flex-shrink:0;
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.12),var(--glow)}
  .htitle h1{font-size:22px;font-weight:800;background:linear-gradient(90deg,var(--c0),var(--c1),var(--c2));
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
  .htitle p{font-size:12px;color:var(--muted);margin-top:2px}
  .stats-row{display:flex;gap:12px;margin-left:auto}
  .stat-pill{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    padding:8px 16px;text-align:center;min-width:90px}
  .stat-pill b{display:block;font-size:20px;color:var(--accent);font-weight:800}
  .stat-pill small{font-size:11px;color:var(--muted)}
  .nav{padding:0 32px;display:flex;align-items:center;gap:6px}
  .tab{padding:8px 18px;border-radius:var(--r2);cursor:pointer;font-size:13px;font-weight:600;
    color:var(--muted);background:transparent;border:1px solid transparent;transition:.2s}
  .tab:hover{color:var(--text);background:var(--panel)}
  .tab.active{color:var(--accent);background:rgba(0,212,255,.08);border-color:rgba(0,212,255,.18);
    box-shadow:0 0 12px rgba(0,212,255,.1)}
  .search-wrap{margin-left:auto}
  .search{padding:7px 14px 7px 32px;border-radius:20px;border:1px solid var(--border);
    background:var(--solid);color:var(--text);font-size:13px;width:220px;outline:none;transition:.2s}
  .search:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(0,212,255,.12)}
  .search-icon{position:relative;left:-198px;color:var(--muted);pointer-events:none}
  .main{padding:20px 32px 40px}

  /* Dashboard */
  .dash-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
  .dash-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    padding:18px 20px;position:relative;overflow:hidden}
  .dash-card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--dc,var(--accent))}
  .dc-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}
  .dc-val{font-size:28px;font-weight:800;color:var(--text)}
  .dc-sub{font-size:11px;color:var(--muted);margin-top:4px}
  .ds-row{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
  .dash-section{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:18px}
  .ds-title{font-size:13px;font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:6px}
  .donut-wrap{text-align:center}
  .dl-item{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text2);padding:3px 0}
  .dl-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
  .bar-list{display:flex;flex-direction:column;gap:8px}
  .bar-row{display:flex;align-items:center;gap:8px;font-size:12px}
  .bar-label{width:70px;flex-shrink:0;color:var(--text2)}
  .bar-track{flex:1;height:18px;background:rgba(0,0,0,.15);border-radius:9px;overflow:hidden}
  .bar-fill{height:100%;border-radius:9px;font-size:10px;color:#fff;padding:0 8px;
    display:flex;align-items:center;white-space:nowrap;min-width:28px;justify-content:flex-end}
  .bar-count{width:36px;text-align:right;color:var(--muted);font-size:11px}
  .heat-list{list-style:none;padding:0;margin:0}
  .heat-item{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border)}
  .heat-rank{width:24px;height:24px;border-radius:6px;display:grid;place-items:center;
    font-size:12px;font-weight:800;flex-shrink:0}
  .r1{background:linear-gradient(135deg,#ffd700,#ffaa00);color:#000}
  .r2{background:linear-gradient(135deg,#c0c0c0,#999);color:#000}
  .r3{background:linear-gradient(135deg,#cd7f32,#a0522d);color:#fff}
  .rx{background:var(--panel2);color:var(--muted)}
  .heat-name{flex:1;cursor:pointer;font-weight:600;font-size:13px}
  .heat-name:hover{color:var(--accent)}
  .heat-val{font-size:11px;color:var(--muted)}
  .heat-cat{font-size:10px;color:var(--muted);background:var(--panel2);padding:2px 8px;border-radius:10px}
  .src-bars{display:flex;flex-direction:column;gap:8px}
  .src-bar{display:flex;align-items:center;gap:8px;font-size:12px}
  .src-bar label{width:72px;flex-shrink:0}
  .src-track{flex:1;height:14px;background:rgba(0,0,0,.15);border-radius:7px;overflow:hidden}
  .src-fill{height:100%;border-radius:7px}
  .src-pct{width:34px;text-align:right;font-size:11px;color:var(--muted)}
  .feed{list-style:none;padding:0;margin:0}
  .feed li{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px}
  .feed-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:5px}
  .feed-body{flex:1;color:var(--text2)}
  .feed-time{color:var(--muted);font-size:10px;white-space:nowrap}
  .ds-scroll{max-height:280px;overflow-y:auto;padding-right:4px}
  .ds-scroll::-webkit-scrollbar{width:5px}
  .ds-scroll::-webkit-scrollbar-track{background:transparent}
  .ds-scroll::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

  /* Shelf */
  .shelf-nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px;padding:10px 14px;
    background:var(--panel);border:1px solid var(--border);border-radius:var(--r);align-items:center}
  .nav-pill{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;
    border:1px solid var(--border);color:var(--muted);transition:.15s;white-space:nowrap}
  .nav-pill:hover{color:var(--text);border-color:var(--accent)}
  .nav-pill.active{color:#fff;background:var(--c0);border-color:var(--c0)}
  .dept{margin-bottom:24px;border:1px solid var(--border);border-radius:var(--r);
    background:var(--panel);overflow:hidden}
  .dept-head{display:flex;align-items:center;gap:12px;padding:14px 18px;
    background:linear-gradient(90deg,rgba(0,212,255,.06),transparent);cursor:pointer;user-select:none}
  .dept-ico{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;font-size:18px;
    background:color-mix(in srgb, var(--c,var(--c0)) 18%, transparent);color:var(--c,var(--c0))}
  .dept-head h2{font-size:16px;font-weight:700}
  .dept-head .cnt{color:var(--muted);font-size:12px;margin-left:4px}
  .dept-bar{height:3px;background:var(--border);position:relative}
  .dept-bar::after{content:'';position:absolute;left:0;top:0;height:100%;
    background:var(--c,var(--c0));border-radius:2px;width:var(--usage,0%);transition:.4s}
  .dept-arrow{margin-left:auto;color:var(--muted);transition:transform .2s;font-size:12px}
  .dept.collapsed .dept-arrow{transform:rotate(-90deg)}
  .dept-body{padding:12px 14px 16px}
  .dept.collapsed .dept-body{display:none}
  .sub-cols{display:flex;gap:14px;overflow-x:auto;padding-bottom:4px}
  .sub-col{min-width:240px;max-width:300px;flex:1;min-width:0;
    border:1px solid var(--border);border-radius:var(--r2);background:var(--solid);overflow:hidden}
  .sub-col-head{padding:8px 12px;font-size:11px;font-weight:700;color:var(--muted);
    text-transform:uppercase;letter-spacing:.5px;display:flex;align-items:center;gap:6px;
    border-bottom:1px solid var(--border);background:var(--panel2)}
  .sub-col-head .dot{width:8px;height:8px;border-radius:50%;background:var(--c,var(--c0))}
  .sub-col-cnt{margin-left:auto;font-size:10px;color:var(--muted);background:var(--panel);padding:1px 8px;border-radius:10px}
  .sub-col-body{max-height:420px;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:8px}
  .sub-col-body::-webkit-scrollbar{width:4px}
  .sub-col-body::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

  /* Cards */
  .card{border:1px solid var(--border);border-radius:var(--r2);cursor:pointer;transition:.2s;
    background:var(--solid);position:relative;overflow:hidden}
  .card:hover{transform:translateY(-3px) scale(1.01);border-color:var(--c,var(--accent));
    box-shadow:0 12px 30px color-mix(in srgb, var(--c,var(--accent)) 18%, transparent)}
  .chip{position:absolute;top:6px;right:7px;font-size:9px;font-weight:700;padding:1px 7px;
    border-radius:10px;background:color-mix(in srgb, var(--c,var(--accent)) 15%, transparent);color:var(--c,var(--accent))}
  .card-name{font-size:13px;font-weight:700;padding:6px 12px 1px;line-height:1.3;letter-spacing:.3px}
  .card-desc{font-size:10.5px;color:var(--muted);padding:0 12px 6px;line-height:1.4;display:-webkit-box;
    -webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden;transition:all .25s}
  .card-foot{display:flex;align-items:center;gap:8px;padding:4px 12px 8px;font-size:10px;color:var(--muted);opacity:.55;transition:all .25s}
  .use-tag{background:color-mix(in srgb, var(--accent) 10%, transparent);color:var(--accent);
    padding:1px 6px;border-radius:9px;font-weight:600}
  .src-tag{background:var(--panel2);padding:1px 6px;border-radius:9px}
  .type-prompt .card-inner{border-left:3px solid var(--c,var(--c0));padding:10px 12px}
  .type-prompt .quote{font-style:italic;color:var(--text2);font-size:10.5px;
    padding:4px 10px;background:var(--panel2);border-radius:8px;margin-top:3px;
    display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden;transition:all .25s}
  .type-python{font-family:"Cascadia Code","Fira Code","Source Code Pro",monospace}
  .type-python .win-bar{display:flex;align-items:center;gap:6px;padding:6px 10px;
    background:#0d1117;border-bottom:1px solid #30363d}
  .type-python .dot{width:9px;height:9px;border-radius:50%}
  .type-python .code-preview{padding:6px 10px;font-size:10.5px;color:#8b949e;white-space:pre-wrap;
    max-height:48px;overflow:hidden;line-height:1.45}
  .type-process .doc-icon{float:left;font-size:22px;margin:6px 10px 0 12px}
  .type-process .doc-path{font-size:10px;color:var(--muted);padding:4px 12px 0}
  .type-process .steps{clear:both;padding:4px 12px 8px;font-size:10.5px;color:var(--text2);line-height:1.5;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;transition:all .25s}
  .type-config .file-header{display:flex;align-items:center;gap:8px;padding:10px 12px}
  .type-config .file-icon{font-size:20px}
  .type-config .ext-badge{font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;
    background:var(--warn);color:#000;margin-left:auto}
  .type-ref .ref-mark{position:absolute;top:10px;right:10px;font-size:28px;opacity:.1;pointer-events:none}
  .type-ref .card-inner{border-left:3px solid var(--c5);padding:12px}
  /* Card hover enhancements */
  .card:hover .card-foot{opacity:1}
  .card:hover .card-desc{-webkit-line-clamp:2}
  .card:hover{z-index:2}

  /* Generations */
  .gen-list{max-height:520px;overflow-y:auto;padding-right:4px}
  .gen-list::-webkit-scrollbar{width:5px}
  .gen-list::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
  .gen-card{border:1px solid var(--border);border-radius:var(--r);background:var(--panel);
    margin-bottom:14px;overflow:hidden;transition:.2s}
  .gen-card:hover{border-color:var(--accent)}
  .gen-head{display:flex;align-items:center;gap:10px;padding:14px 18px;cursor:pointer}
  .gen-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
  .gen-head h3{font-size:15px;font-weight:700;flex:1}
  .gen-meta{font-size:11px;color:var(--muted);display:flex;gap:10px}
  .gen-body{padding:0 18px 14px;display:none;border-top:1px solid var(--border)}
  .gen-card.open .gen-body{display:block}
  .gen-parts{font-size:12px;color:var(--text2);line-height:1.8}
  .gen-parts a{color:var(--accent);cursor:pointer;font-weight:600}
  .gen-parts a:hover{text-decoration:underline}
  .gen-notes{margin-top:10px;font-size:11px;color:var(--muted);font-style:italic;padding:8px 12px;
    background:var(--panel2);border-radius:var(--r2)}

  /* Detail drawer */
  .overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:100;
    opacity:0;pointer-events:none;transition:.25s;backdrop-filter:blur(4px)}
  .overlay.show{opacity:1;pointer-events:auto}
  .drawer{position:fixed;right:-480px;top:0;bottom:0;width:480px;max-width:92vw;
    background:var(--bg2);border-left:1px solid var(--border);z-index:101;
    transition:.35s;overflow-y:auto;padding:24px;box-shadow:-10px 0 40px rgba(0,0,0,.3)}
  .overlay.show .drawer{right:0}
  .drawer .close{position:absolute;top:12px;right:14px;background:var(--panel);border:1px solid var(--border);
    color:var(--muted);border-radius:8px;padding:6px 14px;cursor:pointer;font-size:12px}
  .drawer h2{font-size:19px;font-weight:800;padding-right:60px}
  .drawer .meta{font-size:12px;color:var(--muted);margin-top:4px}
  .drawer .chips{display:flex;gap:6px;margin:12px 0;flex-wrap:wrap}
  .badge{font-size:10px;font-weight:700;padding:3px 10px;border-radius:12px}
  .badge.use{background:rgba(0,212,255,.1);color:var(--accent)}
  .badge.src-initial{background:rgba(0,230,118,.1);color:var(--good)}
  .badge.src-dismantled{background:rgba(255,171,0,.1);color:var(--warn)}
  .badge.src-auto_generated{background:rgba(168,85,247,.1);color:var(--c1)}
  .sec-title{font-size:13px;font-weight:700;margin:18px 0 8px;padding-bottom:4px;
    border-bottom:1px solid var(--border)}
  .drawer pre{background:#0d1117;border:1px solid var(--border);border-radius:var(--r2);
    padding:14px;font-size:11.5px;overflow-x:auto;max-height:300px;line-height:1.55;
    white-space:pre-wrap;word-break:break-all}
  .drawer code{font-family:"Cascadia Code","Fira Code",monospace;color:#8b949e}
  .rel{font-size:12px;line-height:1.9}
  .rel li{margin-bottom:2px}
  .pclick{color:var(--accent);cursor:pointer;font-weight:600}
  .pclick:hover{text-decoration:underline}

  /* Peek */
  #peek{position:fixed;z-index:50;pointer-events:none;opacity:0;transition:.15s;
    background:var(--solid);border:1px solid var(--border);border-radius:var(--r);
    box-shadow:0 8px 30px rgba(0,0,0,.35);padding:12px 16px;max-width:320px}
  #peek.show{opacity:1}
  .pk-head{font-size:13px;font-weight:700;margin-bottom:4px}
  .pk-meta{font-size:10px;color:var(--muted);margin-bottom:6px}
  .pk-src{font-size:11px;color:var(--accent);margin-bottom:4px}
  .pk-desc{font-size:11px;color:var(--text2);line-height:1.5}
  .empty{text-align:center;padding:60px 20px;color:var(--muted);font-size:14px}
  @keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
  .card{animation:fadeUp .3s ease both}
</style>
</head>
<body>
<div class="header">
  <div class="logo">🏪</div>
  <div class="htitle"><h1>零件杂货铺 · 解剖图</h1>
    <p>看清你的 Agent 由什么零件拼成 · 需求 → 检索 → 组装 → 回填</p></div>
  <div class="stats-row" id="stats"></div>
</div>
<div class="nav">
  <div class="tab active" data-tab="dashboard">📈 大盘</div>
  <div class="tab" data-tab="shelf">📊 货架视图</div>
  <div class="tab" data-tab="gens">📜 生成记录</div>
  <div class="search-wrap"><span class="search-icon">🔍</span>
    <input class="search" id="search" placeholder="搜索零件名称 / 描述 / 类型..."></div>
</div>
<div class="main">
  <section id="dashboard"></section>
  <section id="shelf" hidden></section>
  <section id="gens" hidden></section>
</div>
<div class="overlay" id="detail"><aside class="drawer" id="sheet"></aside></div>
<div id="peek"></div>
<script type="application/json" id="__data">__JSON_PAYLOAD__</script>
<script>
(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  let D;
  try{D=JSON.parse($('__data').textContent);}
  catch(e){console.error('[Grocery] Data parse error:',e);
    $('dashboard').innerHTML='<div class="empty">⚠️ 数据加载失败，请重新生成 shop.html</div>';return;}
  if(!D||!D.categories){$('dashboard').innerHTML='<div class="empty">无可用数据</div>';return;}

  const CAT_ICON=['🧭','📐','💻','🧪','🧰','📚'];
  const srcLabel={initial:'初始零件包',dismantled:'拆解产物',auto_generated:'自动生成'};
  const srcClass={initial:'src-initial',dismantled:'src-dismantled',auto_generated:'src-auto'};
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function cardType(p){
    const t=(p.type||'').toLowerCase();
    if(t.includes('prompt'))return'prompt';
    if(t.includes('python')||t.includes('代码')||p.content_format==='python')return'python';
    if(t.includes('流程')||t.includes('规范'))return'process';
    if(t.includes('配置')||/[.]json|[.]yaml|[.]ini|[.]toml/.test(t))return'config';
    if(t.includes('参考')||t.includes('文档'))return'ref';
    return'default';
  }

  function renderStats(){
    try{$('stats').innerHTML=
      '<div class="stat-pill"><b>'+D.stats.parts+'</b><small>零件</small></div>'+
      '<div class="stat-pill"><b>'+D.stats.generations+'</b><small>Skill</small></div>'+
      '<div class="stat-pill"><b>'+D.stats.categories+'</b><small>大类</small></div>';}
    catch(e){console.error('renderStats:',e);}
  }

  function renderDashboard(){
    try{
      const pbid=D.parts_by_id||{},allParts=Object.values(pbid);
      const totalUsage=allParts.reduce((s,p)=>s+(p.usage_count||0),0);
      const sm={};allParts.forEach(p=>{const s=p.source_type||'initial';sm[s]=(sm[s]||0)+1;});
      const tm={};allParts.forEach(p=>{const t=cardType(p);tm[t]=(tm[t]||0)+1;});
      const heat=[...allParts].sort((a,b)=>(b.usage_count||0)-(a.usage_count||0)).slice(0,8);
      const recent=[...D.generations].sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||'')).slice(0,5);

      $('dashboard').innerHTML=
      '<div class="dash-grid">'+
        dcCard('总零件数',D.stats.parts,'分布在 '+D.stats.categories+' 个大类','', 'rgba(0,212,255,.10)')+
        dcCard('已组装 Skill',D.stats.generations,'累计使用 '+totalUsage+' 次','', 'rgba(168,85,247,.10)')+
        dcCard('最热零件',heat[0]?esc(heat[0].name):'—','',heat[0]?heat[0].usage_count+' 次':'0 次','rgba(0,230,118,.10)')+
        dcCard('来源丰富度',Object.keys(sm).length,'种来源渠道','','rgba(255,171,0,.10)')+
      '</div>'+
      '<div class="ds-row">'+
        '<div class="dash-section"><div class="ds-title"><span>🎯</span> 类别分布</div>'+donutHTML()+'</div>'+
        '<div class="dash-section"><div class="ds-title"><span>🏷️</span> 类型构成</div><div class="ds-scroll">'+typeBarsHTML(tm,allParts.length)+'</div></div>'+
      '</div>'+
      '<div class="ds-row">'+
        '<div class="dash-section"><div class="ds-title"><span>🔥</span> 使用热度 TOP 8</div><div class="ds-scroll"><ul class="heat-list">'+heatListHTML(heat)+'</ul></div></div>'+
        '<div class="dash-section"><div class="ds-title"><span>📦</span> 来源占比</div><div class="ds-scroll">'+srcBarsHTML(sm,allParts.length)+
        '</div><div class="ds-title" style="margin-top:18px"><span>🕐</span> 最近活动</div><div class="ds-scroll"><ul class="feed">'+feedHTML(recent)+'</ul></div></div>'+
      '</div>';

      $('dashboard').querySelectorAll('.heat-click').forEach(el=>el.onclick=()=>showDetail(el.dataset.id));
    }catch(e){console.error('renderDashboard:',e);$('dashboard').innerHTML='<div class="empty">大盘渲染失败: '+esc(e.message)+'</div>';}
  }

  function dcCard(l,v,s,ex,clr){
    return'<div class="dash-card" style="--dc:'+clr+'"><div class="dc-label">'+l+'</div><div class="dc-val">'+v+'</div><div class="dc-sub">'+s+(ex?' ('+ex+')':'')+'</div></div>';
  }

  function donutHTML(){
    const cats=D.categories,total=cats.reduce((s,c)=>s+c.count,0)||1;
    let acc=0,segs=cats.map((c,i)=>{
      const pct=c.count/total;const start=acc*360;acc+=pct;const end=acc*360;const large=pct>.5?1:0;
      const cx=100,cy=100,r=70,r2=45;
      const x1=cx+r*Math.cos(Math.PI*(start-90)/180),y1=cy+r*Math.sin(Math.PI*(start-90)/180);
      const x2=cx+r*Math.cos(Math.PI*(end-90)/180),y2=cy+r*Math.sin(Math.PI*(end-90)/180);
      const x3=cx+r2*Math.cos(Math.PI*(end-90)/180),y3=cy+r2*Math.sin(Math.PI*(end-90)/180);
      return'<path d="M'+cx+','+cy+' L'+x1.toFixed(1)+','+y1.toFixed(1)+' A'+r+','+r+' 0 '+large+',1 '+x2.toFixed(1)+','+y2.toFixed(1)+' L'+x3.toFixed(1)+','+y3.toFixed(1)+' A'+r2+','+r2+' 0 '+large+',0 '+x1.toFixed(1)+','+y1.toFixed(1)+' Z" fill="var(--c'+i+')" opacity=".85"/>';
    }).join('');
    const legend=cats.map((c,i)=>'<div class="dl-item"><span class="dl-dot" style="background:var(--c'+i+')"></span>'+esc(c.name)+' ('+c.count+')</div>').join('');
    return'<div class="donut-wrap"><svg viewBox="0 0 200 200" width="180" height="180">'+segs+
      '<circle cx="100" cy="100" r="40" fill="var(--solid)" stroke="none"/>'+
      '<text x="100" y="104" text-anchor="middle" fill="var(--text)" font-size="18" font-weight="800">'+total+'</text>'+
      '<text x="100" y="122" text-anchor="middle" fill="var(--muted)" font-size="10">零件</text></svg><div class="donut-legend">'+legend+'</div></div>';
  }

  function typeBarsHTML(tm,total){
    return Object.entries(tm).map(([label,count])=>{
      const pct=Math.round(count/total*100);
      const names={prompt:'Prompt片段',python:'代码',process:'流程规范',config:'配置文件',ref:'参考文档',default:'其他'};
      return'<div class="bar-row"><div class="bar-label">'+(names[label]||label)+'</div><div class="bar-track"><div class="bar-fill" style="width:'+pct+'%">'+count+'</div></div><div class="bar-count">'+pct+'%</div></div>';
    }).join('');
  }
  function heatListHTML(heat){
    return heat.map((p,i)=>{
      const rc=i<3?'r'+(i+1):'rx';
      return'<li class="heat-item"><div class="heat-rank '+rc+'">'+(i+1)+'</div><div class="heat-name heat-click" data-id="'+esc(p.id)+'">'+esc(p.name)+'</div><div class="heat-val">🔗 '+(p.usage_count||0)+'</div><div class="heat-cat">'+esc(p.category)+'</div></li>';
    }).join('');
  }
  function srcBarsHTML(sm,total){
    return Object.entries(sm).map(([label,count])=>{
      const pct=Math.round(count/total*100),ci=label==='initial'?0:label==='dismantled'?3:1;
      return'<div class="src-bar"><label">'+(srcLabel[label]||label)+'</label><div class="src-track"><div class="src-fill" style="width:'+pct+'%;background:var(--c'+ci+')"></div></div><div class="src-pct">'+pct+'%</div></div>';
    }).join('');
  }
  function feedHTML(recent){
    if(!recent.length)return'<li style="color:var(--muted)">暂无活动记录</li>';
    return recent.map(g=>{
      const dot=g.auto_dismantled?'var(--good)':'var(--accent)';
      return'<li><div class="feed-dot" style="background:'+dot+'"></div><div class="feed-body">组装了 <b>'+esc(g.name)+'</b>，使用了 <b>'+(g.used_part_ids?g.used_part_ids.length:0)+'</b> 个零件'+(g.auto_dismantled?' · 已自动回填':'')+'</div><div class="feed-time">'+esc(g.created_at||'')+'</div></li>';
    }).join('');
  }

  /* --- Shelf --- */
  function renderShelfNav(){
    try{
      const nav=$('shelf');
      let pills='<div class="nav-pill active" data-ci="">▦ 全部</div>';
      D.categories.forEach((c,i)=>{pills+='<div class="nav-pill" data-ci="'+i+'">'+CAT_ICON[i]+' '+esc(c.name)+' <b>'+c.count+'</b></div>';});
      nav.innerHTML='<div class="shelf-nav">'+pills+'</div><div id="shelf-body"></div>';
      nav.querySelectorAll('.nav-pill').forEach(pill=>{pill.onclick=()=>{
        nav.querySelectorAll('.nav-pill').forEach(x=>x.classList.remove('active'));
        pill.classList.add('active');renderShelfBody(pill.dataset.ci);
      };});
    }catch(e){console.error('renderShelfNav:',e);}
  }

  function renderShelfBody(filterIdx){
    try{
      const body=$('shelf-body');if(!body)return;
      const fi=filterIdx!==''?parseInt(filterIdx):null;let html='';
      D.categories.forEach((cat,ci)=>{
        if(fi!==null&&ci!==fi)return;
        const subs=cat.subs,total=Object.values(subs).reduce((a,b)=>a+b.length,0);
        if(!total)return;
        let usedCount=0;Object.values(subs).forEach(ps=>ps.forEach(p=>{if(p.usage_count)usedCount++;}));
        const usagePct=Math.round(usedCount/Math.max(total,1)*100);
        let cols='';
        Object.entries(subs).forEach(([sn,parts])=>{
          cols+='<div class="sub-col"><div class="sub-col-head"><span class="dot" style="background:var(--c'+ci+')"></span>'+esc(sn)+'<span class="sub-col-col">'+parts.length+'</span></div><div class="sub-col-body">'+parts.map((p,i)=>cardHTML(p,i,ci)).join('')+'</div></div>';
        });
        html+='<div class="dept" data-ci="'+ci+'" style="--c:var(--c'+ci+')">'+
          '<div class="dept-head"><div class="dept-ico">'+CAT_ICON[ci]+'</div><h2>'+esc(cat.name)+'</h2><span class="cnt">'+total+' 个零件</span><div class="dept-arrow">▾</div></div>'+
          '<div class="dept-bar" style="--usage:'+usagePct+'%"></div><div class="dept-body"><div class="sub-cols">'+cols+'</div></div></div>';
      });
      body.innerHTML=html||'<div class="empty">没有匹配的零件</div>';
      body.querySelectorAll('.dept-head').forEach(h=>h.onclick=()=>h.parentElement.classList.toggle('collapsed'));
      body.querySelectorAll('.card').forEach(c=>c.onclick=()=>showDetail(c.dataset.id));
    }catch(e){console.error('renderShelfBody:',e);}
  }

  function renderShelf(query){
    renderShelfBody('');
    if(query)document.querySelectorAll('#shelf-body .card').forEach(card=>{
      const p=D.parts_by_id[card.dataset.id];
      if(!p){card.style.display='none';return;}
      const q=query.toLowerCase(),text=[p.name,p.description,p.category,p.sub_category,p.type,''].join(' ').toLowerCase();
      card.style.display=text.includes(q)?'':'none';
    });
  }

  function cardHTML(p,i,ci){
    const ct=cardType(p),src=p.source_type||'initial',
      head='<div class="chip">'+tcChip(ct)+'</div><div class="card-name">'+esc(p.name)+'</div>',
      foot='<div class="card-foot"><span class="use-tag">🔗 '+(p.usage_count||0)+'</span><span class="src-tag">'+esc(srcLabel[src])+'</span></div>',
      desc=p.description?'<div class="card-desc">'+esc(p.description)+'</div>':'';

    if(ct==='prompt'){
      const preview=p.content?'<div class="quote">'+esc(p.content.substring(0,120))+'</div>':'';
      return'<div class="card type-prompt" data-id="'+esc(p.id)+'" style="--c:var(--c'+ci+');animation-delay:'+(i*30)+'ms">'+head+desc+preview+foot+'</div>';
    }
    if(ct==='python'){
      const dots='<span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span><span class="dot" style="background:#27ca40"></span>';
      const codeLines=(p.content||'').split('\\n').slice(0,4).join('\\n');
      return'<div class="card type-python" data-id="'+esc(p.id)+'" style="--c:var(--c'+ci+');animation-delay:'+(i*30)+'ms">'+
        '<div class="win-bar">'+dots+'<span style="font-size:10px;color:#8b949e;margin-left:auto">'+esc(p.content_format||'py')+'</span></div>'+
        '<div class="code-preview">'+esc(codeLines)+'</div>'+head+foot+'</div>';
    }
    if(ct==='process'){
      const steps=p.content?'<div class="steps">'+esc(p.content.substring(0,160))+'</div>':'';
      return'<div class="card type-process" data-id="'+esc(p.id)+'" style="--c:var(--c'+ci+');animation-delay:'+(i*30)+'ms">'+
        '<div class="doc-icon">📋</div>'+head+'<div class="doc-path">'+esc(p.category)+' > '+esc(p.sub_category||'')+'</div>'+desc+steps+foot+'</div>';
    }
    if(ct==='config'){
      const ext=(p.content_format||'').replace(/json|yaml|ini|toml/i,m=>'.'+m)||'.json';
      return'<div class="card type-config" data-id="'+esc(p.id)+'" style="--c:var(--c'+ci+');animation-delay:'+(i*30)+'ms">'+
        '<div class="file-header"><div class="file-icon">⚙️</div><b style="font-size:13px">'+esc(p.name)+'</b><span class="ext-badge">'+ext+'</span></div>'+desc+foot+'</div>';
    }
    if(ct==='ref'){
      return'<div class="card type-ref" data-id="'+esc(p.id)+'" style="--c:var(--c'+ci+');animation-delay:'+(i*30)+'ms">'+
        '<span class="ref-mark">📖</span><div class="card-inner">'+head+desc+foot+'</div></div>';
    }
    return'<div class="card type-default" data-id="'+esc(p.id)+'" style="--c:var(--c'+ci+');animation-delay:'+(i*30)+'ms">'+head+desc+foot+'</div>';
  }
  function tcChip(ct){const n={prompt:'💬 Prompt',python:'🐍 代码',process:'📋 流程',config:'⚙️ 配置',ref:'📖 文档',default:'◆ 通用'};return n[ct]||'◆';}

  /* --- Generations --- */
  function renderGens(){
    try{
      const el=$('gens');
      if(!D.generations.length){el.innerHTML='<div class="empty">📚 暂无生成记录<br><small style="color:var(--muted)">组装 Skill 后会自动出现在这里</small></div>';return;}
      let html='';
      D.generations.forEach(g=>{
        const dotColor=g.auto_dismantled?'var(--good)':'var(--accent)';
        const partsHtml=(g.used_part_ids||[]).map(pid=>{const p=D.parts_by_id[pid];return p?'<a data-id="'+pid+'">'+esc(p.name)+'</a>':esc(pid);}).join(' · ');
        html+='<div class="gen-card"><div class="gen-head"><div class="gen-dot" style="background:'+dotColor+'"></div>'+
          '<h3>'+esc(g.name)+'</h3><div class="gen-meta"><span>'+esc(g.created_at||'')+'</span><span>'+(g.used_part_ids?g.used_part_ids.length:0)+' 个零件</span>'+
          (g.auto_dismantled?'<span style="color:var(--good)">✅ 已回填</span>':'')+'</div></div>'+
          '<div class="gen-body">'+(partsHtml?'<div class="gen-parts">📎 物料清单：'+partsHtml+'</div>':'')+
          (g.notes?'<div class="gen-notes">'+esc(g.notes)+'</div>':'')+'</div></div>';
      });
      el.innerHTML='<div class="gen-list">'+html+'</div>';
      el.querySelectorAll('.gen-head').forEach(h=>h.onclick=()=>h.parentElement.classList.toggle('open'));
      el.querySelectorAll('.gen-parts [data-id]').forEach(a=>a.onclick=e=>{e.stopPropagation();showDetail(a.dataset.id);});
    }catch(e){console.error('renderGens:',e);}
  }

  /* --- Detail drawer --- */
  function showDetail(id){
    try{
      const p=D.parts_by_id[id];if(!p)return;
      const src=p.source_type||'initial';
      const usages=(p.usages||[]).map(u=>'<li><span class="pclick" data-gid="'+esc(u.generation_id)+'">'+esc(u.name)+'</span><span class="tag">'+esc(u.created_at||'')+'</span></li>').join('')||'<li class="tag">暂无被使用记录</li>';
      const sibs=(p.siblings||[]).map(s=>'<li><span class="pclick" data-id="'+esc(s.id)+'">'+esc(s.name)+'</span><span class="tag">'+esc(s.category)+' > '+esc(s.sub_category||'')+'</span></li>').join('')||'<li class="tag">无同源伙伴</li>';
      const fmt=['python','json','yaml'].includes(p.content_format)?p.content_format:'text';
      const dep=(p.depends_on||[]).map(d=>{const dp=D.parts_by_id[d];return dp?'<span class="pclick" data-id="'+d+'">'+esc(dp.name)+'</span>':esc(d);}).join('、')||'无';

      $('sheet').innerHTML=
        '<button class="close" id="closeSheet">✕ 关闭</button>'+
        '<h2>'+esc(p.name)+' <span class="tag">'+esc(p.version||'v1.0')+'</span></h2>'+
        '<div class="meta">'+esc(p.category||'')+' > '+esc(p.sub_category||'')+' | 类型：'+esc(p.type||'')+' | 来源：'+esc(srcLabel[src]||
        src)+(p.source_skill_name?' | 拆解自'+esc(p.source_skill_name):'')+'</div>'+
        '<div class="chips"><span class="badge use">🔗 '+esc(p.usage_count||0)+'次</span><span class="badge '+srcClass[src]+'">'+esc(srcLabel[src])+'</span></div>'+
        '<div class="sec-title">内容</div><pre><code class="language-'+fmt+'">'+esc(p.content||'')+'</code></pre>'+
        '<div class="sec-title">依赖</div><div class="rel">'+dep+'</div>'+
        '<div class="sec-title">被以下 Skill 使用</div><ul class="rel">'+usages+'</ul>'+
        '<div class="sec-title">同源伙伴</div><ul class="rel">'+sibs+'</ul>';
      $('sheet').querySelectorAll('.pclick[data-id]').forEach(el=>el.onclick=()=>showDetail(el.dataset.id));
      $('closeSheet').onclick=function(){$('detail').classList.remove('show');}; $('detail').classList.add('show');
    }catch(e){console.error('showDetail:',e);}
  }

  /* --- Peek tooltip --- */
  const peek=$('peek');
  document.addEventListener('mouseover',function(e){
    const card=e.target.closest('.card');if(!card||!card.closest('#shelf'))return;
    const p=D.parts_by_id[card.dataset.id];if(!p)return;
    peek.innerHTML='<div class="pk-head"><b>'+esc(p.name)+'</b></div><div class="pk-meta">'+esc(p.category)+' > '+esc(p.sub_category||'')+' | '+esc(p.type||'')+'</div><div class="pk-src">来源：'+esc(srcLabel[p.source_type]||p.source_type||'')+'</div><div class="pk-desc">'+esc(p.description||'(无描述)')+'</div>';
    peek.classList.add('show');
    const r=card.getBoundingClientRect(),pw=peek.offsetWidth,ph=peek.offsetHeight;
    let top=r.top-ph-12;if(top<10)top=r.bottom+12;
    let left=Math.min(r.left,window.innerWidth-pw-14);
    peek.style.top=top+'px';peek.style.left=Math.max(10,left)+'px';
  });
  document.addEventListener('mouseout',function(e){if(!e.relatedTarget||!e.relatedTarget.closest('.card'))peek.classList.remove('show');});

  /* --- Tab switching --- */
  $('search').oninput=function(e){peek.classList.remove('show');renderShelf(e.target.value);};
  document.querySelectorAll('.tab').forEach(function(t){
    t.onclick=function(){
      document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
      t.classList.add('active');
      const tab=t.dataset.tab;
      $('dashboard').hidden=tab!=='dashboard';$('shelf').hidden=tab!=='shelf';$('gens').hidden=tab!=='gens';
      $('search').style.visibility=(tab==='shelf')?'visible':'hidden';peek.classList.remove('show');
      if(tab==='dashboard'&&!$('dashboard').innerHTML.trim())renderDashboard();
    };
  });

  /* --- Init --- */
  renderStats();renderDashboard();renderShelfNav();renderShelfBody('');renderGens();
})();
</script>
</body>
</html>"""


def render(root: str) -> str:
    data = build_data(root)
    json_str = json.dumps(data, ensure_ascii=False)
    return TEMPLATE.replace("__JSON_PAYLOAD__", json_str)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    out = render(root)
    path = os.path.join(root, "shop.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"\u5df2\u751f\u6210\u89e3\u5269\u56fe: {os.path.abspath(path)} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
