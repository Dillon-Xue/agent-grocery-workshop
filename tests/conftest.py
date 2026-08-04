import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

from workshop import Workshop  # noqa
from seed_initial_parts import seed  # noqa


@pytest.fixture(scope="session", autouse=True)
def _isolated_wb_root(tmp_path_factory):
    """测试会话全程使用隔离的 WorkBuddy 家目录，避免扫描真实 ~/.workbuddy。"""
    p = tmp_path_factory.mktemp("wb_root")
    os.environ["WORKBUDDY_ROOT"] = str(p)
    yield


@pytest.fixture
def root(tmp_path):
    r = str(tmp_path / "ws")
    os.makedirs(r)
    seed(r)
    ws = Workshop(r)
    gen = {
        "id": "gen_weekly",
        "name": "周报汇总助手",
        "initial_query": "汇总每周周报",
        "created_at": "2026-07-30",
        "used_part_ids": ["part_cod_001", "part_cod_002", "part_cod_006", "part_des_003"],
        "auto_dismantled": True,
        "assembly_notes": "测试用生成记录",
    }
    ws.record_generation(gen)
    return r
