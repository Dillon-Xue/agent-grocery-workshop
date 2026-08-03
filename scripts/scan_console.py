#!/usr/bin/env python3
"""WorkBuddy 控制台 — 数据聚合脚本
扫描 ~/.workbuddy/ 本地存储 + skills 目录，整合 7 个治理 skill 的数据逻辑，
产出 console_data.json 供 HTML 控制台渲染。

用法: python scan_console.py [--output <路径>]
"""

import json
import os
import re
import sys
import shutil
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

# ── 配置 ────────────────────────────────────────────
WORKBUDDY_HOME = os.path.expanduser("~/.workbuddy")
SKILLS_DIR = os.path.join(WORKBUDDY_HOME, "skills")
USAGE_LOG = os.path.join(WORKBUDDY_HOME, "usage-log.json")
PROJECTS_DIR = os.path.join(WORKBUDDY_HOME, "projects")

# 存储分类（与 storage-cleaner 对齐）
STORAGE_CATEGORIES = [
    {"id": "logs",          "name": "运行日志",     "path": os.path.join(WORKBUDDY_HOME, "logs"),             "risk": "safe",     "risk_label": "放心清理", "icon": "📋"},
    {"id": "traces",        "name": "追踪数据",     "path": os.path.join(WORKBUDDY_HOME, "traces"),           "risk": "safe",     "risk_label": "放心清理", "icon": "🔍"},
    {"id": "shell",         "name": "终端快照",     "path": os.path.join(WORKBUDDY_HOME, "shell-snapshots"),  "risk": "safe",     "risk_label": "放心清理", "icon": "🖥️"},
    {"id": "file_history",  "name": "文件历史",     "path": os.path.join(WORKBUDDY_HOME, "file-history"),     "risk": "safe",     "risk_label": "放心清理", "icon": "📝"},
    {"id": "clipboard",     "name": "剪贴板图片",   "path": os.path.join(WORKBUDDY_HOME, "clipboard-images"), "risk": "safe",     "risk_label": "放心清理", "icon": "🖼️"},
    {"id": "audit",         "name": "审计日志",     "path": os.path.join(WORKBUDDY_HOME, "audit-log"),        "risk": "safe",     "risk_label": "放心清理", "icon": "📊"},
    {"id": "connectors",    "name": "连接器缓存",   "path": os.path.join(WORKBUDDY_HOME, "connectors-market"),"risk": "safe",     "risk_label": "放心清理", "icon": "🔌"},
    {"id": "conversations", "name": "对话记录",     "path": PROJECTS_DIR,                                     "risk": "cautious", "risk_label": "谨慎清理", "icon": "💬"},
    {"id": "blobs",         "name": "截图附件",     "path": os.path.join(WORKBUDDY_HOME, "blobs"),            "risk": "cautious", "risk_label": "谨慎清理", "icon": "📎"},
    {"id": "app_cache",     "name": "会话缓存",     "path": os.path.join(WORKBUDDY_HOME, "app"),              "risk": "cautious", "risk_label": "谨慎清理", "icon": "⚡"},
    {"id": "skills",        "name": "Skill目录",    "path": SKILLS_DIR,                                      "risk": "skill",    "risk_label": "用技能管理", "icon": "🧩"},
    {"id": "binaries",      "name": "运行依赖",     "path": os.path.join(WORKBUDDY_HOME, "binaries"),         "risk": "never",    "risk_label": "不可删除", "icon": "🔧"},
    {"id": "vendor",        "name": "第三方库",     "path": os.path.join(WORKBUDDY_HOME, "vendor"),           "risk": "never",    "risk_label": "不可删除", "icon": "📦"},
    {"id": "plugins",       "name": "插件",         "path": os.path.join(WORKBUDDY_HOME, "plugins"),          "risk": "never",    "risk_label": "不可删除", "icon": "🔌"},
]

# Skill 中文名映射（与零件杂货铺对齐）
CN_NAMES = {
    "local-chat-search":           "本地会话搜索",
    "top-token-consuming":         "Token消耗审计",
    "skill-install-guard":         "安装去重守卫",
    "skill-compare":               "技能对比分析",
    "skill-audit":                 "技能审计清理",
    "storage-cleaner":             "存储空间清理",
    "skill-update-check":          "技能更新检查",
    "skill-scanner":               "安全风险扫描",
    "skill-search":                "智能技能搜索",
    "agent-grocery-workshop":      "Skill工坊",
    "fde-doc-assistant":           "FDE交付助手",
    "humanizer":                   "文本人性化",
    "Interview-Debrief":           "面试复盘教练",
    "PortfolioForge":              "个人网站铸造师",
    "Skill-Favor-Metric":          "Skill热度指标",
    "office-to-visual-html":       "文档可视化转换",
    "photo-editing":               "批量图片编辑",
    "playwright-browser-automation":"浏览器自动化",
    "web-access":                  "网络访问工具",
    "workbuddy-session-recovery":  "会话恢复工具",
    "i-have-adhd":                 "ADHD专注助手",
}

# 安全扫描规则（与 skill-scanner 对齐）
# ⚠️ 关键：所有 .* 必须改为有界非贪婪 .{0,N}?，否则在压缩成单行的 minified JS 上会灾难性回溯卡死
SECURITY_RULES = [
    (r'rm\s+-rf\s+/',                        "危", "rm -rf / 危险命令"),
    (r'rm\s+-rf\s+.{0,300}?\.workbuddy',     "危", "删除 .workbuddy 目录"),
    (r'(id_rsa|id_ed25519|\.ssh/)',          "危", "疑似读取 SSH 私钥"),
    (r'curl\s+.{0,300}?\|\s*(ba)?sh',        "危", "curl | bash 注入风险"),
    (r'\bsudo\b|\brunas\b',                  "高", "提权操作"),
    (r'eval\(|exec\(',                       "中", "动态代码执行"),
    (r'shell\s*=\s*True',                    "中", "shell=True 注入风险"),
    (r'\bcurl\b.{0,300}?-o\s|.{0,300}?\bwget\b', "中", "curl/wget 外部下载"),
    (r'rm\s+-rf\s+',                         "低", "递归删除操作"),
    (r'del\s+/[fF]',                         "低", "强制删除文件"),
]


# ── 工具函数 ────────────────────────────────────────

def cn_name(dir_name):
    return CN_NAMES.get(dir_name, dir_name)

def size_human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

def scan_dir_quick(path, max_files=500000):
    """单次遍历目录，同时算总字节数与文件数（替代 dir_total + rglob 双遍慢扫描）"""
    total_bytes = 0
    file_count = 0
    try:
        for r, ds, fs in os.walk(path):
            ds[:] = [d for d in ds if d != '.git']   # 跳过 git 内部对象，避免重复计数
            for f in fs:
                fp = os.path.join(r, f)
                try:
                    total_bytes += os.path.getsize(fp)
                    file_count += 1
                except OSError:
                    pass
                if file_count >= max_files:
                    return total_bytes, file_count
    except OSError:
        pass
    return total_bytes, file_count

_CJK_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
def estimate_tokens(text):
    """CJK 1:1, 非CJK 4:1 (与 top-token-consuming 同算法)，正则批量计数避免逐字符遍历"""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return cjk + (other + 3) // 4

# 遍历时跳过的目录（避免把 .git 对象库 / node_modules 当 Skill 内容读入）
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'dist', 'build'}
# token 估算时跳过的二进制扩展名（不被解码为文本）
TOKEN_SKIP_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.zip', '.gz', '.woff',
                  '.woff2', '.ttf', '.eot', '.pdf', '.mp4', '.mp3', '.bin', '.exe',
                  '.dll', '.so', '.dylib', '.pyc', '.svg'}
MAX_TOKEN_FILE = 256 * 1024  # 单文件 token 估算读取上限，超出按体积粗略估算
SEC_MAX_FILE = 64 * 1024     # 安全扫描单文件读取上限，超出跳过（避免超大单文件正则开销）

def parse_frontmatter(text):
    m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split('\n'):
        kv = re.match(r'^(\w[\w-]*):\s*(.*)', line)
        if kv:
            k = kv.group(1).strip()
            v = kv.group(2).strip().strip('"\'')
            fm[k] = v
    return fm

def read_file_safe(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return ""


# ── Skill 扫描 ──────────────────────────────────────

def scan_skills():
    """扫描 ~/.workbuddy/skills/ 下所有已安装 skill"""
    skills = []
    if not os.path.isdir(SKILLS_DIR):
        return skills

    for entry in sorted(os.listdir(SKILLS_DIR)):
        sdir = os.path.join(SKILLS_DIR, entry)
        if not os.path.isdir(sdir):
            continue
        smd = os.path.join(sdir, "SKILL.md")
        if not os.path.isfile(smd):
            continue

        content = read_file_safe(smd)
        fm = parse_frontmatter(content)
        body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)

        # ── 基本信息
        name = fm.get('name', entry)
        desc = fm.get('description', '')
        if not desc:
            for line in body.split('\n'):
                t = line.strip()
                if t and not t.startswith('#'):
                    desc = t[:120]
                    break

        # ── 来源推断
        source = "手动安装"
        if os.path.exists(os.path.join(sdir, '_skillhub_meta.json')):
            source = "SkillHub市场"
        elif entry.endswith('__skillhub'):
            source = "SkillHub市场"
        elif os.path.exists(os.path.join(sdir, '_knot_meta.json')):
            source = "Knot市场"
        elif fm.get('agent_created') == 'true':
            source = "本机自建"
        elif os.path.exists(os.path.join(sdir, '.git')):
            source = "GitHub"

        # ── 文件统计 + token 估算
        total_tokens = estimate_tokens(content)
        total_bytes = len(content.encode('utf-8'))
        fcount = 1

        for sub in ('scripts', 'references', 'assets'):
            sd = os.path.join(sdir, sub)
            if os.path.isdir(sd):
                for r, ds, fs in os.walk(sd):
                    ds[:] = [d for d in ds if d not in SKIP_DIRS]
                    for fn in fs:
                        ext = os.path.splitext(fn)[1].lower()
                        if ext in TOKEN_SKIP_EXT:
                            continue
                        fp = os.path.join(r, fn)
                        try:
                            sz = os.path.getsize(fp)
                        except OSError:
                            continue
                        total_bytes += sz
                        fcount += 1
                        if sz > MAX_TOKEN_FILE:
                            total_tokens += sz // 4   # 大文件按体积粗略估算
                            continue
                        fc = read_file_safe(fp)
                        total_tokens += estimate_tokens(fc)

        # ── 安装时间
        install_date = ""
        try:
            st = os.stat(sdir)
            ts = getattr(st, 'st_birthtime', 0) or st.st_ctime
            install_date = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        except:
            pass

        # ── 安全扫描
        tier_order = {"低": 0, "中": 1, "高": 2, "危": 3}
        sec_tier = "低"
        sec_findings = []
        for r, ds, fs in os.walk(sdir):
            ds[:] = [d for d in ds if d not in SKIP_DIRS]
            for fn in fs:
                if not fn.endswith(('.py', '.sh', '.ps1', '.bat', '.md', '.js', '.ts')):
                    continue
                fp = os.path.join(r, fn)
                try:
                    if os.path.getsize(fp) > SEC_MAX_FILE:
                        continue
                except OSError:
                    continue
                fc = read_file_safe(fp)
                for pat, sev, note in SECURITY_RULES:
                    if re.search(pat, fc):
                        sec_findings.append({
                            "file": os.path.relpath(os.path.join(r, fn), sdir),
                            "severity": sev,
                            "note": note,
                        })
                        if tier_order.get(sev, 0) > tier_order.get(sec_tier, 0):
                            sec_tier = sev

        token_anomaly = total_tokens >= 6000

        skills.append({
            "id": entry,
            "name": name,
            "display_name": cn_name(entry),
            "description": desc,
            "level": "用户级",
            "source": source,
            "install_date": install_date,
            "token": total_tokens,
            "size_bytes": total_bytes,
            "size_human": size_human(total_bytes),
            "file_count": fcount,
            "anomaly": token_anomaly,
            "security_tier": sec_tier,
            "security_findings": sec_findings,
        })

    return skills


# ── 使用数据 ────────────────────────────────────────

def load_usage():
    try:
        with open(USAGE_LOG, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def merge_usage(skills, usage):
    """合并 usage-log.json 数据到 skill 列表（与 skill-audit 两轨判定对齐）"""
    today = datetime.now().date()
    su = usage.get('skills', {})

    for s in skills:
        u = su.get(s['id'], {})
        last_str = u.get('lastUsedDate', '')
        recent = u.get('recentDates', [])

        s['last_used'] = last_str if last_str else None
        s['use_count'] = len(recent)
        s['days_unused'] = None

        if last_str:
            try:
                ld = datetime.strptime(last_str, '%Y-%m-%d').date()
                s['days_unused'] = (today - ld).days
            except:
                pass

        # 两轨判定
        if s.get('days_unused') is not None:
            d = s['days_unused']
            if d < 30:
                s['status'] = '🟢 保留'
                s['status_color'] = 'safe'
            elif d < 90:
                s['status'] = '🟠 可删除'
                s['status_color'] = 'warn'
            else:
                s['status'] = '🔴 建议删除'
                s['status_color'] = 'danger'
        elif s['install_date']:
            try:
                installed = datetime.strptime(s['install_date'], '%Y-%m-%d').date()
                if (today - installed).days >= 14:
                    s['status'] = '🔴 未使用'
                    s['status_color'] = 'danger'
                else:
                    s['status'] = '🟢 新装'
                    s['status_color'] = 'safe'
            except:
                s['status'] = '—'
                s['status_color'] = 'neutral'
        else:
            s['status'] = '—'
            s['status_color'] = 'neutral'


# ── 存储扫描 ────────────────────────────────────────

def scan_storage():
    cats = []
    safe_b = cautious_b = skill_b = never_b = 0

    for c in STORAGE_CATEGORIES:
        if os.path.isdir(c["path"]):
            sz, cnt = scan_dir_quick(c["path"])
        else:
            sz, cnt = 0, 0
        cats.append({**c, "size_bytes": sz, "size_human": size_human(sz), "file_count": cnt})

        if c["risk"] == "safe": safe_b += sz
        elif c["risk"] == "cautious": cautious_b += sz
        elif c["risk"] == "skill": skill_b += sz
        else: never_b += sz

    return cats, {
        "safe_total": size_human(safe_b), "safe_bytes": safe_b,
        "cautious_total": size_human(cautious_b), "cautious_bytes": cautious_b,
        "skill_total": size_human(skill_b), "skill_bytes": skill_b,
        "never_total": size_human(never_b), "never_bytes": never_b,
    }


# ── 对话统计 ────────────────────────────────────────

def scan_conversations():
    if not os.path.isdir(PROJECTS_DIR):
        return {"total": 0, "recent_7d": 0, "recent_30d": 0, "by_project": []}

    now = datetime.now()
    c7 = (now - timedelta(days=7)).timestamp() * 1000
    c30 = (now - timedelta(days=30)).timestamp() * 1000

    proj_map = {}
    total = r7 = r30 = 0

    for pd_name in os.listdir(PROJECTS_DIR):
        pp = os.path.join(PROJECTS_DIR, pd_name)
        if not os.path.isdir(pp):
            continue
        convos = [f for f in os.listdir(pp) if f.endswith('.jsonl')]
        proj_map[pd_name] = {"count": len(convos), "last_ts": 0}
        for fn in convos:
            total += 1
            try:
                mt = os.path.getmtime(os.path.join(pp, fn)) * 1000
                if mt > proj_map[pd_name]["last_ts"]:
                    proj_map[pd_name]["last_ts"] = mt
                if mt > c7: r7 += 1
                if mt > c30: r30 += 1
            except:
                pass

    by_proj = sorted(
        [{"project": k, "conversations": v["count"],
          "last_active": datetime.fromtimestamp(v["last_ts"]/1000).strftime('%Y-%m-%d') if v["last_ts"] else "—"}
         for k, v in proj_map.items()],
        key=lambda x: x["conversations"], reverse=True
    )

    return {"total": total, "recent_7d": r7, "recent_30d": r30, "by_project": by_proj[:10]}


# ── 重叠分析 ────────────────────────────────────────

def tokenize_zh(text):
    """轻量分词：拉丁词 + 中文二元语法（bigram），无需 jieba 即可捕捉共享短语"""
    text = (text or '').lower()
    toks = set(re.findall(r'[a-z]{3,}', text))
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        for k in range(len(run) - 1):
            toks.add(run[k:k + 2])          # 中文二元语法
    return toks

def analyze_overlaps(skills):
    overlaps = []
    n = len(skills)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = skills[i], skills[j]
            da = tokenize_zh(a.get('description', ''))
            db = tokenize_zh(b.get('description', ''))
            if not da or not db:
                continue
            common = da & db
            if len(common) >= 3:
                score = min(100, int(len(common) / max(len(da), len(db)) * 100))
                if score >= 12:
                    overlaps.append({
                        "skill_a": a["id"], "skill_a_name": a["display_name"],
                        "skill_b": b["id"], "skill_b_name": b["display_name"],
                        "score": score,
                    })
    return sorted(overlaps, key=lambda x: x["score"], reverse=True)


# ── 零件工坊数据（来自 agent-grocery-workshop skill）────────────
# 复用零件杂货铺自身的 library/（零件库）与 generations/（生成 / 拆解记录），
# 使其可视化模块（货架 / 生成 / 拆解 / 人偶胶囊）能在控制台内直接渲染。

def scan_workshop():
    grocery = os.path.join(SKILLS_DIR, "agent-grocery-workshop")
    lib_dir = os.path.join(grocery, "library")
    gen_dir = os.path.join(grocery, "generations")

    # ── 零件库：按 part.category（中文）→ sub_category → 零件 分组 ──
    cat_map = {}          # category_name -> {'subs': {sub: [part]}, 'count': n}
    parts_by_id = {}
    if os.path.isdir(lib_dir):
        for dir_name in sorted(os.listdir(lib_dir)):
            cpath = os.path.join(lib_dir, dir_name)
            if not os.path.isdir(cpath):
                continue
            for fn in sorted(os.listdir(cpath)):
                if not fn.endswith('.json'):
                    continue
                fp = os.path.join(cpath, fn)
                try:
                    part = json.load(open(fp, 'r', encoding='utf-8'))
                except Exception:
                    continue
                pid = part.get('id') or fn[:-5]
                part['id'] = pid
                cat = part.get('category') or dir_name
                sub = part.get('sub_category') or '未分类'
                if cat not in cat_map:
                    cat_map[cat] = {'subs': {}, 'count': 0}
                cat_map[cat]['subs'].setdefault(sub, []).append(part)
                cat_map[cat]['count'] += 1
                parts_by_id[pid] = part

    categories = [{'name': k, 'count': v['count'], 'subs': v['subs']}
                  for k, v in cat_map.items()]

    # ── 生成 / 拆解记录 ──
    # 与 workshop.load_generations 对齐：优先读 generations/<id>/manifest.json（嵌套，
    # 由 record_generation 落盘），同时兼容早期扁平 generations/*.json 旧格式。
    generations = []
    if os.path.isdir(gen_dir):
        for name in sorted(os.listdir(gen_dir)):
            mpath = os.path.join(gen_dir, name, "manifest.json")
            fp = mpath if os.path.isfile(mpath) else (os.path.join(gen_dir, name) if name.endswith(".json") else None)
            if not fp:
                continue
            try:
                g = json.load(open(fp, 'r', encoding='utf-8'))
                if isinstance(g, dict):
                    generations.append(g)
            except Exception:
                pass

    stats = {
        "parts": len(parts_by_id),
        "generations": len(generations),
        "categories": len(categories),
    }
    return {
        "stats": stats,
        "root": grocery,
        "categories": categories,
        "parts_by_id": parts_by_id,
        "generations": generations,
    }


# ── 主流程 ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WorkBuddy 控制台数据聚合")
    parser.add_argument('--output', '-o', default=None, help='输出 JSON 路径')
    args = parser.parse_args()

    t0 = datetime.now()
    print(f"🛠️  WorkBuddy 控制台 · 数据聚合  {t0.strftime('%H:%M:%S')}")
    print("─" * 48)

    # 1
    skills = scan_skills()
    print(f"  [1/5] Skill 扫描  →  {len(skills)} 个")

    # 2
    usage = load_usage()
    merge_usage(skills, usage)
    print(f"  [2/5] 使用记录  →  {sum(1 for s in skills if s['use_count'] > 0)} 个有记录")

    # 3
    sev_warn = sum(1 for s in skills if s['security_tier'] in ('高', '危'))
    total_findings = sum(len(s['security_findings']) for s in skills)
    print(f"  [3/5] 安全扫描  →  {total_findings} 条提示, {sev_warn} 个高风险")

    # 4
    cats, sumry = scan_storage()
    total_st = sum(c['size_bytes'] for c in cats)
    print(f"  [4/5] 存储扫描  →  {size_human(total_st)}")

    # 5
    convos = scan_conversations()
    print(f"  [5/6] 对话统计  →  {convos['total']} 个对话")

    # 6
    workshop = scan_workshop()
    print(f"  [6/6] Skill工坊  →  {workshop['stats']['parts']} 模板 / {workshop['stats']['categories']} 分类 / {workshop['stats']['generations']} 记录")

    # 重叠
    overlaps = analyze_overlaps(skills)

    # ── 组装输出 ──
    unused = [s for s in skills if s['status_color'] in ('warn', 'danger')]
    heavy = [s for s in skills if s['anomaly']]
    high_risk = [s for s in skills if s['security_tier'] in ('高', '危')]

    data = {
        "generated_at": t0.strftime('%Y-%m-%d %H:%M:%S'),
        "overview": {
            "total_storage_bytes": total_st,
            "total_storage": size_human(total_st),
            "total_skills": len(skills),
            "unused_skills": len(unused),
            "token_heavy": len(heavy),
            "conversations_7d": convos["recent_7d"],
            "conversations_30d": convos["recent_30d"],
            "total_conversations": convos["total"],
            "security_warnings": total_findings,
            "high_risk_count": len(high_risk),
            "overlap_pairs": len(overlaps),
        },
        "skills": skills,
        "workshop": workshop,
        "storage": {"categories": cats, "summary": sumry},
        "conversations": convos,
        "overlaps": overlaps,
        "security": {
            "high_risk": [
                {"name": s["display_name"], "id": s["id"],
                 "tier": s["security_tier"], "findings": s["security_findings"]}
                for s in high_risk
            ],
            "total_findings": total_findings,
        },
        "unused_skills": [
            {"name": s["display_name"], "id": s["id"],
             "days_unused": s.get("days_unused"), "status": s["status"]}
            for s in unused
        ],
    }

    out = args.output or os.path.join(os.path.dirname(os.path.abspath(__file__)), "console_data.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 人偶图：复制到工作目录 assets/，供 console.html 相对路径引用（离线可用）──
    here = os.path.dirname(os.path.abspath(__file__))
    avatar_src = os.path.join(SKILLS_DIR, "agent-grocery-workshop", "assets", "sprite_avatar.png")
    if os.path.isfile(avatar_src):
        assets_dir = os.path.join(here, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        try:
            shutil.copy2(avatar_src, os.path.join(assets_dir, "sprite_avatar.png"))
        except Exception as ex:
            print(f"  [!] 人偶图复制跳过：{ex}")

    # ── 内联注入：把数据写进 console.html，使其可双击离线使用 ──
    # 用稳定分隔符，可反复重写（无论当前是 null 还是旧 JSON）
    html_path = os.path.join(here, "console.html")
    embed_re = re.compile(r'const EMBEDDED_DATA = .*?/\*__WB_DATA_END__\*/')
    if os.path.isfile(html_path):
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html = f.read()
            m = embed_re.search(html)
            if m:
                json_inline = json.dumps(data, ensure_ascii=False)
                new_block = f"const EMBEDDED_DATA = {json_inline};/*__WB_DATA_END__*/"
                # 用切片替换，避免 re.sub 替换串对反斜杠的二次转义（会破坏 JSON 转义）
                html = html[:m.start()] + new_block + html[m.end():]
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"  [✓] 已内联数据 → console.html（可双击离线打开）")
            else:
                print(f"  [!] 内联跳过：未找到注入锚点")
        except Exception as ex:
            print(f"  [!] 内联跳过：{ex}")

    elapsed = (datetime.now() - t0).total_seconds()
    print("─" * 48)
    print(f"✅ 完成  |  {len(skills)} Skill | {size_human(total_st)} | {convos['total']} 对话 | {elapsed:.1f}s")
    print(f"📁 {out}")


if __name__ == '__main__':
    main()
