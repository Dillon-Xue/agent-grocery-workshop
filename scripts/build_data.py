#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_data.py - 聚合 WorkBuddy agent 真实数据 -> JSON 快照。

供 generate_console.py 内嵌进自包含 HTML（离线可读），
也供 server.py 在请求时实时重新聚合（写操作后刷新）。

数据源（实测确认真实存在、可读）：
  - <wb_root>/skills/                      已安装 skill（用户级 + 项目级）
  - <wb_root>/usage-log.json               skill 使用次数/最后使用（recentDates）
  - <wb_root>/workbuddy.db                 session_usage.used（agent 总 token 真实）
                                           automations（任务概览）
                                           sessions（对话列表）
  - <wb_root>/sessions/*.json              对话内容（messages 计数）
  - <wb_root>/logs/                        异常日志（error/exception 行）

仅依赖标准库。skill 级 token 为静态粗估（明确标注「估算」），
agent 总 token 为数据库真实求和。
"""
import os
import json
import sqlite3
import subprocess
import datetime
from pathlib import Path


def detect_wb_root():
    """WSL 环境下指向 Windows 用户目录；否则用本机 ~/.workbuddy。
    可用环境变量 WORKBUDDY_ROOT 覆盖（测试隔离用）。"""
    env = os.environ.get("WORKBUDDY_ROOT")
    if env:
        return env
    wsl_win = "/mnt/c/Users/dillon/.workbuddy"
    if os.path.isdir(wsl_win):
        return wsl_win
    home = os.path.expanduser("~/.workbuddy")
    if os.path.isdir(home):
        return home
    return home


def _run(cmd, cwd=None, timeout=5):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def load_usage_log(wb_root):
    p = os.path.join(wb_root, "usage-log.json")
    if not os.path.exists(p):
        return {}
    try:
        d = json.load(open(p, encoding="utf-8"))
        return d.get("skills", {})
    except Exception:
        return {}


def dir_size(path):
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


def parse_frontmatter(md_path):
    """解析 SKILL.md 顶部的 YAML frontmatter（简单 key: value / 多行续接）。"""
    try:
        lines = open(md_path, encoding="utf-8").read().splitlines()
    except Exception:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    buf = []
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        buf.append(ln)
    fm = {}
    cur = None
    for ln in buf:
        if ln and ln[0] not in " \t" and ":" in ln:
            k, _, v = ln.partition(":")
            fm[k.strip()] = v.strip()
            cur = k.strip()
        elif cur and (ln.startswith(" ") or ln.startswith("\t")):
            fm[cur] = (fm.get(cur, "") + " " + ln.strip()).strip()
    return fm


def estimate_token(md_path, skill_dir):
    """静态粗估单次触发体量（明确为估算，非真实累计）。"""
    est = 0
    try:
        est += max(200, len(open(md_path, encoding="utf-8").read()) // 2)
    except Exception:
        est += 200
    for root, _dirs, files in os.walk(skill_dir):
        for f in files:
            if f.endswith((".py", ".js", ".ts")):
                fp = os.path.join(root, f)
                try:
                    est += max(100, len(open(fp, encoding="utf-8", errors="ignore").read()) // 2)
                except Exception:
                    est += 100
    return est


def git_info(skill_dir):
    remote = _run(["git", "-C", skill_dir, "remote", "get-url", "origin"])
    version = _run(["git", "-C", skill_dir, "describe", "--tags", "--always"], timeout=4)
    if not version:
        try:
            version = datetime.datetime.fromtimestamp(
                os.path.getmtime(os.path.join(skill_dir, "SKILL.md"))
            ).strftime("%Y%m%d")
        except Exception:
            version = "unknown"
    return {"source": "git" if remote else "local", "source_url": remote, "version": version or "unknown"}


def scan_skills(skills_dir, usage, location):
    out = []
    if not os.path.isdir(skills_dir):
        return out
    for name in sorted(os.listdir(skills_dir)):
        sd = os.path.join(skills_dir, name)
        if not os.path.isdir(sd):
            continue
        md = os.path.join(sd, "SKILL.md")
        if not os.path.isfile(md):
            continue
        fm = parse_frontmatter(md)
        gi = git_info(sd)
        u = usage.get(name, {})
        rec = u.get("recentDates", []) or []
        out.append({
            "id": name,
            "name": fm.get("name", name),
            "description": fm.get("description", ""),
            "agent_created": str(fm.get("agent_created", "")).lower() == "true",
            "version": gi["version"],
            "source": gi["source"],
            "source_url": gi["source_url"],
            "location": location,
            "disk_bytes": dir_size(sd),
            "usage_count": len(rec),
            "last_used": u.get("lastUsedDate", ""),
            "first_seen": u.get("firstSeenDate", ""),
            "token_estimate": estimate_token(md, sd),
        })
    return out


def agent_token(db_path):
    if not os.path.exists(db_path):
        return 0
    try:
        c = sqlite3.connect(db_path)
        row = c.execute("SELECT COALESCE(SUM(used),0) FROM session_usage").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def load_tasks(db_path):
    if not os.path.exists(db_path):
        return []
    try:
        c = sqlite3.connect(db_path)
        cols = [r[1] for r in c.execute("PRAGMA table_info(automations)")]
        res = []
        for r in c.execute("SELECT * FROM automations"):
            d = dict(zip(cols, r))
            res.append({k: str(v) for k, v in d.items()})
        return res
    except Exception:
        return []


def load_conversations(db_path, sessions_dir):
    convs = []
    if os.path.exists(db_path):
        try:
            c = sqlite3.connect(db_path)
            cols = [r[1] for r in c.execute("PRAGMA table_info(sessions)")]
            if cols:
                for r in c.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 200"):
                    d = dict(zip(cols, r))
                    convs.append({k: str(v) for k, v in d.items()})
        except Exception:
            pass
    msg_counts = {}
    if os.path.isdir(sessions_dir):
        for f in os.listdir(sessions_dir):
            if f.endswith(".json"):
                fp = os.path.join(sessions_dir, f)
                try:
                    d = json.load(open(fp, encoding="utf-8"))
                    if isinstance(d, dict):
                        msg_counts[os.path.splitext(f)[0]] = len(d.get("messages", d.get("conversations", [])))
                except Exception:
                    pass
    for cv in convs:
        cv["message_count"] = msg_counts.get(cv.get("id", ""), cv.get("message_count", 0))
    return convs


def load_anomalies(logs_dir, limit=50):
    items = []
    if not os.path.isdir(logs_dir):
        return items
    for f in sorted(os.listdir(logs_dir)):
        fp = os.path.join(logs_dir, f)
        if not os.path.isfile(fp):
            continue
        try:
            lines = open(fp, encoding="utf-8", errors="ignore").read().splitlines()
        except Exception:
            continue
        errs = [l for l in lines if any(k in l.lower() for k in ["error", "exception", "traceback", "fail", "崩溃"])]
        if errs:
            items.append({"file": f, "error_lines": len(errs), "sample": errs[:3]})
    return items[:limit]


def build_agent_data(wb_root=None):
    wb_root = wb_root or detect_wb_root()
    usage = load_usage_log(wb_root)
    user_skills = scan_skills(os.path.join(wb_root, "skills"), usage, "user")
    proj_skills = scan_skills(os.path.join(os.getcwd(), ".workbuddy", "skills"), usage, "project")
    skills = user_skills + proj_skills
    db = os.path.join(wb_root, "workbuddy.db")
    total_token = agent_token(db)
    tasks = load_tasks(db)
    convs = load_conversations(db, os.path.join(wb_root, "sessions"))
    anomalies = load_anomalies(os.path.join(wb_root, "logs"))
    skills_disk = dir_size(os.path.join(wb_root, "skills"))
    wb_disk = dir_size(wb_root)
    token_est_total = sum(s["token_estimate"] for s in skills)
    return {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "wb_root": wb_root,
        "agent": {
            "skill_count": len(skills),
            "total_token": total_token,
            "skills_disk_bytes": skills_disk,
            "wb_disk_bytes": wb_disk,
            "anomaly_count": len(anomalies),
            "task_count": len(tasks),
            "conversation_count": len(convs),
            "token_est_total": token_est_total,
        },
        "skills": skills,
        "tasks": tasks,
        "conversations": convs,
        "anomalies": anomalies,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wb-root", default=None)
    ap.add_argument("--out", default=None, help="写出 JSON 路径，默认 stdout")
    a = ap.parse_args()
    data = build_agent_data(a.wb_root)
    txt = json.dumps(data, ensure_ascii=False, indent=2)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(txt)
        print("wrote", a.out, "skills=", len(data["skills"]))
    else:
        print(txt)
