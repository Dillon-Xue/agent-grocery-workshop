#!/usr/bin/env python3
"""测试 /api/chat 在遇到 401 时是否返回详细错误并写入日志。

本脚本会启动一个本地 mock LLM 服务（固定返回 401），然后让 server.py 的
/api/chat 转发请求到该 mock，验证错误处理与日志落盘。
"""
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 18082
MOCK_PORT = 18083
BASE_URL = f"http://127.0.0.1:{PORT}"
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"


class MockLLM(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "invalid api key"}).encode("utf-8"))


def start_mock():
    srv = HTTPServer(("127.0.0.1", MOCK_PORT), MockLLM)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def api_post(path, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(body)
        except Exception:
            return {"ok": False, "error": body}


def start_server():
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "server.py"), str(PORT)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/config", timeout=1):
                return proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError("server 启动失败")


def main():
    mock = start_mock()
    proc = start_server()
    try:
        r = api_post("/api/chat", {
            "base_url": MOCK_URL,
            "api_key": "fake-key-for-401-test",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
        })
        print("返回结果:", r)
        assert not r.get("ok"), "期望返回 ok=False"
        err = r.get("error", "")
        assert "401" in err, f"错误信息中应包含 401，实际: {err}"
        assert "invalid api key" in err, f"错误信息中应包含响应体，实际: {err}"
        print("✅ /api/chat 401 错误信息已正确返回（含响应体）")

        # 检查日志
        log = Path.home() / ".workbuddy" / "logs" / "agent-grocery-workshop.log"
        if log.exists():
            text = log.read_text(encoding="utf-8")
            assert "/api/chat HTTP 401" in text, "日志中应包含 /api/chat HTTP 401"
            print("✅ 401 已写入日志文件:", log)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        mock.shutdown()


if __name__ == "__main__":
    sys.exit(main())
