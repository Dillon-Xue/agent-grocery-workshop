#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""server.py - 零件杂货铺 agent 管控台 本地后端 daemon（仅标准库）。

职责：
  1) 提供静态管控台页面（从 skill 目录读取 shop.html 返回；未生成则现场生成）
  2) GET  /api/data              实时聚合 agent 真实数据（build_data）
  3) POST /api/skill/uninstall   卸载 skill（安全移入 _trash，可恢复）
  4) POST /api/space/scan        扫描可清理的本地空间
  5) POST /api/space/clean       执行清理（_trash + 过期日志）
  6) POST /api/backup            备份对话与 skill 配置为 zip
  7) POST /api/conversation/compress  压缩某对话（先备份原文件）
  8) POST /api/chat              代理 LLM 对话（用 skill 的 SKILL.md 作系统上下文）
  9) GET  /api/open-in-wb        返回 workbuddy:// 深链接（实验性）

配置：skill 目录下 config.json（不提交）
  { "wb_root": "...", "git": {"owner":"Dillon-Xue","repo":"agent-grocery-workshop"},
    "llm": {"base_url":"https://api.openai.com/v1","api_key":"","model":"gpt-4o"} }
"""
import os
import sys
import json
import io
import shutil
import datetime
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import build_data  # noqa

CONFIG_PATH = os.path.join(HERE, "config.json")
DEFAULT_PORT = 18790


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            return json.load(open(CONFIG_PATH, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def wb_root(cfg):
    return cfg.get("wb_root") or build_data.detect_wb_root()


def trash_dir(wb):
    d = os.path.join(wb, "_trash")
    os.makedirs(d, exist_ok=True)
    return d


def backup_dir(wb):
    d = os.path.join(wb, "_backup")
    os.makedirs(d, exist_ok=True)
    return d


# ---------- 业务动作 ----------

def uninstall_skill(cfg, skill_id, location):
    wb = wb_root(cfg)
    if location == "project":
        base = os.path.join(os.getcwd(), ".workbuddy", "skills", skill_id)
    else:
        base = os.path.join(wb, "skills", skill_id)
    if not os.path.isdir(base):
        return {"ok": False, "error": "skill 目录不存在: " + base}
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(trash_dir(wb), skill_id + "_" + ts)
    shutil.move(base, dest)
    return {"ok": True, "moved_to": dest}


def scan_space(cfg):
    wb = wb_root(cfg)
    items = []
    # 1. _trash
    td = trash_dir(wb)
    t_size = sum(os.path.getsize(os.path.join(td, f)) for f in os.listdir(td)
                 if os.path.isfile(os.path.join(td, f))) if os.path.isdir(td) else 0
    t_dirs = len([f for f in os.listdir(td) if os.path.isdir(os.path.join(td, f))]) if os.path.isdir(td) else 0
    if t_size or t_dirs:
        items.append({"key": "trash", "label": "已卸载 skill 回收站 (_trash)",
                      "dirs": t_dirs, "bytes": t_size})
    # 2. 过期日志（>14 天）
    logs = os.path.join(wb, "logs")
    old = 0
    old_bytes = 0
    if os.path.isdir(logs):
        cutoff = datetime.datetime.now().timestamp() - 14 * 86400
        for f in os.listdir(logs):
            fp = os.path.join(logs, f)
            try:
                if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                    old += 1
                    old_bytes += os.path.getsize(fp)
            except OSError:
                pass
    if old:
        items.append({"key": "old_logs", "label": "超过 14 天的日志 (logs/)",
                      "files": old, "bytes": old_bytes})
    return {"ok": True, "items": items, "total_bytes": sum(i["bytes"] for i in items)}


def clean_space(cfg, keys):
    wb = wb_root(cfg)
    done = []
    if "trash" in keys:
        td = trash_dir(wb)
        if os.path.isdir(td):
            shutil.rmtree(td, ignore_errors=True)
            os.makedirs(td, exist_ok=True)
            done.append("trash")
    if "old_logs" in keys:
        logs = os.path.join(wb, "logs")
        cutoff = datetime.datetime.now().timestamp() - 14 * 86400
        cnt = 0
        if os.path.isdir(logs):
            for f in os.listdir(logs):
                fp = os.path.join(logs, f)
                try:
                    if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                        cnt += 1
                except OSError:
                    pass
        done.append("old_logs:" + str(cnt))
    return {"ok": True, "done": done}


def backup(cfg):
    wb = wb_root(cfg)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(backup_dir(wb), "agent_backup_" + ts + ".zip")
    import zipfile
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        # 对话
        sess = os.path.join(wb, "sessions")
        if os.path.isdir(sess):
            for f in os.listdir(sess):
                if f.endswith(".json"):
                    z.write(os.path.join(sess, f), "sessions/" + f)
        # skill 元数据（仅 SKILL.md + frontmatter，避免打包大二进制）
        sk = os.path.join(wb, "skills")
        if os.path.isdir(sk):
            for name in os.listdir(sk):
                md = os.path.join(sk, name, "SKILL.md")
                if os.path.isfile(md):
                    z.write(md, "skills/" + name + "/SKILL.md")
    return {"ok": True, "path": out, "bytes": os.path.getsize(out)}


def compress_conversation(cfg, conv_id):
    wb = wb_root(cfg)
    fp = os.path.join(wb, "sessions", conv_id + ".json")
    if not os.path.isfile(fp):
        return {"ok": False, "error": "对话不存在"}
    data = json.load(open(fp, encoding="utf-8"))
    msgs = data.get("messages", data.get("conversations", []))
    if not msgs:
        return {"ok": False, "error": "无消息可压缩"}
    # 备份原文件
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bk = os.path.join(backup_dir(wb), "session_" + conv_id + "_" + ts + ".json")
    shutil.copy(fp, bk)
    # 简单摘要：首尾各保留 2 条 + 统计角色分布
    keep = (msgs[:2] + msgs[-2:]) if len(msgs) > 4 else msgs
    roles = {}
    for m in msgs:
        r = m.get("role", "?")
        roles[r] = roles.get(r, 0) + 1
    summary = {
        "compressed": True,
        "original_count": len(msgs),
        "compressed_at": ts,
        "role_distribution": roles,
        "messages": keep,
    }
    data["messages"] = [{"role": "system", "content": "（对话已压缩，仅保留首尾摘要）"}]
    data["messages"].append({"role": "assistant", "content": json.dumps(summary, ensure_ascii=False)})
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return {"ok": True, "backup": bk, "original": len(msgs), "kept": len(keep)}


def chat_proxy(cfg, skill_id, message, history):
    llm = cfg.get("llm", {})
    key = llm.get("api_key", "")
    if not key:
        return {"ok": False, "error": "未配置 LLM api_key，请在设置页填写"}
    base = llm.get("base_url", "https://api.openai.com/v1").rstrip("/")
    model = llm.get("model", "gpt-4o")
    # 系统上下文：skill 的 SKILL.md
    system = "你是 WorkBuddy 的助手。"
    wb = wb_root(cfg)
    md = os.path.join(wb, "skills", skill_id, "SKILL.md") if skill_id else None
    if md and os.path.isfile(md):
        system = "你正在以 skill《%s》的身份回答用户。请遵循其说明。\n\n" % skill_id
        system += open(md, encoding="utf-8", errors="ignore").read()[:6000]
    messages = [{"role": "system", "content": system}]
    for h in (history or []):
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})
    body = json.dumps({"model": model, "messages": messages, "stream": False}).encode("utf-8")
    req = urllib.request.Request(base + "/chat/completions",
                                 data=body, headers={"Authorization": "Bearer " + key,
                                                     "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode("utf-8"))
            return {"ok": True, "reply": resp["choices"][0]["message"]["content"]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "LLM HTTP %d: %s" % (e.code, e.read(200).decode("utf-8", "ignore"))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def open_in_wb(skill_id, prompt):
    # workbuddy:// 深链接（实验性：参数格式官方未文档化，最坏仅唤起 WB）
    q = ""
    if skill_id:
        q += "skill=" + urllib.parse.quote(skill_id)
    if prompt:
        q += ("&" if q else "") + "prompt=" + urllib.parse.quote(prompt)
    return "workbuddy://chat?" + q if q else "workbuddy://"


import urllib.parse  # noqa  (放末尾避免循环 import 影响上面的引用顺序)


# ---------- HTTP 处理 ----------

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj=None, body=None, ctype="application/json; charset=utf-8"):
        if obj is not None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if body is not None:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body is not None:
            self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            return self._serve_html()
        if self.path == "/api/data":
            cfg = load_config()
            data = build_data.build_agent_data(wb_root(cfg))
            return self._send(200, data)
        if self.path.startswith("/api/open-in-wb"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            url = open_in_wb(qs.get("skill", [""])[0], qs.get("prompt", [""])[0])
            return self._send(200, {"url": url})
        return self._send(404, {"error": "not found"})

    def _serve_html(self):
        html_path = os.path.join(HERE, "shop.html")
        if not os.path.isfile(html_path):
            # 现场生成
            try:
                import generate_shop
                generate_shop.render(wb_root(load_config()))
            except Exception:
                pass
        try:
            html = open(html_path, encoding="utf-8").read()
        except Exception as e:
            return self._send(500, {"error": "shop.html 缺失: " + str(e)})
        # 注入 LIVE 标记（同域即视为由 server 提供）
        html = html.replace("/*__LIVE_FLAG__*/", "window.LIVE=true;window.API='';")
        self._send(200, body=html.encode("utf-8"), ctype="text/html; charset=utf-8")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            payload = {}
        cfg = load_config()
        p = self.path
        if p == "/api/config":
            if payload:
                cfg.update(payload)
                save_config(cfg)
            return self._send(200, {"ok": True, "config": cfg})
        if p == "/api/skill/uninstall":
            return self._send(200, uninstall_skill(cfg, payload.get("id", ""), payload.get("location", "user")))
        if p == "/api/space/scan":
            return self._send(200, scan_space(cfg))
        if p == "/api/space/clean":
            return self._send(200, clean_space(cfg, payload.get("keys", [])))
        if p == "/api/backup":
            return self._send(200, backup(cfg))
        if p == "/api/conversation/compress":
            return self._send(200, compress_conversation(cfg, payload.get("id", "")))
        if p == "/api/chat":
            return self._send(200, chat_proxy(cfg, payload.get("skill_id", ""),
                                              payload.get("message", ""), payload.get("history", [])))
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print("零件杂货铺 agent 管控台已启动: http://%s:%d/" % (a.host, a.port))
    print("按 Ctrl+C 停止。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
