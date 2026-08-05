#!/usr/bin/env python3
"""WorkBuddy 控制台后端服务
提供静态文件、对话检索、安全清理、Skill 对话等 API。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workshop import Workshop

# ── 配置 ──
WORKBUDDY_ROOT = Path.home() / ".workbuddy"
SKILLS_DIR = WORKBUDDY_ROOT / "skills"
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "console_config.json"
BACKUP_DIR = WORKBUDDY_ROOT / "console-backups"

# WorkBuddy 主程序路径（用于「在 WorkBuddy 打开」）
WORKBUDDY_EXE_CANDIDATES = [
    Path("D:/WorkBuddy/WorkBuddy.exe"),
    Path.home() / "AppData" / "Local" / "WorkBuddy" / "WorkBuddy.exe",
    Path("C:/Program Files/WorkBuddy/WorkBuddy.exe"),
]


def find_workbuddy_exe():
    for p in WORKBUDDY_EXE_CANDIDATES:
        if p.exists():
            return p
    return None

# 可清理分类白名单（按 risk 分级）
CLEANABLE_CATEGORIES = {
    "logs": {"risk": "safe", "path": WORKBUDDY_ROOT / "logs"},
    "traces": {"risk": "safe", "path": WORKBUDDY_ROOT / "traces"},
    "shell": {"risk": "safe", "path": WORKBUDDY_ROOT / "shell-snapshots"},
    "file_history": {"risk": "safe", "path": WORKBUDDY_ROOT / "file-history"},
    "clipboard": {"risk": "safe", "path": WORKBUDDY_ROOT / "clipboard-images"},
    "audit": {"risk": "safe", "path": WORKBUDDY_ROOT / "audit-log"},
    "connectors": {"risk": "safe", "path": WORKBUDDY_ROOT / "connectors-market"},
    "conversations": {"risk": "cautious", "path": WORKBUDDY_ROOT / "projects"},
    "blobs": {"risk": "cautious", "path": WORKBUDDY_ROOT / "blobs"},
    "app_cache": {"risk": "cautious", "path": WORKBUDDY_ROOT / "app"},
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "llm": {"base_url": "", "api_key": "", "model": "gpt-4o"},
        "skillhub": {"base_url": "https://api.skillhub.cn", "api_key": ""},
    }


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


CONFIG = load_config()


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 关闭默认日志

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, msg, code=400):
        self._json({"ok": False, "error": msg}, code)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/console.html"):
            path = "/scripts/console.html"
        if path == "/api/config":
            return self._json({"ok": True, "config": {**CONFIG.get("llm", {}), "skillhub": CONFIG.get("skillhub", {})}})
        if path.startswith("/api/"):
            return self._error("Unsupported GET endpoint", 404)
        # 静态文件
        fp = (BASE_DIR / path.lstrip("/")).resolve()
        if not str(fp).startswith(str(BASE_DIR)):
            return self._error("Forbidden", 403)
        if not fp.exists() or fp.is_dir():
            return self._error("Not found", 404)
        content_type = "text/html"
        if fp.suffix == ".js":
            content_type = "application/javascript"
        elif fp.suffix == ".json":
            content_type = "application/json"
        elif fp.suffix in (".png", ".jpg", ".jpeg", ".gif", ".svg"):
            content_type = f"image/{fp.suffix.lstrip('.')}"
        elif fp.suffix == ".css":
            content_type = "text/css"
        data = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = json.loads(self._read_body() or "{}")
        except Exception:
            return self._error("Invalid JSON")

        if path == "/api/search":
            return self.handle_search(payload)
        if path == "/api/clean/preview":
            return self.handle_clean_preview(payload)
        if path == "/api/clean":
            return self.handle_clean(payload)
        if path == "/api/chat":
            return self.handle_chat(payload)
        if path == "/api/config":
            return self.handle_config(payload)
        if path == "/api/conversations":
            return self.handle_list_conversations(payload)
        if path == "/api/conversation/detail":
            return self.handle_conversation_detail(payload)
        if path == "/api/session/summarize":
            return self.handle_summarize(payload)
        if path == "/api/session/delete":
            return self.handle_session_delete(payload)
        if path == "/api/skill/delete":
            return self.handle_skill_delete(payload)
        if path == "/api/skill/check-update":
            return self.handle_skill_check_update(payload)
        if path == "/api/open-workbuddy":
            return self.handle_open_workbuddy(payload)
        if path == "/api/skill/generate-plan":
            return self.handle_skill_generate_plan(payload)
        if path == "/api/skill/generate":
            return self.handle_skill_generate(payload)
        if path == "/api/skill/install":
            return self.handle_skill_install(payload)
        return self._error("Unsupported POST endpoint", 404)

    def handle_search(self, payload):
        query = (payload.get("query") or "").strip()
        scope = payload.get("scope", "all")
        max_results = int(payload.get("max_results", 20))
        if not query:
            return self._json({"ok": True, "total_results": 0, "results": []})
        search_py = SKILLS_DIR / "local-chat-search" / "scripts" / "search.py"
        if not search_py.exists():
            return self._error("local-chat-search 脚本未找到")
        cmd = [
            sys.executable,
            str(search_py),
            "--query", query,
            "--scope", scope,
            "--max-results", str(max_results),
            "--sort-by", payload.get("sort_by", "relevance"),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                return self._error(proc.stderr or "检索脚本执行失败")
            data = json.loads(proc.stdout)
            return self._json({"ok": True, **data})
        except subprocess.TimeoutExpired:
            return self._error("检索超时", 504)
        except Exception as e:
            return self._error(str(e))

    def handle_clean_preview(self, payload):
        cat_id = payload.get("category_id")
        if cat_id not in CLEANABLE_CATEGORIES:
            return self._error(f"未知或不允许清理的分类: {cat_id}")
        info = CLEANABLE_CATEGORIES[cat_id]
        target = info["path"]
        if not target.exists():
            return self._json({"ok": True, "risk": info["risk"], "files": [], "total_size": 0, "total_files": 0})
        files = []
        total = 0
        for root, dirs, names in os.walk(target):
            for n in names:
                fp = Path(root) / n
                try:
                    st = fp.stat()
                    files.append({"path": str(fp), "size": st.st_size})
                    total += st.st_size
                except Exception:
                    pass
        files.sort(key=lambda x: x["size"], reverse=True)
        return self._json({"ok": True, "risk": info["risk"], "files": files[:200], "total_size": total, "total_files": len(files)})

    def handle_clean(self, payload):
        cat_id = payload.get("category_id")
        if cat_id not in CLEANABLE_CATEGORIES:
            return self._error(f"未知或不允许清理的分类: {cat_id}")
        info = CLEANABLE_CATEGORIES[cat_id]
        target = info["path"]
        if not target.exists():
            return self._json({"ok": True, "deleted": 0, "freed": 0})

        # 安全策略：cautious 分类必须显式确认
        if info["risk"] == "cautious" and not payload.get("confirmed"):
            return self._error("该分类为谨慎清理，请先在弹窗中确认", 403)

        # 计算体量用于提示
        freed = 0
        try:
            for root, dirs, names in os.walk(target):
                for n in names:
                    try:
                        freed += (Path(root) / n).stat().st_size
                    except Exception:
                        pass
        except Exception:
            pass

        # 先备份（原样复制到 backup 目录）
        backup = BACKUP_DIR / f"{cat_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup)
        except Exception as e:
            return self._error(f"备份失败，取消清理: {e}")

        # 放入系统回收站（可恢复），而非直接删除
        try:
            send_to_recycle_bin(target)
        except Exception as e:
            return self._error(f"放入回收站失败: {e}（备份已生成于 {backup}）")
        return self._json({
            "ok": True, "deleted": 1, "freed": freed, "backup": str(backup),
            "note": "已放入系统回收站，可从回收站恢复；同时已原样备份。",
        })

    def handle_chat(self, payload):
        llm = CONFIG.get("llm", {})
        base_url = (payload.get("base_url") or llm.get("base_url", "")).rstrip("/")
        api_key = payload.get("api_key") or llm.get("api_key", "")
        model = payload.get("model") or llm.get("model", "gpt-4o")
        if not base_url or not api_key:
            return self._error("请先配置 LLM Base URL 与 API Key", 403)
        messages = payload.get("messages", [])
        if not messages:
            return self._error("消息为空")
        skill_id = payload.get("skill_id")
        system = ""
        if skill_id:
            skill_md = SKILLS_DIR / skill_id / "SKILL.md"
            if skill_md.exists():
                system = skill_md.read_text(encoding="utf-8")[:4000]
        try:
            import urllib.request
            req_data = json.dumps({"model": model, "messages": ([{"role": "system", "content": system}] if system else []) + messages}).encode("utf-8")
            req = urllib.request.Request(f"{base_url}/chat/completions", data=req_data, method="POST")
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                return self._json({"ok": True, "content": content})
        except Exception as e:
            return self._error(str(e))

    def handle_config(self, payload):
        global CONFIG
        CONFIG["llm"] = payload.get("llm", CONFIG.get("llm", {}))
        if "skillhub" in payload:
            CONFIG["skillhub"] = {**CONFIG.get("skillhub", {}), **payload.get("skillhub", {})}
        save_config(CONFIG)
        return self._json({"ok": True})

    # ── 会话列举 ──
    def handle_list_conversations(self, payload):
        only = payload.get("category")
        groups = []
        if not only or only == "conversations":
            if CONVERSATIONS_DIR.exists():
                for proj in CONVERSATIONS_DIR.iterdir():
                    if not proj.is_dir():
                        continue
                    sessions = []
                    for f in proj.glob("*.jsonl"):
                        try:
                            st = f.stat()
                            sessions.append({
                                "id": f.stem, "title": extract_session_title(f),
                                "size": st.st_size, "mtime": _fmt_time(st.st_mtime),
                                "mtime_raw": st.st_mtime,
                                "rel": f"projects/{proj.name}/{f.name}",
                            })
                        except Exception:
                            pass
                    if sessions:
                        sessions.sort(key=lambda x: x["mtime_raw"], reverse=True)
                        last_mtime = sessions[0]["mtime_raw"]
                        for s in sessions:
                            s.pop("mtime_raw", None)
                        groups.append({"category": "conversations", "project": proj.name,
                                       "last_mtime": last_mtime, "sessions": sessions})
        if not only or only == "app_cache":
            app_dir = WORKBUDDY_ROOT / "app"
            if app_dir.exists():
                sess_files = list(app_dir.glob("*.json")) + list(app_dir.glob("*.jsonl"))
                sessions = []
                for f in sess_files:
                    try:
                        st = f.stat()
                        sessions.append({
                            "id": f.stem, "title": extract_session_title(f),
                            "size": st.st_size, "mtime": _fmt_time(st.st_mtime),
                            "mtime_raw": st.st_mtime,
                            "rel": f"app/{f.name}",
                        })
                    except Exception:
                        pass
                if sessions:
                    sessions.sort(key=lambda x: x["mtime_raw"], reverse=True)
                    last_mtime = sessions[0]["mtime_raw"]
                    for s in sessions:
                        s.pop("mtime_raw", None)
                    groups.append({"category": "app_cache", "project": "app（会话缓存）",
                                   "last_mtime": last_mtime, "sessions": sessions})
        groups.sort(key=lambda x: x["last_mtime"], reverse=True)
        for g in groups:
            g.pop("last_mtime", None)
        return self._json({"ok": True, "groups": groups})

    def handle_conversation_detail(self, payload):
        """读取单个 WorkBuddy 会话文件，返回结构化消息列表。"""
        rel = payload.get("rel") or ""
        if not rel or ".." in rel:
            return self._error("非法的会话路径")
        fp = WORKBUDDY_ROOT / rel
        if not safe_under(WORKBUDDY_ROOT, fp) or not fp.exists():
            return self._error(f"会话不存在: {rel}")

        messages = []
        try:
            if fp.suffix == ".jsonl":
                for line in fp.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    t = obj.get("type")
                    if t == "message":
                        role = obj.get("role") or "unknown"
                        content = obj.get("content") or ""
                        text = ""
                        if isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict):
                                    if part.get("type") in ("input_text", "output_text"):
                                        text += (part.get("text") or "")
                                    elif part.get("type") == "text":
                                        text += (part.get("text") or "")
                        elif isinstance(content, str):
                            text = content
                        text = strip_wrapped(text).strip()
                        if text:
                            messages.append({"role": role, "content": text, "time": obj.get("time") or obj.get("timestamp") or ""})
                    elif t == "reasoning":
                        rc = obj.get("rawContent") or obj.get("content") or ""
                        if isinstance(rc, list):
                            for part in rc:
                                if isinstance(part, dict) and part.get("type") == "reasoning_text":
                                    txt = (part.get("text") or "").strip()
                                    if txt:
                                        messages.append({"role": "reasoning", "content": txt[:600], "time": ""})
            else:
                # 普通 JSON 会话缓存，尝试读取 message 数组
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
                msgs = data if isinstance(data, list) else data.get("messages", [])
                for m in msgs:
                    role = m.get("role") or "unknown"
                    content = m.get("content") or ""
                    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                    text = strip_wrapped(text).strip()
                    if text:
                        messages.append({"role": role, "content": text, "time": m.get("time") or m.get("timestamp") or ""})
        except Exception as e:
            return self._json({"ok": False, "error": f"读取会话失败: {e}"})

        return self._json({"ok": True, "rel": rel, "messages": messages})

    # ── 会话总结（AI / 规则回退）──
    def handle_summarize(self, payload):
        items = payload.get("sessions") or []
        if not items:
            return self._error("未选择任何会话")
        llm = CONFIG.get("llm", {})
        summaries = []
        for it in items:
            rel = it.get("rel") or ""
            fp = WORKBUDDY_ROOT / rel
            if not safe_under(WORKBUDDY_ROOT, fp) or not fp.exists():
                summaries.append({"rel": rel, "title": it.get("title", ""), "summary": "（文件不存在或越权）", "used_ai": False})
                continue
            text = extract_conversation_text(fp)
            summary, used_ai = summarize_text(text, llm)
            summaries.append({"rel": rel, "title": it.get("title", ""), "summary": summary, "used_ai": used_ai})
        return self._json({"ok": True, "summaries": summaries})

    # ── 会话删除：强制备份总结 + 回收站 ──
    def handle_session_delete(self, payload):
        items = payload.get("sessions") or []
        if not items:
            return self._error("未选择任何会话")
        targets = []
        for it in items:
            rel = it.get("rel") or ""
            fp = WORKBUDDY_ROOT / rel
            if not safe_under(WORKBUDDY_ROOT, fp) or not fp.exists():
                return self._error(f"非法或不存在的路径: {rel}")
            targets.append((rel, fp))
        # 备份（强制）：复制原始 + 生成 AI/规则总结
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"sessions_{ts}"
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return self._error(f"创建备份目录失败: {e}")
        llm = CONFIG.get("llm", {})
        summary_parts = []
        for rel, fp in targets:
            try:
                dest = backup / rel.replace("/", "_")
                if fp.is_dir():
                    shutil.copytree(fp, dest)
                else:
                    shutil.copy2(fp, dest)
                text = extract_conversation_text(fp)
                s, used_ai = summarize_text(text, llm)
                summary_parts.append(f"## {rel} （AI总结: {'是' if used_ai else '否'}）\n\n{s}\n")
            except Exception as e:
                return self._error(f"备份失败（已取消删除）: {e}")
        try:
            (backup / "SUMMARY.md").write_text("\n---\n\n".join(summary_parts), encoding="utf-8")
        except Exception:
            pass
        # 放入回收站（可恢复）
        deleted = 0
        errors = []
        for rel, fp in targets:
            try:
                send_to_recycle_bin(fp)
                deleted += 1
            except Exception as e:
                errors.append(f"{rel}: {e}")
        return self._json({
            "ok": True, "deleted": deleted, "backup": str(backup), "errors": errors,
            "note": "已放入系统回收站，可从回收站恢复；同时已在备份目录生成会话总结。",
        })

    # ── Skill 卸载：备份 + 回收站 ──
    def handle_skill_delete(self, payload):
        skill_id = payload.get("skill_id") or ""
        if not skill_id or ".." in skill_id or skill_id.startswith("/") or skill_id.startswith("\\"):
            return self._error("非法的 Skill ID")
        fp = SKILLS_DIR / skill_id
        if not safe_under(SKILLS_DIR, fp) or not fp.exists():
            return self._error(f"Skill 不存在: {skill_id}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"skill_{skill_id}_{ts}"
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copytree(fp, backup)
        except Exception as e:
            return self._error(f"备份失败（已取消删除）: {e}")
        try:
            send_to_recycle_bin(fp)
        except Exception as e:
            return self._error(f"放入回收站失败: {e}（备份已生成于 {backup}）")
        return self._json({
            "ok": True, "backup": str(backup),
            "note": f"Skill {skill_id} 已放入系统回收站，可从回收站恢复；备份位于 {backup}。",
        })

    # ── Skill 升级检查：查询 SkillHub 最新版本 ──
    def handle_skill_check_update(self, payload):
        skill_id = payload.get("skill_id") or ""
        if not skill_id or ".." in skill_id or skill_id.startswith("/") or skill_id.startswith("\\"):
            return self._error("非法的 Skill ID")
        fp = SKILLS_DIR / skill_id
        if not safe_under(SKILLS_DIR, fp) or not fp.exists():
            return self._error(f"Skill 不存在: {skill_id}")

        meta_path = fp / "_skillhub_meta.json"
        if not meta_path.exists():
            return self._json({
                "ok": True,
                "checkable": False,
                "reason": "该 Skill 不是从 SkillHub / BuiltinMarket 安装，没有 _skillhub_meta.json，无法在线检查版本。",
            })

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            return self._json({"ok": True, "checkable": False, "reason": f"读取 _skillhub_meta.json 失败: {e}"})

        source = (meta.get("source") or "").lower()
        if source == "marketplace":
            return self._json({
                "ok": True,
                "checkable": False,
                "reason": "该 Skill 来自 WorkBuddy 内置市场（BuiltinMarket），暂不支持通过此接口在线检查版本。",
            })
        if source != "skillhub":
            return self._json({
                "ok": True,
                "checkable": False,
                "reason": f"该 Skill 来源为 {meta.get('source') or '未知'}，不支持在线检查版本。",
            })

        slug = meta.get("slug") or meta.get("name") or skill_id
        current_version = meta.get("version") or "未知"
        hub_cfg = CONFIG.get("skillhub", {})
        base_url = (hub_cfg.get("base_url") or "https://api.skillhub.cn").rstrip("/")

        try:
            detail = fetch_skillhub_skill(base_url, slug, hub_cfg.get("api_key") or "")
        except urllib.error.HTTPError as e:
            return self._json({"ok": False, "error": f"SkillHub 返回 HTTP {e.code}，请检查 SkillHub Base URL 或 slug（{slug}）是否正确。"})
        except Exception as e:
            return self._json({"ok": False, "error": f"查询 SkillHub 失败: {e}"})

        latest = detail.get("latestVersion") or {}
        latest_version = latest.get("version") or ""
        changelog = latest.get("changelog") or ""
        skill_info = detail.get("skill") or {}
        skill_name = skill_info.get("displayName") or meta.get("name") or skill_id

        if not latest_version:
            return self._json({"ok": False, "error": "SkillHub 未返回最新版本信息。"})

        has_update = compare_version(current_version, latest_version) < 0
        advice = ""
        if has_update:
            advice = f"建议升级至 v{latest_version}。"
            if changelog:
                advice += f" 更新说明：{changelog}"
        else:
            advice = "当前已是最新版本，无需升级。"

        return self._json({
            "ok": True,
            "checkable": True,
            "skill_id": skill_id,
            "skill_name": skill_name,
            "slug": slug,
            "source": meta.get("source"),
            "current_version": current_version,
            "latest_version": latest_version,
            "has_update": has_update,
            "changelog": changelog,
            "advice": advice,
            "skillhub_url": f"https://skillhub.tencent.com/skills/{slug}",
        })

    def handle_open_workbuddy(self, payload):
        """启动 WorkBuddy 主程序；如果传入 skill_id，同时打开该 skill 所在目录。"""
        skill_id = payload.get("skill_id") or ""
        if skill_id and (".." in skill_id or skill_id.startswith("/") or skill_id.startswith("\\")):
            return self._error("非法的 Skill ID")

        exe = find_workbuddy_exe()
        if not exe:
            return self._json({"ok": False, "error": "未找到 WorkBuddy 主程序（WorkBuddy.exe）。请确认 WorkBuddy 已安装。"})

        # 在 Windows 上以 detached 方式启动，避免阻塞 HTTP 请求
        try:
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        except AttributeError:
            flags = 0
        try:
            subprocess.Popen([str(exe)], shell=False, creationflags=flags, close_fds=True)
        except Exception as e:
            return self._json({"ok": False, "error": f"启动 WorkBuddy 失败: {e}"})

        opened_path = None
        if skill_id:
            skill_path = SKILLS_DIR / skill_id
            if safe_under(SKILLS_DIR, skill_path) and skill_path.exists():
                try:
                    subprocess.Popen(["explorer", str(skill_path.resolve())], shell=False)
                    opened_path = str(skill_path)
                except Exception:
                    pass

        return self._json({
            "ok": True,
            "message": "已启动 WorkBuddy。",
            "exe": str(exe),
            "opened_path": opened_path,
        })

    # ── 自动生成 Skill ──
    def handle_skill_generate_plan(self, payload):
        requirements = payload.get('requirements') or {}
        if not requirements.get('name') or not requirements.get('description'):
            return self._error('请提供 Skill 名称与功能描述')
        try:
            ws = Workshop(str(BASE_DIR))
            result = ws.assemble(requirements)
            return self._json({
                'ok': True,
                'selected': result.get('selected', []),
                'skipped_conflicts': result.get('skipped_conflicts', []),
                'added_dependencies': result.get('added_dependencies', []),
                'notes': result.get('notes', ''),
            })
        except Exception as e:
            return self._error(str(e))

    def handle_skill_generate(self, payload):
        requirements = payload.get('requirements') or {}
        name = (requirements.get('name') or '').strip()
        description = (requirements.get('description') or '').strip()
        if not name or not description:
            return self._error('请提供 Skill 名称与功能描述')
        try:
            ws = Workshop(str(BASE_DIR))
            result = ws.assemble(requirements)
            selected = result.get('selected', [])
            content = self._generate_skill_content(requirements, selected)
            gid = re.sub(r'[^a-zA-Z0-9_\\-]+', '_', name).lower() or 'gen'
            gen = {
                'id': gid,
                'name': name,
                'description': description,
                'tags': requirements.get('tags', []),
                'created_at': datetime.now().isoformat(timespec='seconds'),
                'selected_part_ids': [p.get('id') for p in selected],
                'notes': result.get('notes', ''),
            }
            gdir = ws.record_generation(gen, content)
            return self._json({
                'ok': True,
                'id': gid,
                'path': str(Path(gdir) / 'SKILL.md'),
                'content': content,
            })
        except Exception as e:
            return self._error(str(e))

    def _generate_skill_content(self, requirements, selected_parts):
        llm = CONFIG.get('llm', {})
        base_url = (llm.get('base_url') or '').rstrip('/')
        api_key = llm.get('api_key') or ''
        name = requirements.get('name', '')
        description = requirements.get('description', '')
        parts_block = '\\n'.join(
            '- {0}：{1}'.format(p.get('name', p.get('id', '?')), p.get('description', ''))
            for p in selected_parts
        ) or '- （无匹配零件，基于描述生成）'
        if base_url and api_key:
            try:
                system = ('你是一个 WorkBuddy Skill 编写助手。请基于用户需求和下列已选用的零件，'
                          '生成一份完整、可直接安装到 ~/.workbuddy/skills/ 的 SKILL.md 文本。'
                          '要求：YAML frontmatter 含 name/description/tags/agent_created: true；'
                          '正文用 Markdown，含功能说明、用法、选用零件清单。'
                          '只输出 SKILL.md 文本本身，不要任何解释或代码围栏。')
                user_msg = ('# 需求\\n名称：{0}\\n描述：{1}\\n\\n# 已选用零件\\n{2}\\n\\n请生成 SKILL.md：'
                            .format(name, description, parts_block))
                import urllib.request as _ur
                req_data = json.dumps({
                    'model': llm.get('model', 'gpt-4o'),
                    'messages': [
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': user_msg},
                    ],
                }).encode('utf-8')
                req = _ur.Request(f'{base_url}/chat/completions', data=req_data, method='POST')
                req.add_header('Authorization', f'Bearer {api_key}')
                req.add_header('Content-Type', 'application/json')
                with _ur.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    return data['choices'][0]['message']['content']
            except Exception:
                pass
        return self._build_skill_markdown(requirements, selected_parts)

    def _build_skill_markdown(self, requirements, selected_parts):
        name = requirements.get('name', '未命名 Skill')
        description = requirements.get('description', '')
        tags = requirements.get('tags', [])
        parts_block = '\\n'.join(
            '- **{0}**：{1}'.format(p.get('name', p.get('id', '?')), p.get('description', ''))
            for p in selected_parts
        ) or '- （无匹配零件，基于描述生成）'
        return ('---\\n'
                'name: {0}\\n'
                'description: {1}\\n'
                'tags: {2}\\n'
                'agent_created: true\\n'
                '---\\n\\n'
                '# {0}\\n\\n'
                '{1}\\n\\n'
                '## 功能\\n'
                '{1}\\n\\n'
                '## 选用的零件\\n'
                '{3}\\n\\n'
                '## 用法\\n'
                '1. 在 WorkBuddy 中通过自然语言触发，或在对话框直接调用。\\n'
                '2. 按上方功能描述提供输入，Skill 返回处理结果。\\n'
                ).format(name, description, ', '.join(tags) if tags else 'auto-generated', parts_block)

    def handle_skill_install(self, payload):
        gid = (payload.get('id') or '').strip()
        if not gid:
            return self._error('缺少生成记录 id')
        gdir = BASE_DIR / 'generations' / gid
        skill_md = gdir / 'SKILL.md'
        if not skill_md.exists():
            return self._error('未找到生成记录：{0}'.format(gid))
        target_name = gid
        try:
            text = skill_md.read_text(encoding='utf-8')
            m = re.search(r'^name:\\s*(.+)$', text, re.MULTILINE)
            if m:
                target_name = re.sub(r'[^a-zA-Z0-9_\\-]+', '_', m.group(1).strip()).lower() or gid
        except Exception:
            pass
        dest = SKILLS_DIR / target_name
        if not safe_under(SKILLS_DIR, dest):
            return self._error('非法的目标路径')
        try:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(gdir, dest)
            return self._json({'ok': True, 'path': str(dest), 'name': target_name})
        except Exception as e:
            return self._error(str(e))

# ── 回收站 / 安全工具（模块级）──
CONVERSATIONS_DIR = WORKBUDDY_ROOT / "projects"


def send_to_recycle_bin(target: Path):
    """将文件或目录移入 Windows 回收站（非直接删除，可恢复）。"""
    target = target.resolve()
    pth = str(target).replace('"', '`"')
    if target.is_dir():
        ps = ('Add-Type -AssemblyName Microsoft.VisualBasic;'
              '[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory('
              '"{pth}",[Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,'
              '[Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)').format(pth=pth)
    else:
        ps = ('Add-Type -AssemblyName Microsoft.VisualBasic;'
              '[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('
              '"{pth}",[Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,'
              '[Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)').format(pth=pth)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                   check=True, capture_output=True, text=True)


def safe_under(base, target):
    """确保 target 严格位于 base 之内（防路径穿越，大小写不敏感）。"""
    base = os.path.normcase(str(base.resolve()))
    target = os.path.normcase(str(target.resolve()))
    return target == base or target.startswith(base + os.sep)


def compare_version(a, b):
    """比较两个语义化版本字符串，返回 -1/0/1。非规范版本按字符串比较。"""
    def norm(v):
        parts = re.split(r"[.-]", str(v or ""))
        nums = []
        for p in parts:
            m = re.match(r"^(\d+)(.*)$", p)
            if m:
                nums.append((int(m.group(1)), m.group(2) or ""))
            else:
                nums.append((-1, p))
        return nums
    na, nb = norm(a), norm(b)
    for (va, sa), (vb, sb) in zip(na, nb):
        if va != vb:
            return -1 if va < vb else 1
        if sa != sb:
            return -1 if sa < sb else 1
    if len(na) != len(nb):
        return -1 if len(na) < len(nb) else 1
    return 0


def fetch_skillhub_skill(base_url, slug, api_key=""):
    """从 SkillHub 查询 skill 详情（最新版本等）。"""
    url = f"{base_url}/api/v1/skills/{slug}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "WorkBuddyConsole/1.0")
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def strip_wrapped(text):
    """去掉对话文本里被系统标签包裹的上下文（system-reminder / user_info / identity_context）。"""
    text = re.sub(r"<system-reminder[\s\S]*?system-reminder>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<user_info[\s\S]*?user_info>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<identity_context[\s\S]*?identity_context>", "", text, flags=re.IGNORECASE)
    return text.strip()


def extract_session_title(f: Path, limit=50):
    """取会话首条用户消息作为标题。"""
    try:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") == "message" and obj.get("role") == "user":
                c = obj.get("content")
                if isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and part.get("type") == "input_text":
                            t = strip_wrapped(part.get("text", ""))
                            if t:
                                return t[:limit]
    except Exception:
        pass
    return f.stem


def _fmt_time(ts):
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def extract_conversation_text(path: Path, limit=12000):
    """从 jsonl 会话文件提取可读对话文本（user/assistant 消息 + 简短思考）。"""
    parts = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            t = obj.get("type")
            if t == "message":
                role = obj.get("role")
                c = obj.get("content")
                if isinstance(c, list):
                    for part in c:
                        if not isinstance(part, dict):
                            continue
                        if part.get("type") == "input_text" and role == "user":
                            txt = strip_wrapped(part.get("text", ""))
                            if txt:
                                parts.append("用户: " + txt)
                        elif part.get("type") == "output_text" and role == "assistant":
                            txt = part.get("text", "")
                            if txt.strip():
                                parts.append("助手: " + txt)
            elif t == "reasoning":
                rc = obj.get("rawContent") or obj.get("content")
                if isinstance(rc, list):
                    for part in rc:
                        if isinstance(part, dict) and part.get("type") == "reasoning_text":
                            txt = part.get("text", "")
                            if txt.strip():
                                parts.append("[思考] " + txt[:400])
    except Exception:
        pass
    joined = "\n".join(parts)
    if len(joined) > limit:
        joined = joined[:limit] + "\n…(已截断)"
    return joined


def summarize_text(text, llm):
    """用 LLM 生成对话结构化摘要；未配置或失败时回退到本地规则摘要。"""
    if text.strip():
        base_url = (llm.get("base_url") or "").rstrip("/")
        api_key = llm.get("api_key") or ""
        model = llm.get("model") or "gpt-4o"
        if base_url and api_key:
            try:
                import urllib.request
                sys_p = ("你是一个对话记录整理助手。请阅读下面的对话记录，提炼成结构化中文摘要，"
                         "包含：1) 主题；2) 用户的目标/需求；3) 关键决策与产出；4) 涉及的文件/命令；"
                         "5) 待办/遗留事项。若信息不足则写“无”。简洁，不超过 400 字。")
                body = json.dumps({"model": model,
                                   "messages": [{"role": "system", "content": sys_p},
                                                {"role": "user", "content": text}]}).encode("utf-8")
                req = urllib.request.Request(f"{base_url}/chat/completions", data=body, method="POST")
                req.add_header("Authorization", f"Bearer {api_key}")
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"]
                    return content.strip(), True
            except Exception:
                pass
    lines = [l for l in text.splitlines() if l.strip()][:30]
    return "（未使用 AI，本地规则提取）\n" + "\n".join(lines), False


def run(port=8080):
    print(f"WorkBuddy Console Server: http://0.0.0.0:{port}")
    HTTPServer(("0.0.0.0", port), APIHandler).serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run(port)
