"""解剖图生成器：把零件库 + 生成记录渲染成一张自包含 HTML。

数据内嵌在 HTML 中，零服务、零端口，用浏览器/预览面板打开即可。
每次零件库变动后重新运行本脚本即可看到最新视图。
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
            sub = p.get("sub_category") or "未分类"
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


TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>零件杂货铺 · 解剖图</title>
<style>
  :root{
    --bg:#0f1115; --panel:#171a21; --panel2:#1f232c; --border:#2a2f3a;
    --text:#e6e9ef; --muted:#9aa3b2; --accent:#5b9dff; --accent2:#7ee0c0;
    --warn:#ffb454; --bad:#ff6b6b; --chip:#262b36;
  }
  @media (prefers-color-scheme: light){
    :root{
      --bg:#f6f7f9; --panel:#ffffff; --panel2:#f0f2f5; --border:#e2e6ec;
      --text:#1c2230; --muted:#66708a; --accent:#2563eb; --accent2:#0d9488;
      --warn:#b45309; --bad:#dc2626; --chip:#eef1f6;
    }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;}
  header{padding:16px 22px;border-bottom:1px solid var(--border);
    display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:var(--panel);}
  header h1{font-size:18px;margin:0;display:flex;align-items:center;gap:8px}
  .stats{display:flex;gap:10px;margin-left:auto;flex-wrap:wrap}
  .stat{background:var(--chip);border:1px solid var(--border);border-radius:10px;
    padding:6px 12px;font-size:13px;color:var(--muted)}
  .stat b{color:var(--text);font-size:15px;margin-right:4px}
  nav{display:flex;gap:6px;padding:10px 22px;border-bottom:1px solid var(--border);
    background:var(--panel);position:sticky;top:0;z-index:5}
  .tab{padding:8px 16px;border-radius:9px;border:1px solid transparent;cursor:pointer;
    color:var(--muted);font-size:14px;background:transparent}
  .tab.active{background:var(--panel2);color:var(--text);border-color:var(--border)}
  .search{margin-left:auto;padding:7px 12px;border-radius:9px;border:1px solid var(--border);
    background:var(--panel2);color:var(--text);font-size:13px;min-width:220px}
  main{padding:18px 22px;max-width:1200px;margin:0 auto}
  .cat{border:1px solid var(--border);border-radius:14px;margin-bottom:16px;background:var(--panel);overflow:hidden}
  .cat-head{display:flex;align-items:center;gap:10px;padding:14px 18px;cursor:pointer;user-select:none}
  .cat-head .arrow{transition:transform .15s;color:var(--muted)}
  .cat.collapsed .arrow{transform:rotate(-90deg)}
  .cat-head h2{margin:0;font-size:16px}
  .cat-head .cnt{color:var(--muted);font-size:13px}
  .cat-body{padding:0 18px 16px}
  .cat.collapsed .cat-body{display:none}
  .sub{margin-top:12px}
  .sub-title{font-size:13px;color:var(--muted);margin:6px 0;display:flex;align-items:center;gap:6px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
  .card{position:relative;border:1px solid var(--border);border-radius:12px;padding:12px 14px;
    background:var(--panel2);cursor:pointer;transition:border-color .15s,transform .1s}
  .card:hover{border-color:var(--accent);transform:translateY(-1px)}
  .card .cname{font-size:14px;font-weight:600;margin-bottom:4px}
  .card .cpath{font-size:12px;color:var(--muted);margin-bottom:8px}
  .badges{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
  .badge{font-size:11px;padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--muted);border:1px solid var(--border)}
  .badge.use{color:var(--accent2);border-color:transparent;background:rgba(126,224,192,.12)}
  .badge.src-initial{color:var(--accent);background:rgba(91,157,255,.12)}
  .badge.src-dismantled{color:var(--warn);background:rgba(255,180,84,.12)}
  .badge.src-auto{color:#c792ea;background:rgba(199,146,234,.12)}
  .gen{border:1px solid var(--border);border-radius:12px;padding:14px 16px;background:var(--panel);margin-bottom:12px}
  .gen-head{display:flex;align-items:center;gap:10px;cursor:pointer}
  .gen-head .gname{font-size:15px;font-weight:600}
  .gen-head .gmeta{color:var(--muted);font-size:12px;margin-left:auto}
  .gen-body{margin-top:10px;display:none}
  .gen.open .gen-body{display:block}
  .bill{list-style:none;padding:0;margin:0}
  .bill li{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px dashed var(--border);font-size:13px}
  .bill li:last-child{border-bottom:none}
  .bill .pclick{cursor:pointer;color:var(--accent)}
  .bill .pclick:hover{text-decoration:underline}
  .notes{margin-top:8px;font-size:12px;color:var(--muted);white-space:pre-wrap}
  .overlay{position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;justify-content:center;
    align-items:flex-start;padding:40px 16px;overflow:auto;z-index:20}
  .overlay[hidden]{display:none}
  .sheet{background:var(--panel);border:1px solid var(--border);border-radius:16px;max-width:760px;width:100%;
    padding:22px 24px;position:relative}
  .sheet h2{margin:0 0 4px;font-size:20px}
  .sheet .close{position:absolute;top:16px;right:18px;cursor:pointer;border:none;background:var(--chip);
    color:var(--text);border-radius:8px;padding:4px 10px;font-size:14px}
  .meta{color:var(--muted);font-size:13px;margin-bottom:14px}
  .sec-title{font-size:13px;color:var(--accent);margin:16px 0 6px;font-weight:600}
  pre{background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:12px;
    overflow:auto;font-size:12.5px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
  .rel{list-style:none;padding:0;margin:0}
  .rel li{padding:5px 0;font-size:13px;border-bottom:1px dashed var(--border)}
  .rel .pclick{cursor:pointer;color:var(--accent)}
  .rel .pclick:hover{text-decoration:underline}
  .empty{color:var(--muted);text-align:center;padding:40px;font-size:14px}
  .tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:6px;background:var(--chip);color:var(--muted);margin-right:6px}
</style>
</head>
<body>
<header>
  <h1>🏪 零件杂货铺 · 解剖图</h1>
  <div class="stats" id="stats"></div>
</header>
<nav>
  <button class="tab active" data-tab="shelf">📊 货架视图</button>
  <button class="tab" data-tab="gens">📜 生成记录</button>
  <input class="search" id="search" placeholder="🔍 搜索零件…">
</nav>
<main>
  <section id="shelf"></section>
  <section id="gens" hidden></section>
</main>

<div class="overlay" id="detail" hidden>
  <div class="sheet" id="sheet"></div>
</div>

<script>window.__SHOP_DATA__ = __DATA_JSON__;</script>
<script>
const D = window.__SHOP_DATA__;
const $ = (id) => document.getElementById(id);
const srcLabel = {initial:'初始零件包', dismantled:'拆解产物', auto_generated:'自动生成'};
const srcClass = {initial:'src-initial', dismantled:'src-dismantled', auto_generated:'src-auto'};

function esc(s){ return String(s==null?'':s).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function renderStats(){
  $('stats').innerHTML = [
    `<div class="stat"><b>${D.stats.parts}</b>零件</div>`,
    `<div class="stat"><b>${D.stats.generations}</b>Skill</div>`,
    `<div class="stat"><b>${D.stats.categories}</b>大类</div>`,
  ].join('');
}

function cardHTML(p){
  const src = p.source_type || 'initial';
  const badges = `<span class="badge use">🔗 使用${p.usage_count||0}次</span>`
    + `<span class="badge ${srcClass[src]||''}">${esc(srcLabel[src]||src)}</span>`
    + `<span class="badge">${esc(p.type||'')}</span>`;
  return `<div class="card" data-id="${esc(p.id)}">
    <div class="cname">${esc(p.name)}</div>
    <div class="cpath">${esc(p.category||'')} › ${esc(p.sub_category||'')}</div>
    <div class="badges">${badges}</div>
  </div>`;
}

function renderShelf(filter){
  filter = (filter||'').trim().toLowerCase();
  const shelf = $('shelf');
  let html = '';
  for (const cat of D.categories){
    const subs = {};
    for (const sub in cat.subs){
      let ps = cat.subs[sub];
      if (filter) ps = ps.filter(p => (p.name+' '+p.description+' '+p.category+' '+p.sub_category+' '+p.type).toLowerCase().includes(filter));
      if (ps.length) subs[sub] = ps;
    }
    const total = Object.values(subs).reduce((a,b)=>a+b.length,0);
    if (filter && total===0) continue;
    let body = '';
    for (const sub in subs){
      body += `<div class="sub"><div class="sub-title">▸ ${esc(sub)} · ${subs[sub].length}</div>`
        + `<div class="grid">${subs[sub].map(cardHTML).join('')}</div></div>`;
    }
    html += `<div class="cat"><div class="cat-head"><span class="arrow">▾</span>`
      + `<h2>${esc(cat.name)}</h2><span class="cnt">${total} 个零件</span></div>`
      + `<div class="cat-body">${body}</div></div>`;
  }
  shelf.innerHTML = html || '<div class="empty">没有匹配的零件</div>';
  shelf.querySelectorAll('.cat-head').forEach(h => h.onclick = () => h.parentElement.classList.toggle('collapsed'));
  shelf.querySelectorAll('.card').forEach(c => c.onclick = () => showDetail(c.dataset.id));
}

function renderGens(){
  const box = $('gens');
  if (!D.generations.length){ box.innerHTML = '<div class="empty">还没有生成记录。在 WorkBuddy 中调用本 Skill 组装一个 Skill 试试。</div>'; return; }
  box.innerHTML = D.generations.map(g => {
    const items = g.used_part_ids.map(id => {
      const p = D.parts_by_id[id];
      const tag = p ? `${esc(p.category)} › ${esc(p.sub_category||'')}` : '未知';
      return `<li><span class="pclick" data-id="${esc(id)}">${esc(p?p.name:id)}</span>`
        + `<span class="tag">${tag}</span></li>`;
    }).join('') || '<li class="tag">无</li>';
    const auto = g.auto_dismantled ? '🔄 已自动回填' : '';
    return `<div class="gen"><div class="gen-head"><span class="gname">📄 ${esc(g.name)}</span>`
      + `<span class="gmeta">${esc(g.created_at||'')} ${auto}</span></div>`
      + `<div class="gen-body"><ul class="bill">${items}</ul>`
      + (g.notes?`<div class="notes">${esc(g.notes)}</div>`:'') + `</div></div>`;
  }).join('');
  box.querySelectorAll('.gen-head').forEach(h => h.onclick = () => h.parentElement.classList.toggle('open'));
  box.querySelectorAll('.pclick').forEach(el => el.onclick = (e)=>{ e.stopPropagation(); showDetail(el.dataset.id); });
}

function showDetail(id){
  const p = D.parts_by_id[id];
  if (!p) return;
  const src = p.source_type || 'initial';
  const usages = (p.usages||[]).map(u =>
    `<li><span class="pclick" data-gid="${esc(u.generation_id)}">${esc(u.name)}</span>`
    + `<span class="tag">${esc(u.created_at||'')}</span></li>`).join('') || '<li class="tag">暂无被使用记录</li>';
  const sibs = (p.siblings||[]).map(s =>
    `<li><span class="pclick" data-id="${esc(s.id)}">${esc(s.name)}</span>`
    + `<span class="tag">${esc(s.category)} › ${esc(s.sub_category||'')}</span></li>`).join('')
    || '<li class="tag">无同源伙伴</li>';
  const content = p.content || '';
  const fmt = (p.content_format==='python'||p.content_format==='json'||p.content_format==='yaml') ? p.content_format : 'text';
  const dep = (p.depends_on||[]).map(d => {
    const dp = D.parts_by_id[d]; return dp?`<span class="pclick" data-id="${esc(d)}">${esc(dp.name)}</span>`:esc(d);
  }).join('、') || '无';
  const sheet = $('sheet');
  sheet.innerHTML = `<button class="close" onclick="closeDetail()">✕ 关闭</button>`
    + `<h2>${esc(p.name)} <span class="tag">${esc(p.version||'v1.0')}</span></h2>`
    + `<div class="meta">${esc(p.category||'')} › ${esc(p.sub_category||'')} ｜ 类型：${esc(p.type||'')} ｜ 来源：${esc(srcLabel[src]||src)}`
    + (p.source_skill_name?` ｜ 拆解自：${esc(p.source_skill_name)}`:'') + `</div>`
    + `<div class="badges"><span class="badge use">🔗 使用${p.usage_count||0}次</span></div>`
    + `<div class="sec-title">【内容】</div><pre><code class="language-${fmt}">${esc(content)}</code></pre>`
    + `<div class="sec-title">【依赖】</div><div class="rel">${dep}</div>`
    + `<div class="sec-title">【被以下 Skill 使用】</div><ul class="rel">${usages}</ul>`
    + `<div class="sec-title">【同源伙伴】</div><ul class="rel">${sibs}</ul>`;
  sheet.querySelectorAll('.pclick[data-id]').forEach(el => el.onclick = () => showDetail(el.dataset.id));
  $('detail').hidden = false;
}
function closeDetail(){ $('detail').hidden = true; }

$('search').oninput = (e) => renderShelf(e.target.value);
document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  const tab = t.dataset.tab;
  $('shelf').hidden = tab!=='shelf';
  $('gens').hidden = tab!=='gens';
  $('search').style.visibility = tab==='shelf' ? 'visible' : 'hidden';
});

renderStats(); renderShelf(''); renderGens();
</script>
</body>
</html>
"""


def render(root: str) -> str:
    data = build_data(root)
    json_str = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA_JSON__", json_str)


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    out = os.path.join(root, "shop.html")
    html = render(root)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成解剖图: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
