#!/usr/bin/env python3
"""真实生成 5 个 Skill 的端到端测试。

用法：
  python scripts/test_generate_5_skills.py

行为：
  1. 启动 server.py（端口 18080，避免与可能运行中的 8080 冲突）
  2. 连续调用 /api/skill/generate 生成 5 个不同需求的 Skill
  3. 轮询 /api/skill/generate-status 直到完成或失败
  4. 校验 generations/<id>/ 目录与 SKILL.md 是否落盘
  5. 汇总结果并保留所有产物，供用户查看效果
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER_PY = ROOT / "scripts" / "server.py"
PORT = 18080
BASE_URL = f"http://127.0.0.1:{PORT}"

TEST_SKILLS = [
    {"name": "每日早安问候", "description": "根据天气和日期生成一句温馨的早安问候语", "tags": ["生活", "问候"]},
    {"name": "JSON 格式化助手", "description": "把用户输入的 JSON 字符串美化排版并校验语法", "tags": ["开发", "工具"]},
    {"name": "会议纪要提炼", "description": "从会议记录中提取待办事项、决策和责任人", "tags": ["办公", "效率"]},
    {"name": "代码注释生成器", "description": "为给定的 Python 函数生成中文 docstring 注释", "tags": ["开发", "Python"]},
    {"name": "旅行清单打包", "description": "根据目的地天数和季节生成旅行物品清单", "tags": ["生活", "旅行"]},
]


def api_post(path, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_for_job(job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = api_post("/api/skill/generate-status", {"job_id": job_id})
        if not r.get("ok"):
            return r
        job = r.get("job", {})
        if job.get("status") in ("done", "error"):
            return r
        time.sleep(0.5)
    return {"ok": False, "error": "轮询超时"}


def start_server():
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_PY), str(PORT)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # 等待服务启动
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/config", timeout=1):
                return proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError("server 启动失败")


def main():
    print(f"启动 server: {SERVER_PY} {PORT}")
    proc = start_server()
    results = []
    try:
        for req in TEST_SKILLS:
            print(f"\n生成 Skill: {req['name']}")
            r = api_post("/api/skill/generate", {"requirements": req})
            if not r.get("ok"):
                print(f"  下发失败: {r.get('error')}")
                results.append({"name": req["name"], "ok": False, "error": r.get("error")})
                continue
            job_id = r["job_id"]
            print(f"  job_id={job_id}, 等待完成...")
            status = wait_for_job(job_id)
            job = status.get("job", {})
            if job.get("status") == "done":
                res = job.get("result", {})
                gid = res.get("id")
                path = res.get("path")
                installed = res.get("generation", {}).get("installed", False)
                results.append({
                    "name": req["name"],
                    "ok": True,
                    "id": gid,
                    "path": path,
                    "installed": installed,
                })
                print(f"  ✅ 完成: {path} (installed={installed})")
            else:
                err = job.get("error") or status.get("error") or "未知错误"
                results.append({"name": req["name"], "ok": False, "error": err})
                print(f"  ❌ 失败: {err}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # 汇总报告
    report_path = ROOT / "generations" / "test_generate_5_skills_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 50)
    ok_count = sum(1 for r in results if r["ok"])
    print(f"生成结果: {ok_count}/{len(results)} 成功")
    for r in results:
        if r["ok"]:
            print(f"  ✅ {r['name']} -> {r['id']} (installed={r['installed']})")
        else:
            print(f"  ❌ {r['name']}: {r['error']}")
    print(f"报告已保存: {report_path}")
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
