"""零件杂货铺 · Agent 管控台 v3 — 自包含 HTML（可纯静态，也可由 server.py 提供实时数据/写操作）。

数据通过 <script type="application/json"> 注入：{ "workshop": {...零件数据...}, "agent": {...agent 真实数据...} }。
JS 顶部自动探测：若由 server.py 同源提供（fetch /api/data 成功），则 LIVE=true，启用卸载/清理/备份/压缩/对话等写操作；
否则为离线静态快照，动作降级为「复制命令到剪贴板」。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workshop import Workshop, CATEGORY_ORDER  # noqa
import build_data  # noqa


def build_workshop(root: str) -> dict:
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
                {"id": s["id"], "name": s["name"], "category": s["category"],
                 "sub_category": s.get("sub_category"), "usage_count": s.get("usage_count", 0)}
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
        "root": os.path.abspath(root),
        "categories": categories,
        "generations": gen_view,
        "parts_by_id": {p["id"]: p for p in enriched},
    }


def render(root: str) -> str:
    workshop = build_workshop(root)
    try:
        agent = build_data.build_agent_data()
    except Exception:
        agent = {"agent": {}, "skills": [], "tasks": [], "conversations": [], "anomalies": []}
    data = {"workshop": workshop, "agent": agent}
    json_str = json.dumps(data, ensure_ascii=False)
    return TEMPLATE.replace("__JSON_PAYLOAD__", json_str)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    out = render(root)
    path = os.path.join(root, "shop.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print("已生成管控台: %s (%d bytes)" % (os.path.abspath(path), len(out)))


TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>零件杂货铺 · Agent 管控台</title>
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
  html[data-theme="light"]{
    --bg:#f5f7fa;--bg2:#fff;--panel:rgba(0,0,0,.03);--panel2:rgba(0,0,0,.02);
    --solid:#fff;--border:rgba(0,0,0,.08);--text:#1a2332;--text2:#556677;--muted:#99aab8;
    --accent:#0891b2;--accent2:#059669;--c0:#0891b2;--c1:#7c3aed;--c2:#059669;--c3:#d97706;--c4:#db2777;--c5:#ea580c;
    --glow:0 0 20px rgba(0,0,0,.04);
  }
  html[data-theme="dark"]{
    --bg:#050a14;--bg2:#080e1c;--panel:rgba(0,212,255,.04);--panel2:rgba(0,212,255,.02);
    --solid:#0c1428;--border:rgba(0,212,255,.12);--text:#e0f4ff;--text2:#8ba4c4;--muted:#4a6a8a;
    --accent:#00d4ff;--accent2:#00ffa3;--c0:#00d4ff;--c1:#a855f7;--c2:#00e676;--c3:#ffab00;--c4:#ff4081;--c5:#ff6e40;
    --glow:0 0 30px rgba(0,212,255,.08);
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    background:var(--bg);color:var(--text);min-height:100vh;line-height:1.55;
    background-image:radial-gradient(ellipse at 80% 0%,rgba(0,212,255,.06) 0%,transparent 50%),
      radial-gradient(ellipse at 20% 100%,rgba(168,85,247,.05) 0%,transparent 50%);}
  .header{padding:20px 28px 14px;display:flex;align-items:center;gap:14px}
  .logo{width:48px;height:48px;border-radius:14px;background:linear-gradient(135deg,var(--c0),var(--c1));
    display:grid;place-items:center;font-size:24px;flex-shrink:0;box-shadow:var(--glow)}
  .htitle h1{font-size:20px;font-weight:800;background:linear-gradient(90deg,var(--c0),var(--c1),var(--c2));
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
  .htitle p{font-size:11px;color:var(--muted);margin-top:2px}
  .stats-row{display:flex;gap:10px;margin-left:auto;align-items:center}
  .stat-pill{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    padding:6px 14px;text-align:center;min-width:78px}
  .stat-pill b{display:block;font-size:18px;color:var(--accent);font-weight:800}
  .stat-pill small{font-size:10px;color:var(--muted)}
  .search-wrap{position:relative;display:flex;align-items:center}
  .search-icon{position:absolute;left:11px;font-size:13px;opacity:.6;pointer-events:none}
  .search{padding:7px 14px 7px 32px;border-radius:20px;border:1px solid var(--border);
    background:var(--solid);color:var(--text);font-size:13px;width:220px;outline:none}
  .search:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(0,212,255,.12)}
  .layout{display:flex;align-items:flex-start;gap:0;padding:0 28px 40px}
  .main{flex:1;min-width:0;padding:18px 24px 10px}
  .sidebar{width:200px;flex-shrink:0;position:sticky;top:14px;
    background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:12px;
    display:flex;flex-direction:column;gap:4px;max-height:calc(100vh - 40px);overflow-y:auto}
  .nav-item{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:var(--r2);
    cursor:pointer;font-size:13px;font-weight:600;color:var(--muted);border:1px solid transparent;transition:.18s}
  .nav-item:hover{color:var(--text);background:var(--panel2)}
  .nav-item.active{color:var(--accent);background:rgba(0,212,255,.08);border-color:rgba(0,212,255,.18);
    box-shadow:0 0 12px rgba(0,212,255,.08)}
  .nav-ico{font-size:16px;width:20px;text-align:center}
  .nav-sec{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;
    padding:12px 14px 4px;font-weight:700}
  .live-badge{margin-top:auto;font-size:10px;color:var(--muted);padding:8px 14px;text-align:center}
  .live-badge b{color:var(--good)}

  /* 通用卡片 */
  .sec-head{display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap}
  .sec-head h2{font-size:18px;font-weight:800;flex:1}
  .btn{padding:7px 14px;border-radius:20px;border:1px solid var(--border);background:var(--solid);
    color:var(--text);font-size:12px;font-weight:600;cursor:pointer;transition:.18s}
  .btn:hover{border-color:var(--accent);color:var(--accent)}
  .btn.bad{border-color:rgba(255,64,129,.3);color:var(--bad);background:rgba(255,64,129,.08)}
  .btn.bad:hover{background:rgba(255,64,129,.16)}
  .btn.go{border-color:rgba(0,230,118,.3);color:var(--good);background:rgba(0,230,118,.08)}
  .btn.go:hover{background:rgba(0,230,118,.16)}
  .btn.primary{border:none;background:var(--c0);color:#00121a;font-weight:700}
  .btn.primary:hover{filter:brightness(1.1)}

  /* 大盘 */
  .kpi-row{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:18px}
  .kpi{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:14px 16px}
  .kpi b{display:block;font-size:22px;font-weight:800;color:var(--accent)}
  .kpi small{font-size:10px;color:var(--muted)}
  .arena{position:relative;height:360px;background:radial-gradient(ellipse at 50% 45%,rgba(0,212,255,.07),transparent 70%);
    border:1px solid var(--border);border-radius:var(--r);margin-bottom:18px;overflow:hidden}
  .arena .wb-avatar{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:2}
  .capsule{position:absolute;transform:translate(-50%,-50%);border-radius:20px;padding:6px 12px;font-size:11px;
    font-weight:700;cursor:pointer;border:1px solid var(--border);background:var(--solid);white-space:nowrap;
    box-shadow:0 4px 14px rgba(0,0,0,.3);transition:.18s;z-index:3}
  .capsule:hover{transform:translate(-50%,-50%) scale(1.08);z-index:5}
  .arena .arena-hint{position:absolute;bottom:8px;left:0;right:0;text-align:center;font-size:10px;color:var(--muted)}

  .sk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
  .sk-card{border:1px solid var(--border);border-radius:var(--r);background:var(--panel);padding:14px;transition:.18s}
  .sk-card:hover{border-color:var(--accent);box-shadow:0 8px 24px rgba(0,212,255,.1)}
  .sk-name{font-size:14px;font-weight:700}
  .sk-desc{font-size:11px;color:var(--muted);margin:4px 0 8px;line-height:1.4;height:30px;overflow:hidden}
  .sk-meta{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px}
  .tag{font-size:10px;padding:2px 7px;border-radius:9px;background:var(--panel2);color:var(--text2)}
  .tag.g{background:rgba(0,230,118,.12);color:var(--good)}
  .tag.y{background:rgba(255,171,0,.12);color:var(--warn)}
  .sk-acts{display:flex;gap:6px}
  .sk-acts .btn{flex:1;padding:6px 8px;font-size:11px;text-align:center}

  /* 统计（workshop） */
  .dash-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
  .dash-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;position:relative;overflow:hidden}
  .dash-card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--dc,var(--accent))}
  .dc-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}
  .dc-val{font-size:26px;font-weight:800;color:var(--text)}
  .dc-sub{font-size:11px;color:var(--muted);margin-top:4px}
  .ds-row{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
  .dash-section{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:18px}
  .ds-title{font-size:13px;font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:6px}
  .bar-row{display:flex;align-items:center;gap:10px;font-size:13px;margin-bottom:14px}
  .bar-label{width:76px;flex-shrink:0;color:var(--text2);font-weight:600}
  .bar-track{flex:1;height:16px;background:rgba(0,0,0,.12);border-radius:8px;overflow:hidden}
  .bar-fill{height:100%;border-radius:8px;background:linear-gradient(90deg,var(--accent),#6eb9ff)}
  .bar-count{width:40px;text-align:right;color:var(--muted);font-size:12px}
  .heat-list{list-style:none;padding:0;margin:0}
  .heat-item{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border)}
  .heat-rank{width:24px;height:24px;border-radius:6px;display:grid;place-items:center;font-size:12px;font-weight:800;flex-shrink:0}
  .r1{background:linear-gradient(135deg,#ffd700,#ffaa00);color:#000}
  .r2{background:linear-gradient(135deg,#c0c0c0,#999);color:#000}
  .r3{background:linear-gradient(135deg,#cd7f32,#a0522d);color:#fff}
  .rx{background:var(--panel2);color:var(--muted)}
  .heat-name{flex:1;font-weight:600;font-size:13px;cursor:pointer}
  .heat-name:hover{color:var(--accent)}
  .heat-val{font-size:11px;color:var(--muted)}
  .src-bar{display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:8px}
  .src-bar label{width:90px;flex-shrink:0}
  .src-track{flex:1;height:14px;background:rgba(0,0,0,.15);border-radius:7px;overflow:hidden}
  .src-fill{height:100%;border-radius:7px}
  .src-pct{width:34px;text-align:right;font-size:11px;color:var(--muted)}
  .ds-scroll{max-height:280px;overflow-y:auto;padding-right:4px}

  /* 货架 */
  .shelf-nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px;padding:10px 14px;
    background:var(--panel);border:1px solid var(--border);border-radius:var(--r);align-items:center}
  .nav-pill{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;
    border:1px solid var(--border);color:var(--muted);transition:.15s;white-space:nowrap}
  .nav-pill:hover{color:var(--text);border-color:var(--accent)}
  .nav-pill.active{color:#fff;background:var(--c0);border-color:var(--c0)}
  .shelf-cards{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;padding-top:4px}
  .card{border:1px solid var(--border);border-radius:var(--r2);cursor:pointer;transition:.2s;background:var(--solid);position:relative;overflow:hidden}
  .card:hover{transform:translateY(-3px) scale(1.01);border-color:var(--accent);box-shadow:0 12px 30px rgba(0,212,255,.18)}
  .card-name{font-size:13px;font-weight:700;padding:8px 12px 2px}
  .card-desc{font-size:10.5px;color:var(--muted);padding:0 12px 8px;line-height:1.4}
  .card-foot{display:flex;gap:8px;padding:4px 12px 10px;font-size:10px;color:var(--muted)}
  .use-tag{background:rgba(0,212,255,.1);color:var(--accent);padding:1px 6px;border-radius:9px;font-weight:600}
  .dept{margin-bottom:20px;border:1px solid var(--border);border-radius:var(--r);background:var(--panel);overflow:hidden}
  .dept-head{display:flex;align-items:center;gap:12px;padding:14px 18px;background:linear-gradient(90deg,rgba(0,212,255,.06),transparent);cursor:pointer}
  .dept-head h2{font-size:16px;font-weight:700}
  .dept-head .cnt{color:var(--muted);font-size:12px}
  .dept-body{padding:12px 14px 16px}

  /* 生成记录 / 拆解任务 */
  .gen-card{border:1px solid var(--border);border-radius:var(--r);background:var(--panel);margin-bottom:14px;overflow:hidden}
  .gen-head{display:flex;align-items:center;gap:10px;padding:14px 18px;cursor:pointer}
  .gen-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
  .gen-head h3{font-size:15px;font-weight:700;flex:1}
  .gen-meta{font-size:11px;color:var(--muted);display:flex;gap:10px}
  .gen-body{padding:0 18px 14px;display:none;border-top:1px solid var(--border)}
  .gen-card.open .gen-body{display:block}
  .gen-basis{margin-top:12px;font-size:11.5px;line-height:1.7}
  .gen-basis-title{font-weight:700;margin-bottom:4px}
  .gen-basis-row{display:flex;gap:6px;padding:3px 0;border-bottom:1px dashed var(--border);flex-wrap:wrap}
  .gen-basis-part{color:var(--accent);cursor:pointer;font-weight:600}
  .gen-timeline{margin-top:12px;padding-left:18px;border-left:2px solid var(--border)}
  .gen-tl-item{position:relative;padding:6px 0 6px 16px;font-size:11.5px;color:var(--text2)}
  .gen-tl-item::before{content:'';position:absolute;left:-7px;top:14px;width:10px;height:10px;border-radius:50%;background:var(--border)}
  .dsm-card{display:flex;align-items:center;gap:14px;padding:14px 18px;border:1px solid var(--border);border-radius:var(--r);background:var(--panel);margin-bottom:12px}
  .dsm-card.done{border-left:3px solid var(--good)}
  .dsm-card.proc{border-left:3px solid var(--warn)}

  /* 对话 / 任务 / 异常 列表 */
  .list-row{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--border);
    border-radius:var(--r2);background:var(--panel);margin-bottom:8px;transition:.15s}
  .list-row:hover{border-color:var(--accent)}
  .lr-main{flex:1;min-width:0}
  .lr-title{font-size:13px;font-weight:700}
  .lr-sub{font-size:11px;color:var(--muted);margin-top:2px}
  .lr-tag{font-size:10px;padding:2px 8px;border-radius:9px;background:var(--panel2);color:var(--text2);flex-shrink:0}

  /* 对话框 */
  .chat-wrap{display:grid;grid-template-columns:300px 1fr;gap:16px}
  .conv-list{max-height:560px;overflow-y:auto;padding-right:4px}
  .chat-box{border:1px solid var(--border);border-radius:var(--r);background:var(--panel);display:flex;flex-direction:column;height:560px}
  .chat-bar{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border)}
  .chat-msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
  .msg{max-width:80%;padding:10px 14px;border-radius:14px;font-size:13px;line-height:1.6}
  .msg.you{align-self:flex-end;background:linear-gradient(135deg,var(--c0),var(--c1));color:#fff;border-bottom-right-radius:4px}
  .msg.boss{align-self:flex-start;background:var(--solid);border:1px solid var(--border);color:var(--text)}
  .chat-in{display:flex;gap:8px;padding:12px 14px;border-top:1px solid var(--border)}
  .chat-in input{flex:1;padding:9px 14px;border-radius:20px;border:1px solid var(--border);background:var(--solid);color:var(--text);font-size:13px;outline:none}
  .skill-pick{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px;border-bottom:1px solid var(--border)}
  .skill-pick .sp{padding:4px 10px;border-radius:14px;font-size:11px;border:1px solid var(--border);cursor:pointer;color:var(--text2)}
  .skill-pick .sp.active{background:var(--c0);color:#00121a;border-color:var(--c0);font-weight:700}

  /* 详情抽屉 */
  .overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:100;opacity:0;pointer-events:none;transition:.25s}
  .overlay.show{opacity:1;pointer-events:auto}
  .drawer{position:fixed;right:-520px;top:0;bottom:0;width:520px;max-width:94vw;background:var(--bg2);
    border-left:1px solid var(--border);z-index:101;transition:.35s;overflow-y:auto;padding:24px;box-shadow:-10px 0 40px rgba(0,0,0,.3)}
  .overlay.show .drawer{right:0}
  .drawer .close{position:absolute;top:12px;right:14px;background:var(--panel);border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:6px 14px;cursor:pointer;font-size:12px}
  .drawer h2{font-size:19px;font-weight:800;padding-right:60px}
  .drawer .meta{font-size:12px;color:var(--muted);margin-top:4px}
  .drawer .chips{display:flex;gap:6px;margin:12px 0;flex-wrap:wrap}
  .badge{font-size:10px;font-weight:700;padding:3px 10px;border-radius:12px}
  .badge.use{background:rgba(0,212,255,.1);color:var(--accent)}
  .badge.src-initial{background:rgba(0,230,118,.1);color:var(--good)}
  .badge.src-dismantled{background:rgba(255,171,0,.1);color:var(--warn)}
  .badge.src-auto_generated{background:rgba(168,85,247,.1);color:var(--c1)}
  .badge.src-git{background:rgba(0,212,255,.1);color:var(--accent)}
  .badge.src-local{background:rgba(255,171,0,.1);color:var(--warn)}
  .sec-title{font-size:13px;font-weight:700;margin:18px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--border)}
  .drawer pre{background:#0d1117;border:1px solid var(--border);border-radius:var(--r2);padding:14px;font-size:11.5px;overflow-x:auto;max-height:300px;line-height:1.55;white-space:pre-wrap;word-break:break-all}
  .drawer code{font-family:"Cascadia Code","Fira Code",monospace;color:#8b949e}
  .rel{font-size:12px;line-height:1.9}
  .pclick{color:var(--accent);cursor:pointer;font-weight:600}
  .pclick:hover{text-decoration:underline}

  .setting-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:18px;max-width:600px;margin-bottom:14px}
  .setting-card label{display:block;font-size:12px;color:var(--text2);margin:10px 0 4px}
  .setting-card input,.setting-card select{width:100%;padding:9px 12px;border-radius:var(--r2);border:1px solid var(--border);background:var(--solid);color:var(--text);font-size:13px;outline:none}
  .setting-card input:focus{border-color:var(--accent)}
  .hint{font-size:11px;color:var(--muted);margin-top:6px;line-height:1.6}

  .empty{text-align:center;padding:60px 20px;color:var(--muted);font-size:14px}
  .toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--solid);border:1px solid var(--accent);
    color:var(--text);padding:10px 20px;border-radius:20px;font-size:13px;z-index:200;box-shadow:var(--glow);opacity:0;transition:.25s}
  .toast.show{opacity:1}
  .warn-banner{background:rgba(255,171,0,.1);border:1px solid rgba(255,171,0,.3);color:var(--warn);
    font-size:12px;padding:10px 14px;border-radius:var(--r2);margin-bottom:14px}
</style>
</head>
<body>
<div class="header">
  <div class="logo">🛰️</div>
  <div class="htitle"><h1>零件杂货铺 · Agent 管控台</h1>
    <p>你的 Agent 全景：skill 资产管理 · 对话 · 任务 · 异常 · 一键运维</p></div>
  <div class="stats-row" id="stats"></div>
  <div class="search-wrap"><span class="search-icon">🔍</span>
    <input class="search" id="search" placeholder="搜索 skill / 零件 / 对话..."></div>
</div>
<div class="layout">
  <div class="main">
    <section id="dashboard"></section>
    <section id="stats" hidden></section>
    <section id="shelf" hidden></section>
    <section id="gens" hidden></section>
    <section id="dismantle" hidden></section>
    <section id="chat" hidden></section>
    <section id="tasks" hidden></section>
    <section id="anomalies" hidden></section>
    <section id="settings" hidden></section>
  </div>
  <aside class="sidebar">
    <div class="nav-sec">总览</div>
    <div class="nav-item active" data-tab="dashboard"><span class="nav-ico">🤖</span> 大盘</div>
    <div class="nav-item" data-tab="stats"><span class="nav-ico">📈</span> 统计</div>
    <div class="nav-sec">零件库</div>
    <div class="nav-item" data-tab="shelf"><span class="nav-ico">📊</span> 货架视图</div>
    <div class="nav-item" data-tab="gens"><span class="nav-ico">📜</span> 生成记录</div>
    <div class="nav-item" data-tab="dismantle"><span class="nav-ico">📦</span> 拆解任务</div>
    <div class="nav-sec">Agent</div>
    <div class="nav-item" data-tab="chat"><span class="nav-ico">💬</span> 对话</div>
    <div class="nav-item" data-tab="tasks"><span class="nav-ico">📋</span> 任务</div>
    <div class="nav-item" data-tab="anomalies"><span class="nav-ico">🚨</span> 异常日志</div>
    <div class="nav-sec">系统</div>
    <div class="nav-item" data-tab="settings"><span class="nav-ico">⚙️</span> 设置</div>
    <div class="live-badge" id="liveBadge">模式：<b>离线快照</b><br>启动 server.py 启用实时运维</div>
  </aside>
</div>
<div class="overlay" id="detail"><aside class="drawer" id="sheet"></aside></div>
<div class="toast" id="toast"></div>
<script type="application/json" id="__data">__JSON_PAYLOAD__</script>
<script>
/*__LIVE_FLAG__*/
(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  let D, LIVE=false, API='';
  try{ D=JSON.parse($('__data').textContent); }
  catch(e){ document.body.innerHTML='<div class="empty">数据解析失败</div>'; return; }
  if(!D||!D.workshop){ document.body.innerHTML='<div class="empty">无可用数据</div>'; return; }
  const W=D.workshop, A=D.agent||{};

  /* ---------- 工具 ---------- */
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function fmtBytes(b){b=Number(b)||0;const u=['B','KB','MB','GB','TB'];let i=0;while(b>=1024&&i<u.length-1){b/=1024;i++;}return b.toFixed(i?1:0)+' '+u[i];}
  function fmtNum(n){n=Number(n)||0;return n>=1e6?(n/1e6).toFixed(2)+'M':n>=1e3?(n/1e3).toFixed(1)+'k':String(n);}
  function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),2200);}
  function copy(text){ try{ navigator.clipboard.writeText(text); toast('已复制命令到剪贴板'); }catch(e){ toast(text); } }

  /* ---------- LIVE 探测 ---------- */
  async function boot(){
    try{
      const r=await fetch(API+'/api/data',{cache:'no-store'});
      if(r.ok){ const j=await r.json(); if(j&&j.agent){ A.agent=j.agent;A.skills=j.skills;A.tasks=j.tasks;A.conversations=j.conversations;A.anomalies=j.anomalies;LIVE=true; } }
    }catch(e){ /* 离线 */ }
    if(LIVE){ $('liveBadge').innerHTML='模式：<b style="color:var(--good)">已连接后端</b><br>实时运维已启用'; }
    init();
  }

  /* ---------- 动作（LIVE 走 API，离线复制命令） ---------- */
  async function api(path, payload){
    const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload||{})});
    return await r.json();
  }
  async function actUninstall(sk){
    if(LIVE){ const r=await api('/api/skill/uninstall',{id:sk.id,location:sk.location}); toast(r.ok?'已卸载：'+sk.id:(r.error||'卸载失败')); if(r.ok)location.reload(); }
    else { copy('mv "%WB%/skills/'+sk.id+'" "%WB%/_trash/"'.replace('%WB%', A.wb_root||'(你的 wb_root)')); }
  }
  async function actClean(){
    if(LIVE){ const sc=await api('/api/space/scan'); const keys=(sc.items||[]).map(i=>i.key);
      if(!keys.length){toast('无需清理');return;} const r=await api('/api/space/clean',{keys}); toast('已清理：'+(r.done||[]).join(', ')); }
    else { copy('清理 _trash 与 14 天前 logs（请在后端配置后执行）'); }
  }
  async function actBackup(){
    if(LIVE){ const r=await api('/api/backup'); toast(r.ok?('已备份：'+r.path):'备份失败'); }
    else { copy('zip -r agent_backup.zip sessions/ skills/*/SKILL.md'); }
  }
  function actOpenWB(sk, prompt){
    const q=(sk?('skill='+encodeURIComponent(sk.id)):'')+(prompt?('&prompt='+encodeURIComponent(prompt)):'');
    window.location.href='workbuddy://chat'+(q?'?'+q:'');
    toast('已尝试在 WorkBuddy 打开对话（实验性）');
  }

  /* ---------- 头部 KPI ---------- */
  function renderStats(){
    const a=A.agent||{};
    $('stats').innerHTML=
      '<div class="stat-pill"><b>'+(a.skill_count!=null?a.skill_count:'-')+'</b><small>Skill</small></div>'+
      '<div class="stat-pill"><b>'+fmtNum(a.total_token||0)+'</b><small>Token</small></div>'+
      '<div class="stat-pill"><b>'+fmtBytes(a.wb_disk_bytes||0)+'</b><small>本地占用</small></div>';
  }

  /* ---------- 大盘 ---------- */
  function wbAvatar(){
    return '<svg class="wb-avatar" width="170" height="200" viewBox="0 0 170 200">'+
      '<defs><linearGradient id="ag" x1="0" y1="0" x2="1" y2="1">'+
      '<stop offset="0" stop-color="#00d4ff"/><stop offset="1" stop-color="#a855f7"/></linearGradient></defs>'+
      '<line x1="85" y1="20" x2="85" y2="6" stroke="url(#ag)" stroke-width="3"/>'+
      '<circle cx="85" cy="4" r="4" fill="#00ffa3"/>'+
      '<rect x="40" y="28" width="90" height="70" rx="18" fill="#0c1428" stroke="url(#ag)" stroke-width="2.5"/>'+
      '<circle cx="66" cy="58" r="9" fill="#00d4ff"/><circle cx="104" cy="58" r="9" fill="#a855f7"/>'+
      '<rect x="64" y="76" width="42" height="6" rx="3" fill="#00ffa3"/>'+
      '<rect x="48" y="100" width="74" height="80" rx="16" fill="#0c1428" stroke="url(#ag)" stroke-width="2.5"/>'+
      '<rect x="62" y="118" width="46" height="8" rx="4" fill="#00d4ff" opacity=".8"/>'+
      '<rect x="62" y="134" width="46" height="8" rx="4" fill="#a855f7" opacity=".8"/>'+
      '<rect x="62" y="150" width="32" height="8" rx="4" fill="#00ffa3" opacity=".8"/>'+
      '</svg>';
  }
  function heatColor(hot){
    // hot 0..1
    if(hot>0.66)return '#ff4081'; if(hot>0.4)return '#ffab00'; if(hot>0.18)return '#00d4ff'; return '#4a6a8a';
  }
  function renderDashboard(){
    const a=A.agent||{}, skills=A.skills||[];
    const kpi=
      kpiCard('Skill 总数', a.skill_count||0,'已安装','rgba(0,212,255,.1)')+
      kpiCard('Agent Token', fmtNum(a.total_token||0),'真实累计','rgba(168,85,247,.1)')+
      kpiCard('Skill 估算', fmtNum(a.token_est_total||0),'单次触发体量','rgba(0,230,118,.1)')+
      kpiCard('对话数', a.conversation_count||0,'sessions','rgba(255,171,0,.1)')+
      kpiCard('任务数', a.task_count||0,'automations','rgba(255,64,129,.1)')+
      kpiCard('异常日志', a.anomaly_count||0,'logs','rgba(255,64,129,.08)');
    const arena='<div class="arena" id="arena">'+wbAvatar()+'<div class="arena-hint">WorkBuddy 人偶 · 背部胶囊=已安装 Skill（大小/颜色∝使用热度）</div></div>';
    const grid=skills.length?('<div class="sk-grid">'+skills.map(skCardHTML).join('')+'</div>'):'<div class="empty">未检测到已安装的 skill</div>';
    $('dashboard').innerHTML=
      '<div class="sec-head"><h2>🤖 大盘</h2>'+
      (LIVE?'<button class="btn bad" id="btnClean">🧹 清理空间</button><button class="btn" id="btnBackup">💾 备份对话</button>':'<span class="tag">离线模式：运维需启动 server.py</span>')+
      '</div>'+
      '<div class="kpi-row">'+kpi+'</div>'+arena+grid;
    if(LIVE){ $('btnClean').onclick=actClean; $('btnBackup').onclick=actBackup; }
    // 放置胶囊
    const arenaEl=$('arena');
    if(arenaEl && skills.length){
      const n=skills.length;
      const maxUse=Math.max(1,...skills.map(s=>s.usage_count||0));
      skills.forEach((s,i)=>{
        const ang=(Math.PI*2*i/n)-(Math.PI/2);
        const R=Math.min(arenaEl.clientWidth,arenaEl.clientHeight)/2-46;
        const cx=arenaEl.clientWidth/2, cy=arenaEl.clientHeight/2;
        const x=cx+Math.cos(ang)*R, y=cy+Math.sin(ang)*R;
        const hot=(s.usage_count||0)/maxUse;
        const size=Math.max(64,Math.min(150, 64+hot*86));
        const c=document.createElement('div');
        c.className='capsule';c.style.left=x+'px';c.style.top=y+'px';
        c.style.minWidth=size+'px';c.style.borderColor=heatColor(hot);
        c.style.color=heatColor(hot);
        c.innerHTML=esc(s.name)+' <span style="opacity:.7">·'+(s.usage_count||0)+'</span>';
        c.title=s.name+' | 使用'+(s.usage_count||0)+'次 | '+(s.source||'')+' | v'+(s.version||'?');
        c.onclick=()=>showSkillDetail(s);
        arenaEl.appendChild(c);
      });
    }
    $('dashboard').querySelectorAll('.sk-acts .btn').forEach(b=>{
      b.onclick=function(){const id=b.dataset.id;const sk=skById(id);const act=b.dataset.act;
        if(act==='uninstall')actUninstall(sk); else if(act==='openwb')actOpenWB(sk); else if(act==='chat')openChat(sk); };
    });
  }
  function kpiCard(l,v,s,clr){return '<div class="kpi" style="background:'+clr+'"><b>'+v+'</b><small>'+l+'</small><div style="font-size:10px;color:var(--muted);margin-top:2px">'+s+'</div></div>';}
  function skById(id){return (A.skills||[]).find(s=>s.id===id);}
  function skCardHTML(s){
    const srcTag=s.source==='git'?'<span class="tag g">git</span>':'<span class="tag y">local</span>';
    return '<div class="sk-card" data-id="'+esc(s.id)+'">'+
      '<div class="sk-name">'+esc(s.name)+'</div>'+
      '<div class="sk-desc">'+esc(s.description||'(无描述)')+'</div>'+
      '<div class="sk-meta">'+srcTag+'<span class="tag">v'+(s.version||'?')+'</span>'+
      '<span class="tag">🔗 '+(s.usage_count||0)+'次</span>'+
      '<span class="tag">⚡'+fmtNum(s.token_estimate||0)+'</span>'+
      '<span class="tag">💾'+fmtBytes(s.disk_bytes||0)+'</span></div>'+
      '<div class="sk-acts">'+
      '<button class="btn" data-id="'+esc(s.id)+'" data-act="openwb">在WB打开</button>'+
      '<button class="btn go" data-id="'+esc(s.id)+'" data-act="chat">对话</button>'+
      '<button class="btn bad" data-id="'+esc(s.id)+'" data-act="uninstall">卸载</button>'+
      '</div></div>';
  }
  function showSkillDetail(s){
    const src=s.source==='git'?'src-git':'src-local';
    $('sheet').innerHTML=
      '<button class="close" id="closeSheet">✕ 关闭</button>'+
      '<h2>'+esc(s.name)+' <span class="tag">v'+(s.version||'?')+'</span></h2>'+
      '<div class="meta">id: '+esc(s.id)+' · 位置: '+esc(s.location||'user')+'</div>'+
      '<div class="chips"><span class="badge use">🔗 '+(s.usage_count||0)+'次</span>'+
      '<span class="badge '+src+'">'+(s.source||'?')+'</span>'+
      (s.source_url?'<span class="badge src-git">'+esc(s.source_url)+'</span>':'')+'</div>'+
      '<div class="sec-title">功能描述</div><div class="rel">'+esc(s.description||'(无)')+'</div>'+
      '<div class="sec-title">资源占用</div><div class="rel">⚡ token 估算：'+fmtNum(s.token_estimate||0)+'<br>💾 磁盘：'+fmtBytes(s.disk_bytes||0)+'<br>🕒 最后使用：'+esc(s.last_used||'—')+'</div>'+
      '<div class="sec-title">操作</div><div class="sk-acts">'+
      '<button class="btn" id="dOpenwb">在 WorkBuddy 打开</button>'+
      '<button class="btn go" id="dChat">对话</button>'+
      '<button class="btn bad" id="dUninstall">卸载</button></div>';
    $('closeSheet').onclick=()=>$('detail').classList.remove('show');
    $('dOpenwb').onclick=()=>actOpenWB(s);
    $('dChat').onclick=()=>{ $('detail').classList.remove('show'); openChat(s); };
    $('dUninstall').onclick=()=>actUninstall(s);
    $('detail').classList.add('show');
  }

  /* ---------- 统计（workshop） ---------- */
  const CAT_ICON=['🧭','📐','💻','🧪','🧰','📚'];
  function cardType(p){const t=(p.type||'').toLowerCase();
    if(t.includes('prompt'))return'prompt'; if(t.includes('python')||t.includes('代码')||p.content_format==='python')return'python';
    if(t.includes('流程')||t.includes('规范'))return'process'; if(t.includes('配置')||/[.]json|[.]yaml|[.]ini|[.]toml/.test(t))return'config';
    if(t.includes('参考')||t.includes('文档'))return'ref'; return'default';}
  function renderStatsPage(){
    const pbid=W.parts_by_id||{}, all=Object.values(pbid);
    const totalUsage=all.reduce((s,p)=>s+(p.usage_count||0),0);
    const tm={};all.forEach(p=>{const t=cardType(p);tm[t]=(tm[t]||0)+1;});
    const heat=[...all].sort((a,b)=>(b.usage_count||0)-(a.usage_count||0)).slice(0,8);
    const sm={};all.forEach(p=>{const s=p.source_type||'initial';sm[s]=(sm[s]||0)+1;});
    const typeNames={prompt:'Prompt片段',python:'代码',process:'流程规范',config:'配置文件',ref:'参考文档',default:'其他'};
    const tBars=Object.entries(tm).map(([k,v])=>{const pct=Math.round(v/all.length*100);
      return'<div class="bar-row"><div class="bar-label">'+(typeNames[k]||k)+'</div><div class="bar-track"><div class="bar-fill" style="width:'+pct+'%"></div></div><div class="bar-count">'+pct+'%</div></div>';}).join('');
    const hList=heat.map((p,i)=>{const rc=i<3?'r'+(i+1):'rx';
      return'<li class="heat-item"><div class="heat-rank '+rc+'">'+(i+1)+'</div><div class="heat-name" data-id="'+esc(p.id)+'">'+esc(p.name)+'</div><div class="heat-val">🔗 '+(p.usage_count||0)+'</div></li>';}).join('');
    const sBars=Object.entries(sm).map(([k,v])=>{const pct=Math.round(v/all.length*100);const lbl={initial:'初始零件包',dismantled:'拆解产物',auto_generated:'自动生成'}[k]||k;
      return'<div class="src-bar"><label>'+lbl+'</label><div class="src-track"><div class="src-fill" style="width:'+pct+'%;background:var(--c0)"></div></div><div class="src-pct">'+pct+'%</div></div>';}).join('');
    $('stats').innerHTML='<div class="sec-head"><h2>📈 零件库统计</h2></div>'+
      '<div class="dash-grid">'+
      kpiCard('总零件数',W.stats.parts,'分布 '+W.stats.categories+' 类','rgba(0,212,255,.1)')+
      kpiCard('已组装 Skill',W.stats.generations,'累计使用 '+totalUsage+' 次','rgba(168,85,247,.1)')+
      kpiCard('最热零件',heat[0]?esc(heat[0].name):'—','','rgba(0,230,118,.1)')+
      kpiCard('来源渠道',Object.keys(sm).length,'种','rgba(255,171,0,.1)')+
      '</div>'+
      '<div class="ds-row"><div class="dash-section"><div class="ds-title">🏷️ 类型构成</div><div class="ds-scroll">'+tBars+'</div></div>'+
      '<div class="dash-section"><div class="ds-title">🔥 使用热度 TOP 8</div><div class="ds-scroll"><ul class="heat-list">'+hList+'</ul></div></div></div>'+
      '<div class="dash-section"><div class="ds-title">📦 来源占比</div><div class="ds-scroll">'+sBars+'</div></div>';
    $('stats').querySelectorAll('.heat-name').forEach(el=>el.onclick=()=>showDetail(el.dataset.id));
  }

  /* ---------- 货架 ---------- */
  let shelfFilter='', shelfQuery='';
  function renderShelfNav(){
    let pills='<div class="nav-pill active" data-ci="">▦ 全部</div>';
    W.categories.forEach((c,i)=>{pills+='<div class="nav-pill" data-ci="'+i+'">'+CAT_ICON[i]+' '+esc(c.name)+' <b>'+c.count+'</b></div>';});
    $('shelf').innerHTML='<div class="sec-head"><h2>📊 货架视图</h2></div><div class="shelf-nav">'+pills+'</div><div id="shelf-body"></div>';
    $('shelf').querySelectorAll('.nav-pill').forEach(p=>p.onclick=()=>{
      $('shelf').querySelectorAll('.nav-pill').forEach(x=>x.classList.remove('active'));p.classList.add('active');
      shelfFilter=p.dataset.ci;renderShelfBody();
    });
    renderShelfBody();
  }
  function renderShelfBody(){
    const body=$('shelf-body');if(!body)return;
    let html='';
    W.categories.forEach((cat,ci)=>{
      const fi=shelfFilter!==''?parseInt(shelfFilter):null; if(fi!==null&&ci!==fi)return;
      let all=[];Object.entries(cat.subs).forEach(([sn,ps])=>ps.forEach(p=>all.push(Object.assign({},p,{'_sub':sn}))));
      if(!all.length)return;
      const cards=all.map((p,i)=>'<div class="card" data-id="'+esc(p.id)+'" style="--c:var(--c'+ci+')">'+
        '<div class="card-name">'+esc(p.name)+'</div>'+
        '<div class="card-desc">'+esc(p.description||'')+'</div>'+
        '<div class="card-foot"><span class="use-tag">🔗 '+(p.usage_count||0)+'</span><span class="tag">'+esc(p.source_type||'initial')+'</span></div></div>').join('');
      html+='<div class="dept" style="--c:var(--c'+ci+')"><div class="dept-head"><h2>'+esc(cat.name)+'</h2><span class="cnt">'+all.length+' 个零件</span></div><div class="dept-body"><div class="shelf-cards">'+cards+'</div></div></div>';
    });
    body.innerHTML=html||'<div class="empty">没有匹配的零件</div>';
    body.querySelectorAll('.card').forEach(c=>c.onclick=()=>showDetail(c.dataset.id));
  }
  function renderShelf(query){shelfQuery=query||'';renderShelfBody();
    if(shelfQuery){const q=shelfQuery.toLowerCase();document.querySelectorAll('#shelf-body .card').forEach(el=>{
      const p=W.parts_by_id[el.dataset.id];if(!p){el.style.display='none';return;}
      const text=[p.name,p.description,p.category,p.sub_category,p.type,''].join(' ').toLowerCase();
      el.style.display=text.includes(q)?'':'none';});}
  }

  /* ---------- 生成记录 ---------- */
  function renderGens(query){
    const q=(query||'').toLowerCase(); let gens=W.generations;
    if(q)gens=gens.filter(g=>{const parts=(g.used_part_ids||[]).map(id=>{const p=W.parts_by_id[id];return p?p.name:'';}).join(' ');
      return [g.name,g.initial_query,parts].join(' ').toLowerCase().includes(q);});
    if(!gens.length){$('gens').innerHTML='<div class="empty">🔍 没有匹配的生成记录</div>';return;}
    let html='';
    gens.forEach(g=>{
      const color=g.auto_dismantled?'var(--good)':'var(--accent)';
      const parts=(g.used_part_ids||[]).map(id=>{const p=W.parts_by_id[id];return p?'<a data-id="'+id+'">'+esc(p.name)+'</a>':esc(id);}).join(' · ');
      html+='<div class="gen-card"><div class="gen-head"><div class="gen-dot" style="background:'+color+'"></div>'+
        '<h3>'+esc(g.name)+'</h3><div class="gen-meta"><span>'+esc(g.created_at||'')+'</span><span>'+(g.used_part_ids?g.used_part_ids.length:0)+' 个零件</span></div></div>'+
        '<div class="gen-body"><div class="gen-timeline">'+
        '<div class="gen-tl-item">📝 需求提出：'+esc(g.initial_query||g.name)+'</div>'+
        '<div class="gen-tl-item">🔍 零件检索：命中 '+(g.used_part_ids?g.used_part_ids.length:0)+' 个</div>'+
        '<div class="gen-tl-item">🔧 组装确认：'+esc(g.created_at||'')+'</div>'+
        (g.auto_dismantled?'<div class="gen-tl-item">♻️ 自动拆解回填</div>':'')+'</div>'+
        (parts?'<div class="gen-basis"><div class="gen-basis-title">📋 选用清单</div><div class="gen-basis-row">'+parts+'</div></div>':'')+
        '</div></div>';
    });
    $('gens').innerHTML='<div class="sec-head"><h2>📜 生成记录</h2></div><div class="gen-list">'+html+'</div>';
    $('gens').querySelectorAll('.gen-head').forEach(h=>h.onclick=()=>h.parentElement.classList.toggle('open'));
    $('gens').querySelectorAll('.gen-basis [data-id]').forEach(a=>a.onclick=e=>{e.stopPropagation();showDetail(a.dataset.id);});
  }

  /* ---------- 拆解任务 ---------- */
  function renderDismantle(query){
    const q=(query||'').toLowerCase(); let gens=W.generations;
    if(q)gens=gens.filter(g=>(g.name||'').toLowerCase().includes(q));
    if(!gens.length){$('dismantle').innerHTML='<div class="empty">🔍 没有匹配的拆解任务</div>';return;}
    let html='';
    gens.forEach(g=>{const done=g.auto_dismantled;
      html+='<div class="dsm-card '+(done?'done':'proc')+'"><div style="font-size:20px">'+(done?'🟢':'🟡')+'</div>'+
        '<div style="flex:1"><div style="font-weight:700">'+esc(g.name)+'</div><div style="font-size:11px;color:var(--muted)">标准深度 · '+esc(g.created_at||'')+'</div></div>'+
        '<div style="font-weight:700;color:'+(done?'var(--good)':'var(--warn)')+'">'+(done?'✅ 已完成':'⏳ 处理中')+'</div></div>';
    });
    $('dismantle').innerHTML='<div class="sec-head"><h2>📦 拆解任务</h2></div>'+html;
  }

  /* ---------- 对话 ---------- */
  let chatSkill=null, chatHist=[];
  function renderChat(){
    const convs=A.conversations||[];
    const lh=convs.length?convs.slice(0,40).map(c=>{
      const title=(c.title||c.custom_title||'(未命名对话)');
      const sub=(c.model||'')+' · '+(c.updated_at||c.created_at||'')+' · '+(c.message_count||0)+' 条';
      return '<div class="list-row" data-id="'+esc(c.id)+'"><div style="flex:1"><div class="lr-title">'+esc(title)+'</div><div class="lr-sub">'+esc(sub)+'</div></div><button class="lr-tag" data-open="'+esc(c.id)+'">在WB打开</button></div>';
    }).join(''):'<div class="empty">未检测到对话</div>';
    const skills=(A.skills||[]).map(s=>'<div class="sp'+(chatSkill&&chatSkill.id===s.id?' active':'')+'" data-id="'+esc(s.id)+'">'+esc(s.name)+'</div>').join('');
    $('chat').innerHTML='<div class="sec-head"><h2>💬 对话</h2>'+
      (LIVE?'<span class="tag g">后端已连接，可直接对话</span>':'<span class="tag y">离线：对话需启动 server.py + 配置 LLM</span>')+'</div>'+
      '<div class="chat-wrap"><div class="conv-list">'+lh+'</div>'+
      '<div class="chat-box"><div class="chat-bar"><b>与 Skill 对话</b>'+(chatSkill?'<span class="tag g">'+esc(chatSkill.name)+'</span>':'<span class="tag">未选择 skill</span>')+'</div>'+
      '<div class="skill-pick" id="skillPick">'+skills+'</div>'+
      '<div class="chat-msgs" id="chatMsgs"><div class="msg boss">👋 选择一个 Skill，然后开始对话。'+(LIVE?'':'（当前离线，请在设置页启动后端并配置 LLM key）')+'</div></div>'+
      '<div class="chat-in"><input id="chatInput" placeholder="输入消息…"><button class="btn primary" id="chatSend">发送</button></div></div></div>';
    $('chat').querySelectorAll('.list-row [data-open]').forEach(b=>b.onclick=()=>actOpenWB(null,''));
    $('chat').querySelectorAll('#skillPick .sp').forEach(sp=>sp.onclick=()=>{chatSkill=skById(sp.dataset.id);renderChat();});
    $('chatSend').onclick=sendChat;
    $('chatInput').addEventListener('keydown',e=>{if(e.key==='Enter')$('chatSend').click();});
  }
  async function sendChat(){
    const inp=$('chatInput'); const v=inp.value.trim(); if(!v)return; inp.value='';
    chatHist.push({role:'user',content:v});
    const msgs=$('chatMsgs'); const me=document.createElement('div');me.className='msg you';me.textContent=v;msgs.appendChild(me);
    const wait=document.createElement('div');wait.className='msg boss';wait.textContent='…';msgs.appendChild(wait);msgs.scrollTop=msgs.scrollHeight;
    if(LIVE){
      const r=await api('/api/chat',{skill_id:chatSkill?chatSkill.id:'',message:v,history:chatHist.slice(0,-1)});
      wait.remove();
      const m=document.createElement('div');m.className='msg boss';
      if(r.ok){m.textContent=r.reply;chatHist.push({role:'assistant',content:r.reply});}
      else{m.textContent='⚠️ '+(r.error||'对话失败');}
      msgs.appendChild(m);msgs.scrollTop=msgs.scrollHeight;
    } else { wait.remove(); const m=document.createElement('div');m.className='msg boss';
      m.textContent='离线模式无法对话。请启动 server.py 并在设置页配置 LLM key；或复制提示词到 WorkBuddy：';msgs.appendChild(m);
      copy((chatSkill?('请以 skill【'+chatSkill.name+'】的身份回答：')+'\\n':'')+v); }
  }
  function openChat(sk){ chatSkill=sk; switchTab('chat'); }

  /* ---------- 任务 ---------- */
  function renderTasks(){
    const tasks=A.tasks||[];
    if(!tasks.length){$('tasks').innerHTML='<div class="empty">📋 暂无自动化任务</div>';return;}
    const rows=tasks.map(t=>{
      const name=t.name||'(未命名)'; const st=t.status||'—';
      const sub=(t.schedule||t.rrule||'')+' · '+(t.last_run_at||t.validFrom||'');
      return '<div class="list-row"><div style="flex:1"><div class="lr-title">'+esc(name)+'</div><div class="lr-sub">'+esc(sub)+'</div></div>'+
        '<span class="lr-tag" style="color:'+(st==='ACTIVE'?'var(--good)':'var(--muted)')+'">'+esc(st)+'</span></div>';
    }).join('');
    $('tasks').innerHTML='<div class="sec-head"><h2>📋 自动化任务</h2></div>'+rows;
  }

  /* ---------- 异常日志 ---------- */
  function renderAnomalies(){
    const an=A.anomalies||[];
    if(!an.length){$('anomalies').innerHTML='<div class="empty">🚨 未发现异常日志</div>';return;}
    const rows=an.map(a=>{
      const samples=(a.sample||[]).map(s=>'<div class="rel">'+esc(s)+'</div>').join('');
      return '<div class="list-row" style="display:block"><div style="display:flex;gap:10px;align-items:center">'+
        '<div style="flex:1"><div class="lr-title">'+esc(a.file)+'</div><div class="lr-sub">命中 '+(a.error_lines||0)+' 处异常行</div></div>'+
        '<span class="lr-tag" style="color:var(--bad)">异常</span></div>'+samples+'</div>';
    }).join('');
    $('anomalies').innerHTML='<div class="sec-head"><h2>🚨 异常日志</h2></div>'+rows;
  }

  /* ---------- 设置 ---------- */
  function renderSettings(){
    const cfg=A.config||{};
    const llm=cfg.llm||{};
    $('settings').innerHTML='<div class="sec-head"><h2>⚙️ 设置</h2></div>'+
      (LIVE?'<div class="warn-banner">配置将保存到 config.json（不提交仓库）。修改后点击保存。</div>':'<div class="warn-banner">离线模式：保存需启动 server.py。以下为只读预览。</div>')+
      '<div class="setting-card"><div class="sec-title">🎨 主题</div>'+
      '<div style="display:flex;gap:10px"><button class="btn" id="thDark">🌙 暗色</button><button class="btn" id="thLight">☀️ 亮色</button></div>'+
      '<div class="sec-title" style="margin-top:16px">🧰 开发环境</div>'+
      '<label>发行版 / 环境</label><input value="WSL FDE" readonly>'+
      '<label>Python 路径</label><input value="C:/Users/dillon/.workbuddy/binaries/python/versions/3.13.12/python.exe" readonly>'+
      '<div class="sec-title" style="margin-top:16px">📦 Git 仓库</div>'+
      '<label>owner/repo</label><input id="cfgGit" value="'+esc((cfg.git&&cfg.git.repo)||'agent-grocery-workshop')+'">'+
      '<div class="sec-title" style="margin-top:16px">🤖 LLM（用于页面内对话）</div>'+
      '<label>Base URL</label><input id="cfgBase" value="'+esc(llm.base_url||'https://api.openai.com/v1')+'">'+
      '<label>API Key</label><input id="cfgKey" type="password" placeholder="sk-..." value="'+esc(llm.api_key||'')+'">'+
      '<label>Model</label><input id="cfgModel" value="'+esc(llm.model||'gpt-4o')+'">'+
      '<div class="hint">key 仅存于本地 config.json，不会提交。页面内对话由本地后端代理调用，不经过 WorkBuddy。</div>'+
      (LIVE?'<button class="btn primary" id="cfgSave" style="margin-top:14px">💾 保存配置</button>':'')+'</div>';
    $('thDark').onclick=()=>document.documentElement.setAttribute('data-theme','dark');
    $('thLight').onclick=()=>document.documentElement.setAttribute('data-theme','light');
    if(LIVE)$('cfgSave').onclick=async function(){
      const newCfg={git:{repo:$('cfgGit').value.trim()},llm:{base_url:$('cfgBase').value.trim(),api_key:$('cfgKey').value,model:$('cfgModel').value.trim()}};
      const r=await api('/api/config',newCfg); toast(r.ok?'配置已保存':'保存失败');
    };
  }

  /* ---------- 零件详情 ---------- */
  function showDetail(id){
    const p=W.parts_by_id[id];if(!p)return;
    const src=p.source_type||'initial';
    const sibs=(p.siblings||[]).map(s=>'<li><span class="pclick" data-id="'+esc(s.id)+'">'+esc(s.name)+'</span><span class="tag">'+esc(s.category)+' · '+(s.usage_count||0)+'次</span></li>').join('')||'<li class="tag">无同源伙伴</li>';
    const dep=(p.depends_on||[]).map(d=>{const dp=W.parts_by_id[d];return dp?'<span class="pclick" data-id="'+d+'">'+esc(dp.name)+'</span>':esc(d);}).join('、')||'无';
    $('sheet').innerHTML='<button class="close" id="closeSheet">✕ 关闭</button>'+
      '<h2>'+esc(p.name)+'</h2><div class="meta">'+esc(p.category||'')+' > '+esc(p.sub_category||'')+'</div>'+
      '<div class="chips"><span class="badge use">🔗 '+(p.usage_count||0)+'次</span><span class="badge src-'+esc(src)+'">'+esc(src)+'</span></div>'+
      '<div class="sec-title">内容</div><pre><code>'+esc(p.content||'')+'</code></pre>'+
      '<div class="sec-title">依赖</div><div class="rel">'+dep+'</div>'+
      '<div class="sec-title">同源伙伴</div><ul class="rel">'+sibs+'</ul>';
    $('sheet').querySelectorAll('.pclick[data-id]').forEach(el=>el.onclick=()=>showDetail(el.dataset.id));
    $('closeSheet').onclick=()=>$('detail').classList.remove('show');
    $('detail').classList.add('show');
  }

  /* ---------- Tab 切换 ---------- */
  $('search').oninput=function(e){
    const q=e.target.value; const tab=document.querySelector('.nav-item.active').dataset.tab;
    if(tab==='shelf')renderShelf(q); else if(tab==='gens')renderGens(q); else if(tab==='dismantle')renderDismantle(q);
    else if(tab==='chat'||tab==='tasks'||tab==='anomalies'||tab==='dashboard'||tab==='stats'){ /* 这些页搜索为全局，简单提示 */ }
  };
  function switchTab(tab){
    document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.tab===tab));
    ['dashboard','stats','shelf','gens','dismantle','chat','tasks','anomalies','settings'].forEach(id=>{$(''+id).hidden=id!==tab;});
    if(tab==='dashboard')renderDashboard();
    else if(tab==='stats')renderStatsPage();
    else if(tab==='shelf'){if(!$('shelf').innerHTML.trim())renderShelfNav();}
    else if(tab==='gens')renderGens('');
    else if(tab==='dismantle')renderDismantle('');
    else if(tab==='chat')renderChat();
    else if(tab==='tasks')renderTasks();
    else if(tab==='anomalies')renderAnomalies();
    else if(tab==='settings')renderSettings();
  }
  document.querySelectorAll('.nav-item').forEach(t=>t.onclick=()=>switchTab(t.dataset.tab));

  /* ---------- init ---------- */
  function init(){
    renderStats();
    switchTab('dashboard');
  }
  boot();
})();
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
