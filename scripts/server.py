#!/usr/bin/env python3
"""WorkBuddy 控制台后端服务
提供静态文件、对话检索、安全清理、Skill 对话等 API。
"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workshop import Workshop

# ── 日志 ──
LOG_DIR = Path.home() / ".workbuddy" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "agent-grocery-workshop.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("agent-grocery-workshop")
from dismantle import parse_skill_to_candidates
from scan_console import scan_workshop as scan_workshop_live
import scan_console

# ── 配置 ──
def detect_workbuddy_home():
    """探测 WorkBuddy 主目录。

    优先级：
    1. 环境变量 WORKBUDDY_HOME
    2. WSL 下探测挂载的 Windows 用户目录 /mnt/c/Users/<user>/.workbuddy
    3. 当前用户 home 下的 ~/.workbuddy
    """
    env = os.environ.get('WORKBUDDY_HOME')
    if env:
        return env
    win_users = '/mnt/c/Users'
    if os.path.isdir(win_users):
        for name in sorted(os.listdir(win_users)):
            if name in ('Public', 'Default', 'All Users', 'Default User'):
                continue
            cand = os.path.join(win_users, name, '.workbuddy')
            if os.path.isdir(cand):
                return cand
    return os.path.expanduser("~/.workbuddy")


WORKBUDDY_ROOT = Path(detect_workbuddy_home())
SKILLS_DIR = WORKBUDDY_ROOT / "skills"
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "console_config.json"
BACKUP_DIR = WORKBUDDY_ROOT / "console-backups"

# 异步 Skill 生成任务（内存态，重启后丢失；产物已落盘）
_generation_jobs = {}
_generation_jobs_lock = threading.Lock()

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
        "github": {"token": ""},
    }


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


CONFIG = load_config()


def _win_user_path(subpath):
    """返回 Windows 用户目录下的工具路径，兼容 server 跑在 Windows 原生与 WSL 两种环境，且不硬编码用户名。

    - Windows 原生（os.name=='nt'）：直接用当前用户 home（C:\\Users\\<用户>）。
    - WSL：CLI/gh 通常装在 Windows 侧，探测 /mnt/c/Users/* 找到实际用户目录。
    - 兜底：当前用户 home（纯 Linux 场景）。
    """
    if os.name == 'nt':
        return os.path.expanduser(os.path.join('~', subpath))
    base = '/mnt/c/Users'
    if os.path.isdir(base):
        for name in os.listdir(base):
            cand = os.path.join(base, name, *subpath.split('/'))
            if os.path.exists(cand):
                return cand
    return os.path.expanduser(os.path.join('~', subpath))


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # 记录到文件日志，便于排查「错误日志看不到」问题
        logger.info(self.address_string() + " " + fmt % args)

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
        if path == "/console_data.json":
            path = "/scripts/console_data.json"
        if path == "/api/config":
            return self._json({"ok": True, "config": {"llm": CONFIG.get("llm", {}), "skillhub": CONFIG.get("skillhub", {}), "github": CONFIG.get("github", {})}})
        if path == "/api/workshop":
            return self.handle_workshop_data({})
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
        if path == "/api/skill/generate-plan":
            return self.handle_skill_generate_plan(payload)
        if path == "/api/skill/generate":
            return self.handle_skill_generate(payload)
        if path == "/api/skill/generate-status":
            return self.handle_skill_generate_status(payload)
        if path == "/api/skill/generations":
            return self.handle_skill_generations(payload)
        if path == "/api/workshop":
            return self.handle_workshop_data(payload)
        if path == "/api/skill/install":
            return self.handle_skill_install(payload)
        if path == "/api/skill/dismantle":
            return self.handle_skill_dismantle(payload)
        if path == "/api/skill/git":
            return self.handle_skill_git(payload)
        if path == "/api/skill/publish":
            return self.handle_skill_publish(payload)
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
            req_data = json.dumps({"model": model, "messages": ([{"role": "system", "content": system}] if system else []) + messages}).encode("utf-8")
            req = urllib.request.Request(f"{base_url}/chat/completions", data=req_data, method="POST")
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                return self._json({"ok": True, "content": content})
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")[:500]
            except Exception:
                pass
            logger.error(f"/api/chat HTTP {e.code} for model={model}, skill={skill_id}: {body}\n{traceback.format_exc()}")
            return self._error(f"LLM 请求失败 HTTP {e.code}：{e.reason}。响应：{body or '(无响应体)'}", e.code)
        except Exception as e:
            logger.error(f"/api/chat 异常 model={model}, skill={skill_id}: {e}\n{traceback.format_exc()}")
            return self._error(str(e))

    def handle_config(self, payload):
        global CONFIG
        CONFIG["llm"] = payload.get("llm", CONFIG.get("llm", {}))
        if "skillhub" in payload:
            CONFIG["skillhub"] = {**CONFIG.get("skillhub", {}), **payload.get("skillhub", {})}
        if "github" in payload:
            CONFIG["github"] = {**CONFIG.get("github", {}), **payload.get("github", {})}
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
        if not safe_under(SKILLS_DIR, fp):
            return self._error(f"非法的 Skill 路径: {skill_id}")
        # 若目录已不存在，视为已卸载，让前端同步移除列表项（解决「删除后仍展示」问题）
        if not fp.exists():
            logger.warning(f"Skill 目录已不存在，按已卸载处理: {fp}")
            return self._json({
                "ok": True,
                "already_removed": True,
                "backup": "",
                "note": f"Skill {skill_id} 目录已不存在，已从前端列表同步移除。",
            })
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"skill_{skill_id}_{ts}"
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copytree(fp, backup)
        except Exception as e:
            logger.error(f"Skill 备份失败 {skill_id}: {e}\n{traceback.format_exc()}")
            return self._error(f"备份失败（已取消删除）: {e}")
        try:
            send_to_recycle_bin(fp)
        except Exception as e:
            logger.error(f"Skill 放入回收站失败 {skill_id}: {e}\n{traceback.format_exc()}")
            return self._error(f"放入回收站失败: {e}（备份已生成于 {backup}）")
        logger.info(f"Skill 已卸载: {skill_id} -> 回收站 (备份 {backup})")
        # 删除成功后立即重新生成 console_data.json 快照，避免刷新页面仍看到已删除 skill
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                scan_console.main(['--quick'])
            logger.info(f"console_data.json 已重新生成（快速模式）:\n{buf.getvalue()[:500]}")
        except Exception as e:
            logger.error(f"删除后重新生成 console_data.json 失败: {e}\n{traceback.format_exc()}")
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
        job_id = 'gen_' + uuid.uuid4().hex[:12]
        with _generation_jobs_lock:
            _generation_jobs[job_id] = {
                'id': job_id,
                'status': 'pending',
                'progress': ['已加入生成队列'],
                'created_at': datetime.now().isoformat(timespec='seconds'),
                'requirements': requirements,
                'result': None,
                'error': None,
            }
        threading.Thread(
            target=self._run_generation_job,
            args=(job_id, requirements),
            daemon=True,
        ).start()
        return self._json({'ok': True, 'job_id': job_id})

    def _run_generation_job(self, job_id, requirements):
        def update(**kwargs):
            with _generation_jobs_lock:
                _generation_jobs[job_id].update(kwargs)

        def push(msg):
            with _generation_jobs_lock:
                _generation_jobs[job_id].setdefault('progress', []).append(msg)

        try:
            update(status='running')
            ws = Workshop(str(BASE_DIR))
            push('开始检索零件库…')
            result = ws.assemble(requirements)
            selected = result.get('selected', [])
            candidates = result.get('candidates', [])
            skipped = result.get('skipped_conflicts', [])
            notes = result.get('notes', '')
            push('共扫描到 {0} 个候选零件，冲突跳过 {1} 个'.format(len(candidates), len(skipped)))
            if selected:
                push('最终确定选用 {0} 个零件：'.format(len(selected)))
                for p in selected:
                    reason = self._part_selection_reason(p, requirements)
                    push('  · {0}（{1}）—— {2}'.format(
                        p.get('name', p.get('id', '?')),
                        p.get('type', '未分类'),
                        reason,
                    ))
            else:
                push('未匹配到现成零件，将基于需求描述直接生成模板。')
            if notes:
                push('组装备注：' + notes)
            push('正在生成 SKILL.md 正文…')
            content = self._generate_skill_content(requirements, selected)
            name = requirements.get('name', '未命名 Skill')
            gid = re.sub(r'[\s/\:*?"<>|]+', '_', name).lower() or 'gen'
            # 先生成目录路径，避免在 manifest 中引用未赋值的 gdir
            gdir = str(BASE_DIR / 'generations' / gid)
            selected_parts = [
                {
                    'id': p.get('id'),
                    'name': p.get('name', p.get('id')),
                    'type': p.get('type', '未分类'),
                    'description': p.get('description', ''),
                    'reason': self._part_selection_reason(p, requirements),
                }
                for p in selected
            ]
            gen = {
                'id': gid,
                'name': name,
                'description': requirements.get('description', ''),
                'tags': requirements.get('tags', []),
                'created_at': datetime.now().isoformat(timespec='seconds'),
                'selected_part_ids': [p.get('id') for p in selected],
                'used_part_ids': [p.get('id') for p in selected],
                'selected_parts': selected_parts,
                'candidates_count': len(candidates),
                'skipped_count': len(skipped),
                'notes': notes,
                'progress': list(_generation_jobs[job_id].get('progress', [])),
                'path': str(Path(gdir) / 'SKILL.md'),
                'status': 'done',
                'auto_dismantled': False,
            }
            gdir = ws.record_generation(gen, content)
            # 生成完成后默认直接安装到 WorkBuddy（需求4：生成的 skill 默认直接安装）
            _inst_ok = False
            _inst_err = ''
            try:
                _gd = BASE_DIR / 'generations' / gid / 'SKILL.md'
                _tname = gid
                if _gd.exists():
                    try:
                        _gt = _gd.read_text(encoding='utf-8')
                        for _line in _gt.splitlines():
                            if _line.lower().startswith('name:'):
                                _tname = _line.split(':', 1)[1].strip() or gid
                                break
                    except Exception:
                        pass
                _bad = set(' /:*?<>|')
                _bad.add(chr(34))
                _bad.add(chr(92))
                _tname = ''.join('_' if c in _bad else c for c in _tname.lower()) or gid
                _dest = SKILLS_DIR / _tname
                if safe_under(SKILLS_DIR, _dest):
                    if _dest.exists():
                        shutil.rmtree(_dest)
                    shutil.copytree(BASE_DIR / 'generations' / gid, _dest)
                    _inst_ok = True
            except Exception as _e:
                _inst_err = str(_e)
                logger.error(f"Skill 自动安装失败 {gid}: {_inst_err}")
            gen['installed'] = _inst_ok
            # 回写 installed 状态到 manifest.json，供前端「已安装」状态展示与刷新后保留
            try:
                _mp = BASE_DIR / 'generations' / gid / 'manifest.json'
                _obj = json.loads(_mp.read_text(encoding='utf-8')) if _mp.exists() else {}
                _obj['installed'] = gen['installed']
                _mp.write_text(json.dumps(_obj, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass
            if _inst_ok:
                push('已自动安装到 WorkBuddy（~/.workbuddy/skills）。')
            else:
                push('自动安装失败：' + (_inst_err or '未知错误') + '（可在列表点击「重新安装」）。')
            update(
                status='done',
                progress=['生成完成：' + str(Path(gdir) / 'SKILL.md')],
                result={
                    'id': gid,
                    'path': str(Path(gdir) / 'SKILL.md'),
                    'content': content,
                    'generation': gen,
                    'selected_parts': selected_parts,
                    'candidates_count': len(candidates),
                    'skipped_count': len(skipped),
                },
            )
        except Exception as e:
            logger.error(f"Skill 生成任务 {job_id} 失败: {e}\n{traceback.format_exc()}")
            update(status='error', error=str(e), progress=['生成失败：' + str(e)])

    def handle_skill_generate_status(self, payload):
        job_id = (payload.get('job_id') or '').strip()
        if not job_id:
            return self._error('缺少 job_id')
        with _generation_jobs_lock:
            job = _generation_jobs.get(job_id)
        if not job:
            return self._error('未找到生成任务：' + job_id)
        return self._json({
            'ok': True,
            'job': {
                'id': job['id'],
                'status': job['status'],
                'progress': job['progress'],
                'created_at': job['created_at'],
                'result': job['result'],
                'error': job['error'],
            },
        })

    def handle_skill_generations(self, payload):
        """返回磁盘上所有已落盘的生成记录。

        前端进入「Skill开发」tab 或刷新页面时调用，保证除内存快照（EMBEDDED_DATA /
        console_data.json）之外，也能从 generations/ 目录读取真实历史记录，避免刷新后
        新生成的 Skill 记录「消失」。
        """
        try:
            ws = Workshop(str(BASE_DIR))
            gens = ws.load_generations()
        except Exception as e:
            return self._error('读取生成记录失败：' + str(e))
        return self._json({'ok': True, 'generations': gens})

    @staticmethod
    def _part_selection_reason(part, requirements):
        """给出为什么选中这个零件的简短理由。"""
        desc = (part.get('description') or '').strip()
        ptags = set((part.get('tags') or []))
        rtags = set((requirements.get('tags') or []))
        matched_tags = ptags & rtags
        if matched_tags:
            return '标签匹配「{0}」{1}'.format(
                '」「'.join(sorted(matched_tags)),
                '：' + desc if desc else '',
            )
        if desc:
            return '功能匹配：' + desc
        return '与需求语义相关'

    def _generate_skill_content(self, requirements, selected_parts):
        llm = CONFIG.get('llm', {})
        base_url = (llm.get('base_url') or '').rstrip('/')
        api_key = llm.get('api_key') or ''
        name = requirements.get('name', '')
        description = requirements.get('description', '')
        parts_block = '\n'.join(
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
                user_msg = ('# 需求\n名称：{0}\n描述：{1}\n\n# 已选用零件\n{2}\n\n请生成 SKILL.md：'
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
        parts_block = '\n'.join(
            '- **{0}**：{1}'.format(p.get('name', p.get('id', '?')), p.get('description', ''))
            for p in selected_parts
        ) or '- （无匹配零件，基于描述生成）'
        return ('---\n'
                'name: {0}\n'
                'description: {1}\n'
                'tags: {2}\n'
                'agent_created: true\n'
                '---\n\n'
                '# {0}\n\n'
                '{1}\n\n'
                '## 功能\n'
                '{1}\n\n'
                '## 选用的零件\n'
                '{3}\n\n'
                '## 用法\n'
                '1. 在 WorkBuddy 中通过自然语言触发，或在对话框直接调用。\n'
                '2. 按上方功能描述提供输入，Skill 返回处理结果。\n'
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
                target_name = re.sub(r'[\\s/\\\\:*?"<>|]+', '_', m.group(1).strip()).lower() or gid
        except Exception:
            pass
        dest = SKILLS_DIR / target_name
        if not safe_under(SKILLS_DIR, dest):
            return self._error('非法的目标路径')
        try:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(gdir, dest)
            # 写回 installed 状态到 manifest.json（需求4：安装结果持久化，刷新后仍显示「已安装」）
            try:
                _mp = gdir / 'manifest.json'
                _obj = json.loads(_mp.read_text(encoding='utf-8')) if _mp.exists() else {}
                _obj['installed'] = True
                _mp.write_text(json.dumps(_obj, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass
            return self._json({'ok': True, 'path': str(dest), 'name': target_name})
        except Exception as e:
            # 安装失败也写回 installed=false，便于前端显示「安装失败 / 重新安装」
            try:
                _mp = gdir / 'manifest.json'
                _obj = json.loads(_mp.read_text(encoding='utf-8')) if _mp.exists() else {}
                _obj['installed'] = False
                _mp.write_text(json.dumps(_obj, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass
            return self._error(str(e))

    def handle_skill_dismantle(self, payload):
        """对 generations/<id>/SKILL.md 执行拆解：识别候选零件、写回 library/（需求1）、记录 manifest。"""
        gid = (payload.get('id') or '').strip()
        if not gid:
            return self._error('缺少生成记录 id')
        gdir = BASE_DIR / 'generations' / gid
        skill_md = gdir / 'SKILL.md'
        manifest = gdir / 'manifest.json'
        if not skill_md.exists():
            return self._error('未找到生成记录：{0}'.format(gid))
        try:
            ws = Workshop(str(BASE_DIR))
            candidates = parse_skill_to_candidates(str(skill_md))
            # 将候选零件写回零件库 library/，使其在「组件管理」货架中实时可见（需求1）
            saved_parts = []
            for i, c in enumerate(candidates):
                pid = 'part_dm_{0}_{1:03d}'.format(gid, i)
                part = {
                    'id': pid,
                    'name': c.get('name') or '候选零件 {0}'.format(i + 1),
                    'category': c.get('category') or '参考文档',
                    'sub_category': c.get('sub_category') or gid,
                    'type': c.get('type') or '流程规范',
                    'description': c.get('description') or '',
                    'content': c.get('content') or '',
                    'content_format': c.get('content_format') or 'markdown',
                    'source_type': 'dismantled',
                    'source_skill_name': c.get('source_skill_name') or gid,
                    'metadata': dict(c.get('metadata') or {}),
                    'version': 'v1.0',
                    'depends_on': [],
                    'conflicts_with': [],
                }
                try:
                    ws.add_part(part)
                    saved_parts.append(pid)
                except Exception:
                    pass
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            manifest_obj = {}
            if manifest.exists():
                try:
                    manifest_obj = json.loads(manifest.read_text(encoding='utf-8'))
                except Exception:
                    manifest_obj = {}
            manifest_obj['auto_dismantled'] = True
            manifest_obj['dismantled_at'] = now
            manifest_obj['dismantle_candidates'] = candidates
            manifest_obj['dismantle_saved_part_ids'] = saved_parts
            manifest.write_text(json.dumps(manifest_obj, ensure_ascii=False, indent=2), encoding='utf-8')
            return self._json({
                'ok': True, 'id': gid, 'candidates': candidates,
                'count': len(candidates), 'saved_parts': saved_parts,
            })
        except Exception as e:
            return self._error('拆解失败：{0}'.format(e))

    # ── Skill 发布链路：Git 同步 + SkillHub 发布 ──
    @staticmethod
    def _slugify(name):
        s = (name or '').strip().lower()
        s = re.sub(r'[^a-z0-9]+', '-', s)
        s = re.sub(r'-+', '-', s).strip('-')
        return s or 'skill'

    def _derive_slug(self, name):
        """派生 GitHub 仓库名 / SkillHub slug 用的健壮 slug。

        与 _slugify 不同：当 name 无 ASCII（如纯中文名）时不会回退成固定的 'skill'，
        而是生成 skill-<随机hex>，保证每个 Skill 全局唯一、避免仓库名/slug 冲突碰撞。
        """
        base = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')
        return base if len(base) >= 2 else ('skill-' + uuid.uuid4().hex[:8])

    @staticmethod
    def _extract_frontmatter(text):
        fm = {}
        m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
        if not m:
            return fm
        for line in m.group(1).splitlines():
            if ':' in line:
                k, v = line.split(':', 1)
                fm[k.strip()] = v.strip()
        return fm

    def _set_frontmatter_field(self, skill_md, field, value):
        text = skill_md.read_text(encoding='utf-8')
        lines = text.split('\n')
        fm_end = None
        if lines and lines[0].strip() == '---':
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    fm_end = i
                    break
        if fm_end is None:
            return
        idx = None
        for i in range(1, fm_end):
            if lines[i].split(':', 1)[0].strip() == field:
                idx = i
                break
        new_line = '{0}: {1}'.format(field, value)
        if idx is not None:
            lines[idx] = new_line
        else:
            lines.insert(fm_end, new_line)
        skill_md.write_text('\n'.join(lines), encoding='utf-8')

    def _find_gh(self):
        candidates = [
            _win_user_path('.workbuddy/binaries/gh/bin/gh.exe'),
            "gh",
        ]
        for c in candidates:
            p = self._to_native_exe(c)
            if shutil.which(p) or Path(p).exists():
                return p
        return "gh"

    @staticmethod
    def _to_native_exe(p):
        # WSL 下把 Windows 风格 exe 路径（C:/... 或 C:\...）转 /mnt/c/...
        if os.name != 'nt' and len(p) >= 2 and p[0].isalpha() and p[1] == ':':
            drive = p[0].lower()
            rest = p[2:].replace(chr(92), '/')
            return '/mnt/' + drive + rest
        return p

    def _gh_whoami(self, env):
        try:
            proc = subprocess.run([self._find_gh(), 'api', 'user', '--jq', '.login'],
                                   capture_output=True, text=True, timeout=30, env=env)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except Exception:
            pass
        return 'Dillon-Xue'

    def _run_cmd(self, cmd, cwd, env=None):
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                              timeout=120, env=full_env)
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or '命令失败').strip()
            raise RuntimeError(msg[-500:])
        return proc.stdout.strip()

    def handle_skill_git(self, payload):
        """自动建 GitHub 仓库并同步生成的 Skill 代码（git init + commit + push + 写回 homepage）。"""
        gid = (payload.get('id') or '').strip()
        if not gid:
            return self._error('缺少生成记录 id')
        gdir = BASE_DIR / 'generations' / gid
        skill_md = gdir / 'SKILL.md'
        if not skill_md.exists():
            return self._error('未找到生成记录：{0}'.format(gid))
        text = skill_md.read_text(encoding='utf-8')
        fm = self._extract_frontmatter(text)
        name = fm.get('name') or gid
        # 仓库名(slug)必须唯一合法：优先用已配置 slug；否则中文名经 _slugify 会落到 'skill' 造成碰撞，
        # 改用 _derive_slug（中文名回退 skill-<hex> 保证唯一），并写回 frontmatter 与发布的 slug 保持一致。
        raw_slug = (payload.get('slug') or (fm.get('slug') or '').strip() or '').strip()
        if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', raw_slug):
            raw_slug = self._derive_slug(name)
        slug = raw_slug
        self._set_frontmatter_field(skill_md, 'slug', slug)
        token = (CONFIG.get('github') or {}).get('token') or ''
        if not token:
            return self._error('请先在「设置 → GitHub 发布」配置 GitHub Token 后再提交 Git（未配置无法同步到 Git）')
        env = dict(os.environ)
        if token:
            env['GH_TOKEN'] = token
        gh = self._find_gh()
        owner = self._gh_whoami(env)
        repo_url = 'https://github.com/{0}/{1}.git'.format(owner, slug)
        if payload.get('dry_run'):
            return self._json({'ok': True, 'dry_run': True, 'slug': slug, 'owner': owner,
                               'repo_url': repo_url,
                               'steps': ['(dry-run) 将创建并推送 GitHub 仓库 {0}/{1}'.format(owner, slug)]})
        steps = []
        try:
            try:
                self._run_cmd([gh, 'repo', 'create', slug, '--public',
                               '--description', (fm.get('description') or name)[:200],
                               '--confirm'], cwd=gdir, env=env)
                steps.append('已创建 GitHub 仓库 {0}/{1}'.format(owner, slug))
            except Exception as e:
                steps.append('创建仓库跳过：{0}（可能已存在）'.format(str(e)[:120]))
            if not (gdir / '.git').exists():
                self._run_cmd(['git', 'init'], cwd=gdir)
            self._run_cmd(['git', 'add', '-A'], cwd=gdir)
            try:
                self._run_cmd(['git', 'commit', '-m', 'init: {0}'.format(name)], cwd=gdir)
            except Exception:
                steps.append('无新改动需提交')
            try:
                self._run_cmd(['git', 'remote', 'get-url', 'origin'], cwd=gdir)
            except Exception:
                self._run_cmd(['git', 'remote', 'add', 'origin', repo_url], cwd=gdir)
            push_url = repo_url
            if token:
                push_url = 'https://x-access-token:{0}@github.com/{1}/{2}.git'.format(token, owner, slug)
            self._run_cmd(['git', 'remote', 'set-url', 'origin', push_url], cwd=gdir)
            try:
                self._run_cmd(['git', 'push', '-u', 'origin', 'HEAD'], cwd=gdir)
            finally:
                self._run_cmd(['git', 'remote', 'set-url', 'origin', repo_url], cwd=gdir)
            steps.append('已推送至 {0}'.format(repo_url))
            # 写回 homepage 并补提交
            homepage = 'https://github.com/{0}/{1}'.format(owner, slug)
            try:
                self._set_frontmatter_field(skill_md, 'homepage', homepage)
                self._run_cmd(['git', 'add', '-A'], cwd=gdir)
                self._run_cmd(['git', 'commit', '-m', 'chore: 补充 homepage'], cwd=gdir)
                self._run_cmd(['git', 'remote', 'set-url', 'origin', push_url], cwd=gdir)
                try:
                    self._run_cmd(['git', 'push', 'origin', 'HEAD'], cwd=gdir)
                finally:
                    self._run_cmd(['git', 'remote', 'set-url', 'origin', repo_url], cwd=gdir)
            except Exception:
                pass
            return self._json({'ok': True, 'slug': slug, 'owner': owner,
                               'repo_url': repo_url, 'homepage': homepage, 'steps': steps})
        except Exception as e:
            return self._error('Git 同步失败：{0}'.format(e))

    def handle_skill_publish(self, payload):
        """调用 SkillHub CLI 发布生成的 Skill（自动补齐 frontmatter / 读取本地凭据）。"""
        gid = (payload.get('id') or '').strip()
        if not gid:
            return self._error('缺少生成记录 id')
        gdir = BASE_DIR / 'generations' / gid
        skill_md = gdir / 'SKILL.md'
        if not skill_md.exists():
            return self._error('未找到生成记录：{0}'.format(gid))
        # 发布前自动补齐 SkillHub 必需的 frontmatter 字段（slug/displayName/version），
        # 否则生成的 SKILL.md 缺字段会令 CLI 校验失败。
        try:
            self._ensure_publish_frontmatter(skill_md)
        except Exception as e:
            return self._error('规范化 SKILL.md 失败：{0}'.format(e))
        cfg = CONFIG.get('skillhub') or {}
        cli = payload.get('cli_path') or cfg.get('cli_path') or _win_user_path('.skillhub/skills_store_cli.py')
        cli = self._to_native_exe(cli)
        token = (payload.get('token')
                 or (CONFIG.get('skillhub') or {}).get('api_key')
                 or '')
        if not token:
            return self._error('请先在「设置 → SkillHub」配置 API Key 后再发布（未配置 SkillHub 无法发布）')
        version = payload.get('version') or '1.0.0'
        changelog = payload.get('changelog') or '首次发布'
        dry = bool(payload.get('dry_run', False))
        cmd = [sys.executable, cli, 'publish', str(gdir),
               '--token', token, '--version', version, '--changelog', changelog]
        if dry:
            cmd.append('--dry-run')
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            out = (proc.stdout or '') + (proc.stderr or '')
            if proc.returncode != 0:
                return self._error('发布失败：' + out.strip()[-800:])
            verify = ''
            try:
                slug = self._extract_frontmatter(skill_md.read_text(encoding='utf-8')).get('slug') or self._slugify(gid)
                vp = subprocess.run([sys.executable, cli, 'search', slug],
                                    capture_output=True, text=True, timeout=60)
                verify = (vp.stdout or vp.stderr or '').strip()[-400:]
            except Exception:
                pass
            return self._json({'ok': True, 'output': out.strip()[-1500:], 'verify': verify})
        except subprocess.TimeoutExpired:
            return self._error('发布超时', 504)
        except Exception as e:
            return self._error('发布异常：{0}'.format(e))


    def _ensure_publish_frontmatter(self, skill_md):
        """发布前规范化 SKILL.md frontmatter，补齐 SkillHub CLI 必需的 slug/displayName/version。

        无论 SKILL.md 是默认模板还是 LLM 生成（格式可能不标准），都重写为规范形式，
        保留原有其它字段（如 homepage/license），确保 CLI 的 _validate_metadata 通过。
        """
        nl = chr(10)
        text = skill_md.read_text(encoding='utf-8')
        fm = self._extract_frontmatter(text)
        name = (fm.get('name') or '').strip() or skill_md.parent.name
        slug = (fm.get('slug') or '').strip()
        # slug 必须是 kebab-case 且长度>=2；缺失时用 name 派生（中文 name 无 ASCII 会清空，
        # 回退为 skill-<随机hex>，保证全局唯一、合法，避免 SkillHub slug 冲突导致发布失败）。
        if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', slug or ''):
            base = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')
            slug = base if len(base) >= 2 else ('skill-' + uuid.uuid4().hex[:8])
        display = (fm.get('displayName') or '').strip() or name
        version = (fm.get('version') or '').strip() or '1.0.0'
        merged = dict(fm)
        merged['name'] = name
        merged['slug'] = slug
        merged['displayName'] = display
        merged['version'] = version
        merged['description'] = (fm.get('description') or '').strip()
        merged['tags'] = fm.get('tags') or ''
        merged['agent_created'] = True
        order = ['name', 'slug', 'displayName', 'version', 'description', 'tags', 'agent_created']
        lines = ['---']
        for k in order:
            lines.append(k + ': ' + str(merged.get(k, '')))
        for k, v in merged.items():
            if k not in order:
                lines.append(k + ': ' + str(v))
        lines.append('---')
        new_fm = nl.join(lines) + nl
        body = text
        if text.startswith('---'):
            end = text.find(nl + '---', 3)
            if end != -1:
                nxt = text.find(nl, end + 4)
                body = text[nxt + 1:] if nxt != -1 else ''
        skill_md.write_text(new_fm + body, encoding='utf-8')
        return slug

    def handle_workshop_data(self, payload):
        """实时返回零件工坊数据（零件库 + 生成/拆解记录 + 实时引用次数）。

        前端「组件管理 / 概览」优先调用此接口，保证引用次数、拆解入库产物实时刷新（需求1、需求6）。
        """
        try:
            data = scan_workshop_live()
            return self._json({'ok': True, 'workshop': data})
        except Exception as e:
            return self._error('读取工坊数据失败：' + str(e))

# ── 回收站 / 安全工具（模块级）──
CONVERSATIONS_DIR = WORKBUDDY_ROOT / "projects"


def send_to_recycle_bin(target: Path):
    """将文件或目录移入系统回收站（非直接删除，可恢复）。

    兼容 Windows（PowerShell）与 Linux/WSL（gio trash / trash-put）。
    """
    target = target.resolve()
    if sys.platform == "win32":
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
        return

    # Linux / WSL：优先 gio trash，其次 trash-put
    for cmd in (["gio", "trash"], ["trash-put"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd + [str(target)], check=True, capture_output=True, text=True)
                return
            except Exception:
                pass

    # 兜底：移动到 ~/.workbuddy/console-backups/.trash_fallback/
    fallback = BACKUP_DIR / ".trash_fallback"
    fallback.mkdir(parents=True, exist_ok=True)
    dest = fallback / (target.name + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.move(str(target), str(dest))


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
    # 启动时用快速模式生成/刷新 console_data.json 快照，避免 100+ skill 跨 WSL 全量扫描阻塞启动。
    # 完整扫描（token/安全）后续可通过 /api/refresh 或手动运行 scan_console.py 触发。
    try:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            scan_console.main(['--quick'])
        logger.info(f"启动时已刷新 console_data.json（快速模式）:\n{buf.getvalue()[:500]}")
    except Exception as e:
        logger.error(f"启动时刷新 console_data.json 失败: {e}\n{traceback.format_exc()}")
    print(f"WorkBuddy Console Server: http://0.0.0.0:{port}")
    HTTPServer(("0.0.0.0", port), APIHandler).serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run(port)
