#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腾讯云函数（SCF）工单代理 —— 公开分享页提交/查询工单的中转服务。

职责：
- 对外暴露两个最小接口（避免暴露任意读表能力）：
    POST /ticket            提交工单 → 写飞书 Base → 返回工单号+状态
    GET  /ticket?ticket=FB-0007  按工单号查询状态+处理备注
- 凭证仅从环境变量读取（云函数后台配置，不进代码/git）：
    FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_BASE_TOKEN / FEISHU_TABLE_ID
- 复用与本地 server 一致的飞书字段映射与校验逻辑（此处自包含，便于独立打包部署）。

部署说明（腾讯云函数 SCF）：
1. 新建 Python3 函数，运行方式「Web 函数」或「事件函数（API 网关触发）」。
2. 上传本文件（含 main_handler）。
3. 在「函数配置 → 环境变量」配置 FEISHU_APP_ID / FEISHU_APP_SECRET 等值。
4. API 网关开启「集成响应」，并将函数 URL 配置为分享页 window.TICKET_API_BASE。
5. 本地测试：python ticket_cloud_proxy.py 启动内置 HTTP（:9000），curl 联调。
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, parse_qs
from datetime import datetime

# ── 本地测试时加载 .env（云函数环境用真实环境变量，不依赖此文件）──
def _load_env_file():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        envp = os.path.join(here, "..", ".env")  # 项目根目录 .env
        if not os.path.exists(envp):
            envp = os.path.join(here, ".env")
        if not os.path.exists(envp):
            return
        for line in open(envp, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass

_load_env_file()

FEISHU_HOST = "https://open.feishu.cn"
DEFAULT_BASE_TOKEN = "XSJObdBLNaiyb7sxajwcABHZnpd"
DEFAULT_TABLE_ID = "tblwhB10MZQ8PCmR"

FIELD_USER = "用户名"
FIELD_CONTACT = "联系方式"
FIELD_TYPE = "类型"
FIELD_DESC = "问题描述"
FIELD_EXPECT = "预期"
FIELD_VERSION = "预计修改的版本"
FIELD_TICKET = "序号"
FIELD_STATUS = "当前状态"
FIELD_TIME = "提出时间"
FIELD_REMARK = "处理备注"

VALID_TYPES = ["问题", "需求"]
VALID_STATUS = ["新增", "已修改", "已合入", "关闭", "拒绝"]
DEFAULT_STATUS = "新增"

_TOKEN_CACHE = {"token": None, "expire_at": 0.0}
_TOKEN_LOCK = threading.Lock()
_RATE = {}
_RATE_LOCK = threading.Lock()


def _env(name, default=None):
    return os.environ.get(name, default)


def _get_token():
    now = time.time()
    with _TOKEN_LOCK:
        if _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["expire_at"] - 60:
            return _TOKEN_CACHE["token"]
        app_id, app_secret = _env("FEISHU_APP_ID"), _env("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            raise RuntimeError("缺少飞书凭证环境变量")
        data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
        req = urllib.request.Request(
            f"{FEISHU_HOST}/open-apis/auth/v3/tenant_access_token/internal",
            data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                resp = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"获取飞书 token 失败：HTTP {e.code}")
        if resp.get("code") != 0:
            raise RuntimeError(f"获取飞书 token 失败：{resp.get('msg')}")
        _TOKEN_CACHE["token"] = resp["tenant_access_token"]
        _TOKEN_CACHE["expire_at"] = time.time() + float(resp.get("expire", 7200))
        return _TOKEN_CACHE["token"]


def _request(method, path, body=None, token=None, params=None):
    url = f"{FEISHU_HOST}{path}"
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            raise RuntimeError(f"飞书 API 请求失败：HTTP {e.code}")


def _norm(v):
    if isinstance(v, list) and v:
        return v[0]
    return v


def _looks_like_phone(s):
    s = (s or "").strip()
    return bool(s) and s.isdigit() and 5 <= len(s) <= 20


def _validate(payload):
    t = (payload.get("type") or "").strip()
    d = (payload.get("desc") or "").strip()
    if t and t not in VALID_TYPES:
        return False, f"类型必须是：{'/'.join(VALID_TYPES)}"
    if not d:
        return False, "问题描述不能为空"
    if len(d) > 4000:
        return False, "问题描述过长（上限 4000 字）"
    return True, None


def _list_all(token, base, table):
    out, page = [], None
    while True:
        p = {"page_size": "100", "user_id_type": "user_id"}
        if page:
            p["page_token"] = page
        d = _request("GET", f"/open-apis/bitable/v1/apps/{base}/tables/{table}/records",
                     token=token, params=p)
        if d.get("code") != 0:
            raise RuntimeError(d.get("msg") or "查询失败")
        data = d.get("data") or {}
        for it in (data.get("items") or []):
            out.append(it.get("fields") or {})
        page = data.get("page_token")
        if not page or not data.get("has_more"):
            break
    return out


def submit(payload):
    token = _get_token()
    base = _env("FEISHU_BASE_TOKEN", DEFAULT_BASE_TOKEN)
    table = _env("FEISHU_TABLE_ID", DEFAULT_TABLE_ID)
    fields = {}
    if payload.get("user"):
        fields[FIELD_USER] = payload["user"][:50]
    if payload.get("contact") and _looks_like_phone(payload["contact"]):
        fields[FIELD_CONTACT] = payload["contact"][:100]
    if payload.get("type"):
        fields[FIELD_TYPE] = payload["type"]
    if payload.get("desc"):
        fields[FIELD_DESC] = payload["desc"][:4000]
    if payload.get("expect"):
        fields[FIELD_EXPECT] = payload["expect"][:2000]
    if payload.get("version"):
        fields[FIELD_VERSION] = payload["version"][:50]
    url = f"/open-apis/bitable/v1/apps/{base}/tables/{table}/records"
    resp = _request("POST", url, body={"fields": fields}, token=token)
    if resp.get("code") != 0 and "phone" in (resp.get("msg") or "").lower():
        fields.pop(FIELD_CONTACT, None)
        resp = _request("POST", url, body={"fields": fields}, token=token)
    if resp.get("code") != 0:
        return {"ok": False, "error": f"飞书写入失败：{resp.get('msg')}"}
    rec = (resp.get("data") or {}).get("record") or {}
    rid = rec.get("record_id") or rec.get("id")
    ticket = _norm(rec.get("fields", {}).get(FIELD_TICKET))
    status = _norm(rec.get("fields", {}).get(FIELD_STATUS)) or DEFAULT_STATUS
    if not ticket and rid:
        q = _request("GET", f"/open-apis/bitable/v1/apps/{base}/tables/{table}/records/{rid}",
                     token=token, params={"user_id_type": "user_id"})
        if q.get("code") == 0:
            qf = (q.get("data") or {}).get("record", {}).get("fields") or {}
            ticket = _norm(qf.get(FIELD_TICKET))
    return {"ok": True, "ticket": ticket, "status": status or DEFAULT_STATUS}


def query(ticket_id):
    ticket_id = (ticket_id or "").strip().upper()
    token = _get_token()
    base = _env("FEISHU_BASE_TOKEN", DEFAULT_BASE_TOKEN)
    table = _env("FEISHU_TABLE_ID", DEFAULT_TABLE_ID)
    for f in _list_all(token, base, table):
        if _norm(f.get(FIELD_TICKET)) == ticket_id:
            return {
                "ok": True, "found": True, "ticket": _norm(f.get(FIELD_TICKET)),
                "status": _norm(f.get(FIELD_STATUS)) or DEFAULT_STATUS,
                "fields": {
                    "user": f.get(FIELD_USER, ""), "contact": f.get(FIELD_CONTACT, ""),
                    "type": _norm(f.get(FIELD_TYPE)) or "", "desc": f.get(FIELD_DESC, ""),
                    "expect": f.get(FIELD_EXPECT, ""), "version": f.get(FIELD_VERSION, ""),
                    "remark": f.get(FIELD_REMARK, "") if isinstance(f.get(FIELD_REMARK), str) else "",
                    "submit_time": f.get(FIELD_TIME, ""),
                },
            }
    return {"ok": True, "found": False}


def rate_limited(key, limit=20, window=60):
    now = time.time()
    with _RATE_LOCK:
        hits = _RATE.get(key, [])
        hits = [t for t in hits if now - t < window]
        if len(hits) >= limit:
            _RATE[key] = hits
            return True
        hits.append(now)
        _RATE[key] = hits
        return False


def handle_ticket(event):
    """统一处理 ticket 请求，返回 (status_code, dict)。event 为 SCF/本地通用结构。"""
    method = (event.get("httpMethod") or event.get("method") or "GET").upper()
    path = event.get("path") or "/ticket"
    qs = event.get("queryString") or {}
    if isinstance(qs, str):
        qs = parse_qs(qs)
    body = event.get("body") or "{}"
    try:
        payload = json.loads(body) if isinstance(body, str) else body
    except Exception:
        payload = {}

    client_ip = (event.get("requestContext") or {}).get("sourceIp", "unknown")
    if method == "POST":
        if rate_limited("submit:" + str(client_ip), limit=20, window=60):
            return 429, {"ok": False, "error": "提交过于频繁，请稍后再试"}
        ok, err = _validate(payload or {})
        if not ok:
            return 400, {"ok": False, "error": err}
        try:
            res = submit(payload)
        except Exception as e:
            return 502, {"ok": False, "error": "工单提交失败，请稍后重试"}
        if not res.get("ok"):
            return 502, res
        return 200, {"ok": True, "ticket": res["ticket"], "status": res["status"],
                     "message": "工单已提交，可在「我的工单」中查询状态。"}
    else:  # GET
        ticket_id = (qs.get("ticket") or [""])[0] if isinstance(qs.get("ticket"), list) else qs.get("ticket", "")
        ticket_id = (ticket_id or "").strip()
        if not ticket_id:
            return 400, {"ok": False, "error": "请提供工单号"}
        try:
            res = query(ticket_id)
        except Exception:
            return 502, {"ok": False, "error": "查询失败，请稍后重试"}
        return 200, res


def main_handler(event, context):
    """腾讯云函数 SCF 入口（API 网关触发）。"""
    code, data = handle_ticket(event)
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json; charset=utf-8",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type"},
        "body": json.dumps(data, ensure_ascii=False),
    }


# ── 本地内置 HTTP server（便于联调，非云函数运行时）──
if __name__ == "__main__":
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import sys

    class H(BaseHTTPRequestHandler):
        def _send(self, code, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            from urllib.parse import urlparse
            u = urlparse(self.path)
            code, d = handle_ticket({"httpMethod": "GET", "path": u.path,
                                     "queryString": {k: v[0] for k, v in parse_qs(u.query).items()}})
            self._send(code, d)

        def do_POST(self):
            from urllib.parse import urlparse
            u = urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            code, d = handle_ticket({"httpMethod": "POST", "path": u.path, "body": body})
            self._send(code, d)

        def log_message(self, *a):
            pass

    port = int(os.environ.get("PORT", "9000"))
    print(f"本地工单代理测试服务：http://127.0.0.1:{port}")
    HTTPServer(("0.0.0.0", port), H).serve_forever()
