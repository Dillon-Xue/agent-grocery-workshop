#!/usr/bin/env python3
"""测试删除修复：
1. 删除一个真实存在的生成 Skill（每日早安问候）。
2. 再次删除同一个 Skill（目录已不存在），验证返回 ok 且前端可同步移除。"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 18081
BASE_URL = f"http://127.0.0.1:{PORT}"
SKILL_ID = "每日早安问候"


def api_post(path, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    proc = start_server()
    try:
        # 1. 正常删除
        print(f"1) 删除存在的 Skill: {SKILL_ID}")
        r1 = api_post("/api/skill/delete", {"skill_id": SKILL_ID})
        print(f"   -> ok={r1.get('ok')}, backup={r1.get('backup')}")
        assert r1.get("ok") is True, f"期望 ok=True，实际 {r1}"

        # 2. 再次删除（目录已不存在）
        print(f"2) 再次删除（已不存在）: {SKILL_ID}")
        r2 = api_post("/api/skill/delete", {"skill_id": SKILL_ID})
        print(f"   -> ok={r2.get('ok')}, already_removed={r2.get('already_removed')}")
        assert r2.get("ok") is True, f"期望 ok=True，实际 {r2}"
        assert r2.get("already_removed") is True, f"期望 already_removed=True，实际 {r2}"

        print("\n✅ 删除修复测试通过")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
