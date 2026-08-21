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
