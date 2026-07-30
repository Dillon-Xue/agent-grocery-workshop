"""初始零件包：23 个种子零件。

首次使用时调用 seed(root) 把零件写入 library/ 各分类目录。
零件字段对照设计文档：id/name/description/category/sub_category/type/
content/source_type/metadata 等。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workshop import Workshop  # noqa

SEED_PARTS = [
    # ---------------- 需求分析 (5) ----------------
    {
        "id": "part_req_001", "name": "需求澄清通用模板", "category": "需求分析",
        "sub_category": "需求澄清", "type": "Prompt片段",
        "description": "多轮对话中引导用户澄清需求的通用 Prompt 模板",
        "content": "你是一个需求分析专家。请通过提问帮用户澄清：目标、使用场景、输入、输出、处理流程、约束条件。每次只问 1-2 个最关键的问题，避免一次抛出过多。",
        "source_type": "initial",
        "metadata": {"tags": ["需求分析", "对话引导"], "author": "initial-pack"},
    },
    {
        "id": "part_req_002", "name": "场景分析框架", "category": "需求分析",
        "sub_category": "场景拆解", "type": "流程规范",
        "description": "把用户模糊想法拆成具体使用场景的方法",
        "content": "步骤：1) 列出所有潜在使用者角色；2) 对每个角色写出『在什么情况下、要完成什么、当前痛点是什么』；3) 按频次与价值排序，挑出 Top3 场景优先实现。",
        "source_type": "initial",
        "metadata": {"tags": ["场景", "拆解"], "author": "initial-pack"},
    },
    {
        "id": "part_req_003", "name": "痛点识别模板", "category": "需求分析",
        "sub_category": "痛点挖掘", "type": "Prompt片段",
        "description": "引导用户描述当前痛点的 Prompt",
        "content": "请描述：你现在是怎么解决这个问题的？最花时间/最容易出错的环节是什么？如果完美解决，会带来什么量化收益？",
        "source_type": "initial",
        "metadata": {"tags": ["痛点", "访谈"], "author": "initial-pack"},
    },
    {
        "id": "part_req_004", "name": "目标定义模板", "category": "需求分析",
        "sub_category": "目标定义", "type": "Prompt片段",
        "description": "用 SMART 原则引导定义目标",
        "content": "把目标改写成 SMART：具体(Specific)、可衡量(Measurable)、可达成(Achievable)、相关(Relevant)、有时限(Time-bound)。逐项追问用户补全。",
        "source_type": "initial",
        "metadata": {"tags": ["SMART", "目标"], "author": "initial-pack"},
    },
    {
        "id": "part_req_005", "name": "约束条件清单", "category": "需求分析",
        "sub_category": "约束检查", "type": "流程规范",
        "description": "技术/资源/时间约束检查清单",
        "content": "检查项：运行环境(本地/云端)、鉴权方式、数据隐私边界、第三方依赖是否可联网、交付时间窗、是否需要多人协作。任一项不确定都要向用户确认。",
        "source_type": "initial",
        "metadata": {"tags": ["约束", "边界"], "author": "initial-pack"},
    },
    # ---------------- 方案设计 (4) ----------------
    {
        "id": "part_des_001", "name": "技术选型决策树", "category": "方案设计",
        "sub_category": "技术选型", "type": "流程规范",
        "description": "根据需求推荐技术栈的决策树",
        "content": "Q1 是否需要 UI？是→前端栈；否→CLI/脚本。Q2 是否重 IO？是→异步框架。Q3 是否需持久化？是→SQLite/轻库。每次只沿一条分支深入，给出理由。",
        "source_type": "initial",
        "metadata": {"tags": ["选型", "决策"], "author": "initial-pack"},
    },
    {
        "id": "part_des_002", "name": "架构设计模板", "category": "方案设计",
        "sub_category": "模块划分", "type": "流程规范",
        "description": "模块划分与数据流设计模板",
        "content": "# 架构\n- 输入：\n- 处理模块：\n- 输出：\n- 数据流：输入 → 模块A → 模块B → 输出\n- 异常路径：",
        "source_type": "initial",
        "metadata": {"tags": ["架构", "模块"], "author": "initial-pack"},
    },
    {
        "id": "part_des_003", "name": "API设计规范", "category": "方案设计",
        "sub_category": "接口规范", "type": "参考文档",
        "description": "RESTful API 设计标准参考",
        "content": "资源用名词复数；GET 读、POST 建、PUT 全量改、PATCH 局部改、DELETE 删；路径用 kebab-case；错误统一 {code,message}；分页用 ?page&size。",
        "source_type": "initial",
        "metadata": {"tags": ["API", "REST"], "author": "initial-pack"},
    },
    {
        "id": "part_des_004", "name": "数据模型设计模板", "category": "方案设计",
        "sub_category": "数据建模", "type": "参考文档",
        "description": "实体关系设计指南",
        "content": "列出实体 → 标注字段与类型 → 标注实体间关系(1:1/1:N/N:N) → 写出建表/建类语句草稿 → 检查冗余与范式。",
        "source_type": "initial",
        "metadata": {"tags": ["数据模型", "ER"], "author": "initial-pack"},
    },
    # ---------------- 代码开发 (6) ----------------
    {
        "id": "part_cod_001", "name": "requests库调用模板", "category": "代码开发",
        "sub_category": "HTTP调用", "type": "Python代码片段",
        "description": "带超时与重试的 HTTP 请求封装",
        "content": "import requests\n\ndef http_get(url, timeout=10, headers=None):\n    resp = requests.get(url, timeout=timeout, headers=headers)\n    resp.raise_for_status()\n    return resp.json()",
        "content_format": "python",
        "source_type": "initial",
        "metadata": {"tags": ["http", "requests"], "author": "initial-pack"},
    },
    {
        "id": "part_cod_002", "name": "文件读写模板", "category": "代码开发",
        "sub_category": "本地IO", "type": "Python代码片段",
        "description": "本地文件安全读写",
        "content": "def read_text(path):\n    with open(path, 'r', encoding='utf-8') as f:\n        return f.read()\n\ndef write_text(path, text):\n    import os\n    os.makedirs(os.path.dirname(path), exist_ok=True)\n    with open(path, 'w', encoding='utf-8') as f:\n        f.write(text)",
        "content_format": "python",
        "source_type": "initial",
        "metadata": {"tags": ["io", "文件"], "author": "initial-pack"},
    },
    {
        "id": "part_cod_003", "name": "JSON处理模板", "category": "代码开发",
        "sub_category": "序列化", "type": "Python代码片段",
        "description": "JSON 序列化/反序列化",
        "content": "import json\n\ndef dump_json(obj, path):\n    with open(path, 'w', encoding='utf-8') as f:\n        json.dump(obj, f, ensure_ascii=False, indent=2)\n\ndef load_json(path):\n    with open(path, 'r', encoding='utf-8') as f:\n        return json.load(f)",
        "content_format": "python",
        "source_type": "initial",
        "metadata": {"tags": ["json"], "author": "initial-pack"},
    },
    {
        "id": "part_cod_004", "name": "日志配置模板", "category": "代码开发",
        "sub_category": "日志", "type": "Python代码片段",
        "description": "logging 标准配置",
        "content": "import logging\n\nlogging.basicConfig(\n    level=logging.INFO,\n    format='%(asctime)s %(levelname)s %(message)s',\n)\nlog = logging.getLogger(__name__)",
        "content_format": "python", "source_type": "initial", "metadata": {"tags": ["log"], "author": "initial-pack"},
    },
    {
        "id": "part_cod_005", "name": "错误处理模板", "category": "代码开发",
        "sub_category": "异常", "type": "Python代码片段",
        "description": "try-except 封装与友好报错",
        "content": "def safe_run(fn, *args, **kwargs):\n    try:\n        return fn(*args, **kwargs)\n    except FileNotFoundError as e:\n        log.error('文件缺失: %s', e)\n    except Exception as e:\n        log.exception('未预期错误')\n    return None",
        "content_format": "python", "source_type": "initial", "metadata": {"tags": ["error"], "author": "initial-pack"},
    },
    {
        "id": "part_cod_006", "name": "日期格式化模板", "category": "代码开发",
        "sub_category": "时间", "type": "Python代码片段",
        "description": "datetime 统一处理",
        "content": "from datetime import datetime\n\ndef now_str(fmt='%Y-%m-%d %H:%M:%S'):\n    return datetime.now().strftime(fmt)\n\ndef parse(s, fmt='%Y-%m-%d'):\n    return datetime.strptime(s, fmt)",
        "content_format": "python", "source_type": "initial", "metadata": {"tags": ["datetime"], "author": "initial-pack"},
    },
    # ---------------- 测试用例 (3) ----------------
    {
        "id": "part_tst_001", "name": "pytest基础模板", "category": "测试用例",
        "sub_category": "单测", "type": "Python代码片段",
        "description": "单元测试框架骨架",
        "content": "def test_example():\n    assert 1 + 1 == 2\n\ndef test_raises():\n    import pytest\n    with pytest.raises(ValueError):\n        int('x')",
        "content_format": "python", "source_type": "initial", "metadata": {"tags": ["pytest"], "author": "initial-pack"},
    },
    {
        "id": "part_tst_002", "name": "测试数据构造模板", "category": "测试用例",
        "sub_category": "数据构造", "type": "Python代码片段",
        "description": "模拟数据生成",
        "content": "import dataclasses\n\ndef make_sample(**overrides):\n    base = {'id': 1, 'name': 'sample'}\n    base.update(overrides)\n    return base",
        "content_format": "python", "source_type": "initial", "metadata": {"tags": ["fixture"], "author": "initial-pack"},
    },
    {
        "id": "part_tst_003", "name": "集成测试模板", "category": "测试用例",
        "sub_category": "联调", "type": "流程规范",
        "description": "多模块联调方案",
        "content": "准备环境 → 灌入测试数据 → 依次调用模块A/B/C → 校验最终状态 → 清理。每个步骤失败立即中断并保留现场日志。",
        "source_type": "initial", "metadata": {"tags": ["integration"], "author": "initial-pack"},
    },
    # ---------------- 依赖工具 (4) ----------------
    {
        "id": "part_tool_001", "name": "Python虚拟环境配置", "category": "依赖工具",
        "sub_category": "环境", "type": "配置文件",
        "description": "venv 创建与激活", "content": "python -m venv .venv\nsource .venv/bin/activate  # Windows: .venv\\Scripts\\activate",
        "content_format": "yaml", "source_type": "initial", "metadata": {"tags": ["venv"], "author": "initial-pack"},
    },
    {
        "id": "part_tool_002", "name": "requirements模板", "category": "依赖工具",
        "sub_category": "依赖", "type": "配置文件",
        "description": "依赖清单格式", "content": "requests>=2.31.0\npytest>=8.0.0\n",
        "content_format": "yaml", "source_type": "initial", "metadata": {"tags": ["pip"], "author": "initial-pack"},
    },
    {
        "id": "part_tool_003", "name": "Docker基础配置", "category": "依赖工具",
        "sub_category": "容器", "type": "配置文件",
        "description": "最小 Python 镜像 Dockerfile",
        "content": "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nCMD [\"python\", \"main.py\"]",
        "content_format": "yaml", "source_type": "initial", "metadata": {"tags": ["docker"], "author": "initial-pack"},
    },
    {
        "id": "part_tool_004", "name": "Git工作流规范", "category": "依赖工具",
        "sub_category": "版本控制", "type": "参考文档",
        "description": "版本控制最佳实践",
        "content": "main 受保护；功能走 feature/* 分支；提交信息用『动词 对象』；合并前跑测试；禁止 --no-verify 跳过钩子。",
        "source_type": "initial", "metadata": {"tags": ["git"], "author": "initial-pack"},
    },
    # ---------------- 参考文档 (1) ----------------
    {
        "id": "part_ref_001", "name": "Skill开发最佳实践", "category": "参考文档",
        "sub_category": "通用", "type": "参考文档",
        "description": "通用 Skill 开发指南",
        "content": "SKILL.md 第一行为名称；用 YAML frontmatter 写 description/metadata；步骤用有序列表；脚本放 scripts/；避免写死绝对路径；说明触发场景与示例。",
        "source_type": "initial", "metadata": {"tags": ["skill", "best-practice"], "author": "initial-pack"},
    },
]


def seed(root: str) -> int:
    ws = Workshop(root)
    count = 0
    for part in SEED_PARTS:
        ws.add_part(dict(part))
        count += 1
    return count


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    n = seed(target)
    print(f"已写入 {n} 个初始零件到 {target}/library/")
