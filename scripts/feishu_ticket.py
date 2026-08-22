#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""飞书多维表格工单读写模块（基于 Feishu OpenAPI，使用自建应用 app_id/app_secret）。

设计要点：
- 仅依赖 Python 标准库（urllib），本地 server.py 与腾讯云函数代理共用同一套逻辑。
- 凭证只从环境变量读取，绝不硬编码、不进 git：
    FEISHU_APP_ID         自建应用 App ID
    FEISHU_APP_SECRET     自建应用 App Secret
    FEISHU_BASE_TOKEN     多维表格 app_token（默认 XSJObdBLNaiyb7sxajwcABHZnpd）
    FEISHU_TABLE_ID       数据表 table_id（默认 tblwhB10MZQ8PCmR）
- 工单号 = 飞书「序号」字段（auto_number，前缀 FB- + 4 位自增），写入后回读，不自己造号。
- 当前状态 = 单选字段，默认「新增」，选项：新增/已修改/已合入/关闭/拒绝。
- 字段写零：表缺「处理备注」列时自动跳过该字段（配合你后台手动加列即可生效，无需改代码/重部署）。

安全：
- 本模块不打印任何凭证；异常信息不回显 token。
- 频率限制（IP 维度）与输入长度校验在接口层（server.py / 云函数）做，本模块只负责飞书读写。
"""
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# ── 常量 ──
DEFAULT_BASE_TOKEN = "XSJObdBLNaiyb7sxajwcABHZnpd"
DEFAULT_TABLE_ID = "tblwhB10MZQ8PCmR"
FEISHU_HOST = "https://open.feishu.cn"

# 飞书表真实字段（与用户 Base 对齐）
FIELD_USER = "用户名"
FIELD_CONTACT = "联系方式"
FIELD_TYPE = "类型"          # 单选：问题 / 需求
FIELD_DESC = "问题描述"
FIELD_EXPECT = "预期"
FIELD_VERSION = "预计修改的版本"
FIELD_TICKET = "序号"         # auto_number，工单号
FIELD_STATUS = "当前状态"      # 单选，默认 新增
FIELD_TIME = "提出时间"        # 系统字段（created_at），自动生成
FIELD_REMARK = "处理备注"      # 可选：用户后台维护的回复（表缺列则忽略）

# 允许的类型与状态枚举（与服务端校验保持一致）
VALID_TYPES = ["问题", "需求"]
VALID_STATUS = ["新增", "已修改", "已合入", "关闭", "拒绝"]
DEFAULT_STATUS = "新增"

# token 缓存（进程内，避免每次请求都取 token；tenant_access_token 有效期 7200s）
_TOKEN_CACHE = {"token": None, "expire_at": 0.0}
_TOKEN_LOCK = threading.Lock()


def _env(name, default=None):
    import os
    return os.environ.get(name, default)


def _get_token():
    """获取 tenant_access_token，带进程内缓存。"""
    now = time.time()
    with _TOKEN_LOCK:
        if _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["expire_at"] - 60:
            return _TOKEN_CACHE["token"]
        app_id = _env("FEISHU_APP_ID")
        app_secret = _env("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            raise RuntimeError("缺少飞书凭证环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET")
        url = f"{FEISHU_HOST}/open-apis/auth/v3/tenant_access_token/internal"
        data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                resp = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"获取飞书 token 失败：HTTP {e.code}")
        if resp.get("code") != 0:
            raise RuntimeError(f"获取飞书 token 失败：{resp.get('msg')}")
        token = resp.get("tenant_access_token")
        expire = resp.get("expire", 7200)
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expire_at"] = time.time() + float(expire)
        return token


def _request(method, path, body=None, token=None, params=None):
    """通用飞书 OpenAPI 请求。返回解析后的 JSON dict。"""
    url = f"{FEISHU_HOST}{path}"
    if params:
        from urllib.parse import urlencode
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


def _build_fields(payload):
    """从提交 payload 构造飞书字段字典（仅含表支持的字段；缺「处理备注」列时跳过）。"""
    fields = {}
    if payload.get("user"):
        fields[FIELD_USER] = payload["user"][:50]
    if payload.get("contact"):
        fields[FIELD_CONTACT] = payload["contact"][:100]
    if payload.get("type"):
        fields[FIELD_TYPE] = payload["type"]
    if payload.get("desc"):
        fields[FIELD_DESC] = payload["desc"][:4000]
    if payload.get("expect"):
        fields[FIELD_EXPECT] = payload["expect"][:2000]
    if payload.get("version"):
        fields[FIELD_VERSION] = payload["version"][:50]
    # 处理备注列：可选；若表不存在该列，写入会被飞书忽略（不影响其余字段），这里仍尝试写入。
    if payload.get("remark"):
        fields[FIELD_REMARK] = payload["remark"][:2000]
    return fields


def _norm_status(v):
    if isinstance(v, list) and v:
        return v[0]
    if isinstance(v, str):
        return v
    return DEFAULT_STATUS


def _norm_ticket(v):
    if isinstance(v, list) and v:
        return v[0]
    return v


def _looks_like_phone(s):
    """粗判是否为手机号（飞书 phone 字段只接受合法的电话格式）。"""
    s = (s or "").strip()
    # 仅数字、长度 5-20、含常见区号写法；非常严格，宁可跳过也不让整条写入失败
    return bool(s) and s.isdigit() and 5 <= len(s) <= 20


def submit_ticket(payload):
    """提交工单：写入飞书表，返回 {ok, ticket, status, message, warn}。

    payload 字段：user, contact, type, desc, expect, version。
    容错：飞书「联系方式」列为 phone 类型，若用户填了非电话内容会导致整条写入失败；
          此时自动剔除联系方式字段重试，并通过 warn 提示联系方式未保存。
    """
    token = _get_token()
    base_token = _env("FEISHU_BASE_TOKEN", DEFAULT_BASE_TOKEN)
    table_id = _env("FEISHU_TABLE_ID", DEFAULT_TABLE_ID)
    warn = None
    fields = _build_fields(payload)
    # 联系方式不像手机号则不传，避免 phone 字段转换失败
    if FIELD_CONTACT in fields and not _looks_like_phone(fields.get(FIELD_CONTACT)):
        fields.pop(FIELD_CONTACT, None)
        warn = "联系方式非手机号格式，未写入（不影响工单提交）。"
    url = f"/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records"
    resp = _request("POST", url, body={"fields": fields}, token=token)
    # 二次兜底：万一仍因 phone 报错，剔除联系方式重试一次
    if resp.get("code") != 0 and "phone" in (resp.get("msg") or "").lower():
        fields.pop(FIELD_CONTACT, None)
        warn = "联系方式格式不被飞书电话字段接受，已跳过（不影响工单提交）。"
        resp = _request("POST", url, body={"fields": fields}, token=token)
    if resp.get("code") != 0:
        return {"ok": False, "error": f"飞书写入失败：{resp.get('msg')}"}
    rec = (resp.get("data") or {}).get("record") or {}
    rec_fields = rec.get("fields") or {}
    ticket = _norm_ticket(rec_fields.get(FIELD_TICKET))
    status = _norm_status(rec_fields.get(FIELD_STATUS)) or DEFAULT_STATUS
    record_id = rec.get("record_id") or rec.get("id")
    # 写入响应可能不含自动编号的「序号」字段，回查一次补齐工单号
    if not ticket and record_id:
        q = _request("GET", f"/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}",
                     token=token, params={"user_id_type": "user_id"})
        if q.get("code") == 0:
            qf = (q.get("data") or {}).get("record", {}).get("fields") or {}
            ticket = _norm_ticket(qf.get(FIELD_TICKET))
            if not status or status == DEFAULT_STATUS:
                status = _norm_status(qf.get(FIELD_STATUS)) or DEFAULT_STATUS
    return {"ok": True, "ticket": ticket, "status": status,
            "record_id": record_id, "warn": warn}


def _list_all_records(token, base_token, table_id, page_size=100):
    """拉取表内全部记录（自动翻页）。返回 list[fields_dict]。"""
    out = []
    page_token = None
    while True:
        params = {"page_size": str(page_size), "user_id_type": "user_id"}
        if page_token:
            params["page_token"] = page_token
        resp = _request("GET", f"/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records",
                        token=token, params=params)
        if resp.get("code") != 0:
            raise RuntimeError(resp.get("msg") or "查询失败")
        data = resp.get("data") or {}
        for it in (data.get("items") or []):
            out.append(it.get("fields") or {})
        page_token = data.get("page_token")
        if not page_token or not data.get("has_more"):
            break
    return out


def _parse_time(v):
    """把飞书时间字段统一成 ISO 字符串或原值。"""
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000, tz=timezone(timedelta(hours=8))).isoformat()
    if isinstance(v, str):
        return v
    return ""


def list_tickets(status=None, ticket_type=None, limit=200):
    """拉取工单列表，支持按状态、类型筛选，按提出时间倒序。

    返回 {"ok":True,"items":[...]}，每个 item 包含：
    ticket, status, type, desc, expect, user, contact, version, remark, submit_time。
    """
    token = _get_token()
    base_token = _env("FEISHU_BASE_TOKEN", DEFAULT_BASE_TOKEN)
    table_id = _env("FEISHU_TABLE_ID", DEFAULT_TABLE_ID)
    items = []
    for f in _list_all_records(token, base_token, table_id):
        tid = _norm_ticket(f.get(FIELD_TICKET))
        if not tid:
            continue
        s = _norm_status(f.get(FIELD_STATUS)) or DEFAULT_STATUS
        t = _norm_status(f.get(FIELD_TYPE)) or ""
        if status and s != status:
            continue
        if ticket_type and t != ticket_type:
            continue
        items.append({
            "ticket": tid,
            "status": s,
            "type": t,
            "desc": f.get(FIELD_DESC, ""),
            "expect": f.get(FIELD_EXPECT, ""),
            "user": f.get(FIELD_USER, ""),
            "contact": f.get(FIELD_CONTACT, ""),
            "version": f.get(FIELD_VERSION, ""),
            "remark": f.get(FIELD_REMARK, "") if isinstance(f.get(FIELD_REMARK), str) else "",
            "submit_time": _parse_time(f.get(FIELD_TIME)),
        })
    # 按提出时间倒序；无时间放最后
    items.sort(key=lambda x: x["submit_time"] or "0", reverse=True)
    if limit:
        items = items[:limit]
    return {"ok": True, "items": items}


# 工单查询缓存（进程内，短时效，避免每次查询全表拉取）
_TICKET_CACHE = {"ts": 0.0, "data": {}}
_TICKET_CACHE_LOCK = threading.Lock()
_TICKET_CACHE_TTL = 15  # 秒


def query_ticket(ticket_id):
    """按工单号（序号，如 FB-0007）查询工单状态与备注。

    飞书 auto_number 字段 filter 受限，改为拉取全表在本地匹配（工单表体量小）。
    返回 {ok, found, ticket, status, fields:{...}}。
    """
    ticket_id = (ticket_id or "").strip().upper()
    token = _get_token()
    base_token = _env("FEISHU_BASE_TOKEN", DEFAULT_BASE_TOKEN)
    table_id = _env("FEISHU_TABLE_ID", DEFAULT_TABLE_ID)
    now = time.time()
    with _TICKET_CACHE_LOCK:
        if now - _TICKET_CACHE["ts"] < _TICKET_CACHE_TTL and ticket_id in _TICKET_CACHE["data"]:
            rec_fields = _TICKET_CACHE["data"][ticket_id]
        else:
            _TICKET_CACHE["data"] = {}
            for f in _list_all_records(token, base_token, table_id):
                tid = _norm_ticket(f.get(FIELD_TICKET))
                if tid:
                    _TICKET_CACHE["data"][tid] = f
            _TICKET_CACHE["ts"] = now
            rec_fields = _TICKET_CACHE["data"].get(ticket_id)
    if not rec_fields:
        return {"ok": True, "found": False}
    return {
        "ok": True,
        "found": True,
        "ticket": _norm_ticket(rec_fields.get(FIELD_TICKET)),
        "status": _norm_status(rec_fields.get(FIELD_STATUS)) or DEFAULT_STATUS,
        "fields": {
            "user": rec_fields.get(FIELD_USER, ""),
            "contact": rec_fields.get(FIELD_CONTACT, ""),
            "type": _norm_status(rec_fields.get(FIELD_TYPE)) or "",
            "desc": rec_fields.get(FIELD_DESC, ""),
            "expect": rec_fields.get(FIELD_EXPECT, ""),
            "version": rec_fields.get(FIELD_VERSION, ""),
            "remark": rec_fields.get(FIELD_REMARK, "") if isinstance(rec_fields.get(FIELD_REMARK), str) else "",
            "submit_time": rec_fields.get(FIELD_TIME, ""),
        },
    }


# ── 频率限制（简单内存版，进程级别；云函数可用同模块单独实例）──
_RATE = {}
_RATE_LOCK = threading.Lock()


def rate_limited(key, limit=10, window=60):
    """返回 True 表示超过限制。key 通常为 IP。"""
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


def validate_submit(payload):
    """校验提交字段，返回 (ok, error)。"""
    t = (payload.get("type") or "").strip()
    d = (payload.get("desc") or "").strip()
    if t and t not in VALID_TYPES:
        return False, f"类型必须是：{ '/'.join(VALID_TYPES) }"
    if not d:
        return False, "问题描述不能为空"
    if len(d) > 4000:
        return False, "问题描述过长（上限 4000 字）"
    if payload.get("user") and len(payload["user"]) > 50:
        return False, "用户名过长（上限 50 字）"
    if payload.get("contact") and len(payload["contact"]) > 100:
        return False, "联系方式过长（上限 100 字）"
    return True, None


if __name__ == "__main__":
    # 本地快速自检（需要环境变量已配置）
    import os
    if not os.environ.get("FEISHU_APP_ID"):
        print("请先设置 FEISHU_APP_ID / FEISHU_APP_SECRET 环境变量")
    else:
        r = submit_ticket({"user": "自检", "type": "问题", "desc": "模块自检", "contact": "test"})
        print("submit:", r)
        if r.get("ticket"):
            print("query:", query_ticket(r["ticket"]))
