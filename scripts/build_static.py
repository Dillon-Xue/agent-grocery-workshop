#!/usr/bin/env python3
"""构建可分享的静态控制台页面。

流程：
1. 刷新 workshop / storage 快照到 console.html / console_data.json；
2. 创建 deploy_static 目录；
3. 复制 console.html（重命名为 index.html）、console_data.json、assets；
4. 在 index.html 的 init 函数处注入 window.STATIC_MODE=true，
   使静态页明确知道自己无后端，避免空间管理等页面继续向后端发请求。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_HTML = ROOT / "scripts" / "console.html"
SRC_DATA = ROOT / "scripts" / "console_data.json"
SRC_ASSETS = ROOT / "scripts" / "assets"
DST = ROOT / "deploy_static"


def _load_env_file():
    """加载仓库根目录 .env 到当前进程环境变量，供 feishu_ticket 读取凭证。"""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and os.environ.get(key) is None:
            os.environ[key] = val


def fetch_ticket_snapshot() -> list:
    """拉取当前飞书多维表格中的全部工单，作为静态分享页的快照数据。

    快照只在构建时注入到 deploy_static/index.html，不进 git（deploy_static/ 已忽略）。
    """
    _load_env_file()
    if not os.environ.get("FEISHU_APP_ID") or not os.environ.get("FEISHU_APP_SECRET"):
        return []
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import feishu_ticket
        result = feishu_ticket.list_tickets(limit=10000)
        return result.get("items", []) if result.get("ok") else []
    except Exception as exc:
        print(f"[build_static] ticket snapshot failed: {exc}", file=sys.stderr)
        return []


def run_refresher(script_name: str) -> bool:
    script = ROOT / "scripts" / script_name
    if not script.exists():
        print(f"[build_static] {script_name} not found, skipping")
        return False
    print(f"[build_static] running {script_name}...")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"{script_name} failed with exit code {result.returncode}")
    return True


def inject_static_mode(html: str) -> str:
    # 把 init 函数里的 window.STATIC_MODE = false; 改成 true，
    # 使静态页明确知道自己无后端（console.html catch 分支里本来也有 true，但那是回退分支）
    new_html = re.sub(
        r"(function init\(data\)\{\s*DATA=data;\s*)window\.STATIC_MODE = false;",
        r"\1window.STATIC_MODE = true;",
        html,
    )
    if new_html == html:
        # 兜底：在第一个 <script> 标签内的顶部添加
        new_html = html.replace(
            "<script>\nconst TAB_META",
            "<script>\nwindow.STATIC_MODE = true;\nconst TAB_META",
        )
    # 注入分享页工单云代理地址（部署分享页时通过环境变量 TICKET_API_BASE 传入；
    # 留空则不注入，前端回退到同域后端，本地控制台不受影响）
    ticket_api = os.environ.get("TICKET_API_BASE", "").strip().rstrip("/")
    if ticket_api:
        new_html = new_html.replace(
            "<script>\nwindow.STATIC_MODE = true;",
            f"<script>\nwindow.TICKET_API_BASE = {json.dumps(ticket_api)};\nwindow.STATIC_MODE = true;",
            1,
        )
    return new_html


def main():
    # 1. 刷新快照
    run_refresher("refresh_workshop_snapshot.py")
    run_refresher("refresh_storage_snapshot.py")

    # 2. 确认源文件
    if not SRC_HTML.exists():
        raise FileNotFoundError(f"{SRC_HTML} not found")
    if not SRC_DATA.exists():
        raise FileNotFoundError(f"{SRC_DATA} not found")

    # 3. 构建部署目录
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)

    html = open(SRC_HTML, encoding="utf-8").read()
    html = inject_static_mode(html)

    # 注入当前飞书工单快照（只进构建产物，不进 git）
    snapshot_items = fetch_ticket_snapshot()
    if snapshot_items:
        snapshot_json = json.dumps(snapshot_items, ensure_ascii=False, separators=(",", ":"))
        if "<script>\nconst TAB_META" in html:
            html = html.replace(
                "<script>\nconst TAB_META",
                f"<script>\nwindow.TICKET_SNAPSHOT = {snapshot_json};\nconst TAB_META",
                1,
            )
            print(f"[build_static] ticket snapshot injected: {len(snapshot_items)} items")
        else:
            print("[build_static] warning: TICKET_SNAPSHOT anchor not found, skipping injection")

    # 校验内联数据 JSON 有效
    m = re.search(r"const EMBEDDED_DATA = (.*?);/\*__WB_DATA_END__\*/", html, re.S)
    if m:
        json.loads(m.group(1))
    else:
        print("[build_static] warning: EMBEDDED_DATA anchor not found")

    (DST / "index.html").write_text(html, encoding="utf-8")
    shutil.copy2(SRC_DATA, DST / "console_data.json")

    if SRC_ASSETS.exists():
        shutil.copytree(SRC_ASSETS, DST / "assets")

    # 4. 打印摘要
    data = json.loads(open(SRC_DATA, encoding="utf-8").read())
    ov = data.get("overview", {})
    print("[build_static] deploy_static ready")
    print(f"  generated_at: {data.get('generated_at')}")
    print(f"  skills: {len(data.get('skills', []))}")
    print(f"  workshop parts: {data.get('workshop', {}).get('stats', {}).get('parts')}")
    print(f"  workshop generations: {data.get('workshop', {}).get('stats', {}).get('generations')}")
    print(f"  storage total: {ov.get('total_storage')}")
    print(f"  files:")
    for p in sorted(DST.rglob("*")):
        if p.is_file():
            print(f"    {p.relative_to(DST)} ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
