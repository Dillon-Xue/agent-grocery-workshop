# 零件杂货铺 (Grocery Workshop)

> 一个把 Agent 拆成「零件」、又能把零件「组装」回新 Skill 的本地工作台；并内置 WorkBuddy 管控台（console.html）。安装即可在浏览器统一管理 Skill / 存储 / 对话，零件库越用越满。

## 一、名称
零件杂货铺（Grocery Workshop）

## 二、描述
通过多轮澄清需求、从零件库检索匹配、冲突二选一 + 依赖补全，自动拼装新 Skill，并以内置的 WorkBuddy 管控台（console.html）统一管理 Skill / 存储 / 对话。核心价值是**透明化**（看清 Agent 内部构造）、**积累性**（拆解与生成形成正向循环）、**可控性**（全自动组装 + 完整溯源，不黑盒）。

## 三、功能
- 零件库管理：6 大类 / 二级类组织，增删改查。
- 多轮需求澄清：覆盖目标 / 场景 / 输入 / 输出 / 流程 / 约束六维度。
- 自动检索匹配：中文二元语法 + 英文分词的关键词检索。
- 冲突检测：互斥零件二选一，跳过项写入说明。
- 依赖补全：自动补齐 `depends_on` 闭包。
- 组装生成：输出选用零件清单 + 组装说明 + 新 Skill 文件 + manifest。
- 自动拆解回填：新 Skill 生成后自动解析回零件库，闭环积累。
- 管控台可视化：一屏「Agent 全景驾驶舱」概览（KPI / 存储 / 健康 / 零件分类 / 人偶胶囊 / 可操作建议 / Token 排行 / 生命周期动作），以及 Skill 健康度 / 升级 / 删除、存储清理、历史对话检索，零件「模板库 / Skill生成记录 / 任务拆解」视图（平铺 + 折叠、悬停浮窗、详情页反向关联 + 同源伙伴）。

## 四、架构
纯文件 + 脚本，无服务、无数据库。agent 自身即引擎，脚本承担确定性机械工作。

```
<skill-root>/
├── SKILL.md
├── README.md
├── library/          # 零件库（数据永久保留，按 ASCII 子目录分 6 大类）
├── generations/      # 每次组装产物（manifest.json + SKILL.md）
├── tests/            # pytest 全量测试（工作坊 + 管控台 + 集成）
├── scripts/
│   ├── workshop.py           # 核心库
│   ├── scan_console.py       # 扫描 ~/.workbuddy，内联数据进 console.html
│   ├── server.py             # 管控台本地后端（端口 8080）
│   ├── generate_shop.py      # 【可选/遗留】渲染 shop.html 解剖图
│   ├── dismantle.py          # 解析 SKILL.md → 候选零件
│   ├── assemble.py           # 需求 → 选用零件（CLI）
│   └── seed_initial_parts.py # 种子零件
├── console.html      # 管控台前端（scan_console.py 注入数据后可用，可双击离线打开）
└── console_config.json # 本地配置（含 LLM/SkillHub Key，不入库）
```

**数据 / 视图解耦**：零件库与 generations/ 是唯一数据源；`console.html` 是管控台视图，由 `scan_console.py` 注入实时数据，重新生成不会丢失数据。`shop.html` 为早期解剖图视图，已并入控制台，默认不再生成。

## 五、流程
1. 初始化：`python scripts/seed_initial_parts.py <skill-root>`
2. 澄清需求：多轮对话产出需求文档 JSON。
3. 检索组装：`python scripts/assemble.py <skill-root> requirements.json`
4. 生成 Skill：撰写新 SKILL.md 并 `record_generation(...)` 落盘。
5. 自动回填：对新 Skill 跑 `dismantle.py`，审核后 `add_part`（`source_type=auto_generated`）。
6. 查看结果：重跑 `python scripts/scan_console.py` 并刷新管控台，在「Skill生成记录」板块查看本次组装与选用零件（默认不再生成 shop.html）。

> 🖥️ **调用本 Skill 的主路径是打开管控台**：运行 `python scripts/scan_console.py` 刷新数据 → 后台 `python scripts/server.py` 起后端 → 用 `present_files` 打开 `http://127.0.0.1:8080/console.html`。

## 六、使用场景
- 从已有 Skill / PDF / 代码库沉淀可复用零件。
- 凭模糊想法快速拼装新 Skill。
- 看清 Agent 由哪些零件构成、零件被谁使用、哪些零件同源。

## 七、使用示例
用户：「帮我做个把飞书和邮件周报汇总成 Markdown 的工具」

1. 多轮澄清得需求文档：
   ```json
   {"name":"周报汇总助手","scenario":"每周五汇总","inputs":"飞书+邮件","outputs":"Markdown","process":"读取合并","constraints":"本地"}
   ```
2. `assemble.py` 给出匹配零件清单 → 据此撰写新 SKILL.md → 落盘生成记录。
3. 自动拆解回填，新零件入库。
4. 重跑 `scan_console.py` 并刷新控制台：在「Skill生成记录」板块可见本次组装记录；「模板库」里「代码开发」类下「IMAP邮件读取模板」卡片标注「🔗 使用3次」，详情页可见「被以下 Skill 使用：周报汇总助手、邮件备份工具」及同源伙伴。

## 快速开始

以下是在 WorkBuddy 中使用「零件杂货铺」的真实对话示例：

---

**你：** 帮我做一个 Skill，能自动把飞书群消息和邮件周报汇总成一份 Markdown 周报。

**零件杂货铺：** 好的，我需要先澄清几个维度：

1. **目标**：这个 Skill 的核心输出是什么？
   **你：** 每周五自动生成一份 Markdown 周报，按「项目 / 进展 / 风险」分栏。

2. **输入来源**：数据从哪来？
   **你：** 飞书群消息（按 #周报 标签过滤）+ 邮件附件（含"周报"标题的）。

3. **约束条件**：有技术或安全限制吗？
   **你：** 必须纯本地运行，不能上传到外部服务器；飞书用 Open API，邮件用 IMAP。

4. **输出格式**：除了 Markdown 还要别的吗？
   **你：** 再同步发一条到钉钉群通知就行。

> ✅ 需求已收敛 → 自动检索零件库…

**零件杂货铺：** 从 6 大类 82 个零件中匹配到 **12 个**：

| 类别 | 选用零件 | 用途 |
|---|---|---|
| 需求分析 | 约束检查模板、目标定义框架 | 固化需求结构 |
| 设计 | 数据流设计、API选型评估 | 飞书+IMAP+钉钉三通道 |
| 代码开发 | IMAP邮件读取模板、飞书OpenAPI封装、Markdown生成器 | 核心逻辑 |
| 工具 | 定时任务调度器 | 每周五自动触发 |
| 参考 | 周报模板规范 | 输出格式 |

⚠️ **冲突检测**：「HTTP请求封装v1」与「HTTP请求封装v2」互斥 → 已自动选中 v2（更新版），跳过项已记录说明。
📦 **依赖补全**：自动追加「环境变量配置模板」（IMAP密码等敏感信息所需）。

---

**你：** 就按这些组装吧。

**零件杂货铺：** 已完成：

- ✅ 生成 `generations/gen_weekly_report/` — 含 SKILL.md + manifest.json
- ✅ 自动拆解回填 5 个新零件入库（周报解析器、钉钉Webhook通知等）
- ✅ 重跑 `scan_console.py` 并刷新控制台 — 在「Skill生成记录」即可看到新生成的 Skill 及其全部零件构成

```bash
# 以上全流程由 skill 自动驱动，无需手动执行命令
# 调用本 Skill 即在浏览器打开管控台（console.html）：
python scripts/scan_console.py && python scripts/server.py
# 如需单独重新生成早期解剖图快照（默认不再生成）：
python scripts/generate_shop.py .
```

---

> 💡 **核心体验**：你说需求 → 我问清楚 → 自动挑零件 → 组装出新 Skill → 拆解回填让零件库更富 → 下次组装选择更多。越用越强。

## 测试

项目自带 pytest 全量测试，覆盖零件工坊、管控台后端纯函数与端到端集成流程：

```bash
python3 -m pytest -v
```

主要测试文件：

- `tests/test_workshop.py`：零件加载、检索、冲突检测、依赖补全、反向关联。
- `tests/test_console.py`：`build_data` 快照结构、`server.py` 路径安全、版本比较。
- `tests/test_generate_shop.py`：shop.html 渲染与内嵌 JS 语法检查（依赖 node）。
- `tests/test_integration.py`：需求澄清 → 检索组装 → 落盘生成 → 拆解回填完整流程。
- `tests/test_seed.py`：初始种子零件写入。
- `tests/test_dismantle.py`：SKILL.md 解析为候选零件。

测试默认使用隔离的临时 WorkBuddy 家目录，不会扫描真实的 `~/.workbuddy`。如需在脚本中指定家目录，可设置环境变量：

```bash
WORKBUDDY_ROOT=/path/to/.workbuddy python scripts/scan_console.py
```

