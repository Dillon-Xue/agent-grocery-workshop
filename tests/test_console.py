"""管控台后端纯函数测试（不依赖真实数据 / 网络 / Windows 副作用）。

早期版本曾针对 open_in_wb / scan_space / uninstall_skill 等独立函数，
这些能力在管控台 v3 后端中已重构为 HTTP handler（handle_open_workbuddy /
handle_skill_delete 等），无独立可单测函数。此处改为覆盖当前 server 模块中
真实存在的纯函数与路径安全逻辑。
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_data
import server


def test_build_agent_data_structure(tmp_path):
    d = build_data.build_agent_data(str(tmp_path))
    assert "agent" in d and "skills" in d and "tasks" in d
    assert "conversations" in d and "anomalies" in d
    assert isinstance(d["agent"]["skill_count"], int)
    assert d["agent"]["skill_count"] == 0


def test_safe_under_allows_nested_and_blocks_traversal():
    base = Path("/home/user/.workbuddy/skills")
    assert server.safe_under(base, Path("/home/user/.workbuddy/skills/foo")) is True
    assert server.safe_under(base, Path("/home/user/.workbuddy/skills/foo/bar")) is True
    assert server.safe_under(base, Path("/home/user/.workbuddy/../etc")) is False
    assert server.safe_under(base, Path("/etc/passwd")) is False
    assert server.safe_under(base, base) is True


def test_compare_version_semver():
    assert server.compare_version("1.2.3", "1.2.3") == 0
    assert server.compare_version("1.2.3", "1.2.4") < 0
    assert server.compare_version("1.3.0", "1.2.9") > 0
    assert server.compare_version("0.9.0", "1.0.0") < 0


def test_find_workbuddy_exe_returns_path_or_none():
    # 仅探测可执行文件是否存在，不真正启动 WorkBuddy（避免副作用）
    res = server.find_workbuddy_exe()
    assert res is None or isinstance(res, (str, os.PathLike))
