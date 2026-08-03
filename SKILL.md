---
name: 零件杂货铺 (Grocery Workshop)
description: Agent 零件管理与 Skill 自动组装，并内置 WorkBuddy 管控台（console.html）。安装后调用即可在浏览器打开统一控制台，管理已装 Skill（健康度 / 升级 / 删除）、存储空间、历史对话与设置；同时保留零件库检索、冲突二选一、依赖补全、自动拼装 Skill 的能力，拼装记录直接在控制台「Skill生成记录」中查看。
agent_created: true
---

# 零件杂货铺 (Grocery Workshop)

## 一、名称
零件杂货铺（Grocery Workshop）—— 一个把 Agent 拆成「零件」、又能把零件「组装」回新 Skill 的本地工作台；并内置一张零依赖的 WorkBuddy 管控台（console.html），安装即可用。

## 二、描述
你是一个本地 Agent 零件管理员，同时是用户 WorkBuddy 环境的「控制台」。两件事一体：

1. **管控台（主交付物）**：安装并调用本 Skill 后，直接在浏览器打开 `console.html`，统一管理已装 Skill（健康度 / 升级 / 删除 / 使用频率）、存储空间（日志 / 会话 / 缓存明细与清理）、历史对话（按项目 / 时间浏览 + 全文检索）、以及设置（主题 / 环境 / LLM / SkillHub）。
2. **零件工坊（引擎）**：用户的模糊想法被澄清成需求文档，系统从零件库检索匹配组件，做冲突二选一与依赖补全，拼出新 Skill；新 Skill 还能被自动拆回零件库，形成「越用越满」的积累闭环。拼装记录直接进入控制台的「Skill生成记录」板块，无需另开文件。

所有零件与生成记录通过管控台的「模板库 / Skill生成记录 / 任务拆解」视图呈现，用户一眼看清自己的 Agent 由什么构成、每个零件被谁用过。

## 三、功能
- **管控台（核心交付）**：
  - Skill 管理：健康度、使用频率、一键升级（连 SkillHub 校验版本）、页面内安全删除（强制备份 + AI 总结 + 回收站可恢复）。
  - 存储空间：日志 / 会话 / 缓存 占用明细、风险分级、一键清理（同样走备份 + 回收站）。
  - 对话：按项目 / 时间倒序浏览历史会话 + 全文检索融合在同一页。
  - 设置：外观 / 后端 / 开发环境 / LLM / SkillHub 配置。
- **零件库管理**：零件按 6 大类（需求分析 / 方案设计 / 代码开发 / 测试用例 / 依赖工具 / 参考文档）与二级类组织，支持增删改查。
- **多轮需求澄清**：与用户对话，覆盖「目标 / 场景 / 输入 / 输出 / 流程 / 约束」六维度，产出冻结的需求文档。
- **自动检索匹配**：按关键词 + 类别从零件库匹配相关零件（中文按二元语法切分，英文按词切分）。
- **冲突检测**：互斥零件自动二选一，被跳过的写入物料清单说明。
- **依赖补全**：自动补齐被选中零件的 `depends_on` 闭包。
- **组装生成**：输出选用零件清单 + 组装说明，并落盘生成新 Skill 文件与 manifest。
- **自动拆解回填**：新 Skill 生成后自动解析回零件库（`source_type=auto_generated`），闭环积累。

## 四、架构
纯文件 + 脚本。管控台由前端 `console.html` + 本地后端 `server.py` 组成；零件工坊由 `workshop.py` 等确定性脚本驱动。

```
<skill-root>/
├── SKILL.md                  # 本文件
├── README.md                 # 使用文档
├── library/                  # 零件库（数据永久保留）
│   ├── requirements/         # 需求分析
│   ├── design/               # 方案设计
│   ├── coding/               # 代码开发
│   ├── testing/              # 测试用例
│   ├── tools/                # 依赖工具
│   └── reference/            # 参考文档
├── generations/              # 每次组装产物（manifest.json + SKILL.md）
├── assets/
│   └── sprite_avatar.png     # 控制台头像
├── scripts/
│   ├── workshop.py           # 核心库：检索 / 冲突 / 依赖 / 反向关联 / 组装
│   ├── dismantle.py          # 解析 SKILL.md 为候选零件
│   ├── assemble.py           # 给定需求输出选用零件（CLI）
│   ├── seed_initial_parts.py # 初始化种子零件
│   ├── scan_console.py       # 扫描 ~/.workbuddy，内联数据进 console.html
│   ├── server.py             # 管控台本地后端（端口 8080）
│   └── generate_shop.py      # 【可选/遗留】渲染 shop.html 解剖图（默认不再生成）
├── console.html              # 管控台前端（scan_console.py 注入数据后可用，可双击离线打开）
└── console_config.json       # 本地配置（含 LLM/SkillHub Key，不入库）
```

**数据 vs 视图解耦**：零件库与 generations/ 是持久数据源；`console.html` 是管控台视图，由 `scan_console.py` 注入实时数据，重新生成不会丢失任何数据。`shop.html` 为早期解剖图视图，功能已并入控制台「模板库 / 生成记录」，**默认不再生成**。

## 五、流程

### A. 启动管控台（调用本 Skill 的主路径）
1. **刷新数据**：`python scripts/scan_console.py` —— 扫描 `~/.workbuddy`，把 Skill / 存储 / 对话等最新数据内联进 `console.html`（使其可离线双击，也为后端提供快照）。
2. **起后端**：`python scripts/server.py`（后台运行，监听 8080）。
3. **呈现给用户**：用 `present_files` 打开 `http://127.0.0.1:8080/console.html`（功能最全）；也可直接打开 `console.html` 文件（离线、数据已内联，但对话详情 / 升级校验 / 打开 WorkBuddy 等需后端的功能会受限）。
4. 告知用户：之后刷新浏览器即可，数据已持久化；需要重启后端时重跑第 2 步。

### B. 零件组装（按需使用）
1. **初始化**：首次使用运行 `python scripts/seed_initial_parts.py <skill-root>` 填充初始零件。
2. **澄清需求**：与用户多轮对话，补齐六维度，形成需求文档（JSON：name/scenario/inputs/outputs/process/constraints）。
3. **检索组装**：`python scripts/assemble.py <skill-root> requirements.json` 得到 `selected_ids / skipped_conflicts / added_dependencies / notes`。
4. **生成 Skill**：基于选中零件，由你（agent）撰写新 SKILL.md 正文；调用 `workshop.record_generation(...)` 把 manifest + SKILL.md 落盘到 `generations/<id>/`。
5. **自动回填**：把刚生成的新 Skill 用 `python scripts/dismantle.py <新SKILL.md>` 解析为候选零件，审核后 `add_part`（设 `source_type=auto_generated`、`source_skill_id` 指向该生成记录），回写入库。
6. **查看结果**：重跑 `scan_console.py` + 刷新控制台，在「Skill生成记录」板块即可看到本次组装记录与选用零件（**不再生成 shop.html**）。

## 六、使用场景
- 想统一管理 / 清理 WorkBuddy 的 Skill、存储、历史对话 —— 直接调用本 Skill 打开控制台。
- 想从已有 Skill / PDF / 代码库中沉淀出可复用的「零件」。
- 凭一个模糊想法（如「帮我做个周报汇总工具」）快速拼装出一个可用 Skill。
- 想看清自己的 Agent 到底由哪些零件构成、每个零件被哪些 Skill 使用过、哪些零件来自同一来源（在控制台「模板库」查看）。

## 七、使用示例
**场景 1：用户说「打开控制台 / 管理一下我的 Skill」**
1. 运行 `python scripts/scan_console.py` 刷新数据。
2. 后台启动 `python scripts/server.py`。
3. `present_files` 打开 `http://127.0.0.1:8080/console.html`，用户在浏览器里管理 Skill / 存储 / 对话。

**场景 2：用户说「我想做个帮我把飞书和邮件里的周报汇总成 Markdown 的工具」**
1. 多轮追问，澄清出需求文档。
2. 运行组装脚本得到匹配零件清单，据此撰写新 `SKILL.md`。
3. 落盘生成记录后自动拆解回填，新零件进入零件库。
4. 重跑 `scan_console.py` 并刷新控制台，在「Skill生成记录」中看到新记录与选用零件（货架上「代码开发」类可见「IMAP邮件读取模板」标注「🔗 使用3次」，详情页可见「被以下 Skill 使用：周报汇总助手」）。

## 八、调用后如何行动（给 agent 的操作指引）
- 用户提到「打开控制台 / 管理 Skill / 清理存储 / 看对话 / 零件库 / 杂货铺 / 看我的 Agent 构成」等意图时，进入本 Skill。
- **默认动作**：按「流程 A」启动管控台并 `present_files` 打开 `console.html`。这是本 Skill 的主交付物。
- 仅当用户明确要「组装 / 拆解」Skill 时，走「流程 B」，最终在控制台查看结果，不生成 shop.html。
- 所有写操作作用于 `library/` 与 `generations/` 文件；**绝不直接手改 `console.html`**（它由 `scan_console.py` 注入数据）。
- 路径一律用相对 `<skill-root>` 表达，避免在文档或产物里写入本机绝对路径。

## 九、注意事项
- 管控台数据全部来自磁盘扫描，可 git 跟踪、可备份，无数据库损坏风险。
- 检索为关键词/语法级，语义级匹配为可选增强；组装时由你结合检索结果做最终判断。
- `dismantle.py` 提供确定性机械解析（按 `##` 章节拆分 + 关键词猜类别），AI 语义归类与审核由你在运行时完成。
- `shop.html` / `generate_shop.py` 为早期解剖图方案，已并入控制台视图，**默认不再使用**；仅在需要离线解剖图快照时可手动 `python scripts/generate_shop.py <skill-root>` 生成。
