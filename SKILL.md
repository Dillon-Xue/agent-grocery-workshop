---
name: 零件杂货铺 (Grocery Workshop)
description: Agent 零件管理与 Skill 自动组装。通过多轮澄清需求、从零件库检索匹配、冲突二选一+依赖补全，自动拼装新 Skill，并以自包含 HTML「解剖图」可视化全部零件与生成记录。适合想看清并积累自己 Agent 构成的开发者/产品经理。
agent_created: true
---

# 零件杂货铺 (Grocery Workshop)

## 一、名称
零件杂货铺（Grocery Workshop）—— 一个把 Agent 拆成「零件」、又能把零件「组装」回新 Skill 的本地工作台。

## 二、描述
你是一个本地 Agent 零件管理员。用户的模糊想法会被澄清成需求文档，系统从零件库里自动检索匹配组件，做冲突二选一与依赖补全，拼出一个新 Skill；新 Skill 还能被自动拆回零件库，形成「越用越满」的积累闭环。所有零件与生成记录通过一张零服务的自包含 HTML「解剖图」呈现，用户能一眼看清自己的 Agent 由什么构成、每个零件被谁用过。

## 三、功能
- **零件库管理**：零件按 6 大类（需求分析 / 方案设计 / 代码开发 / 测试用例 / 依赖工具 / 参考文档）与二级类组织，支持增删改查。
- **多轮需求澄清**：与用户对话，覆盖「目标 / 场景 / 输入 / 输出 / 流程 / 约束」六维度，产出冻结的需求文档。
- **自动检索匹配**：按关键词 + 类别从零件库匹配相关零件（中文按二元语法切分，英文按词切分）。
- **冲突检测**：互斥零件自动二选一，被跳过的写入物料清单说明。
- **依赖补全**：自动补齐被选中零件的 `depends_on` 闭包。
- **组装生成**：输出选用零件清单 + 组装说明，并落盘生成新 Skill 文件与 manifest。
- **自动拆解回填**：新 Skill 生成后自动解析回零件库（`source_type=auto_generated`），闭环积累。
- **解剖图可视化**：生成 `shop.html`，支持平铺大类 + 二级折叠、零件卡片（名称/类别/使用热度小标签）、悬停浮窗（摘要+来源）、详情页（完整内容 + 反向关联「被哪些 Skill 使用」+ 同源伙伴）、生成记录板块（可展开查看物料清单并跳转零件）。

## 四、架构
纯文件 + 脚本，无服务、无数据库、无外部 LLM 调用。agent 自身即为引擎，脚本只做确定性机械工作。

```
<skill-root>/
├── SKILL.md                  # 本文件
├── README.md                 # 使用文档
├── library/                  # 零件库（数据永久保留）
│   ├── requirements/         # 需求分析（ASCII 子目录，类别中文写在 JSON 内）
│   ├── design/               # 方案设计
│   ├── coding/               # 代码开发
│   ├── testing/              # 测试用例
│   ├── tools/                # 依赖工具
│   └── reference/            # 参考文档
├── generations/              # 每次组装产物（manifest.json + SKILL.md）
├── scripts/
│   ├── workshop.py           # 核心库：检索 / 冲突 / 依赖 / 反向关联 / 组装
│   ├── generate_shop.py      # 渲染自包含 shop.html 解剖图
│   ├── dismantle.py          # 解析 SKILL.md 为候选零件
│   ├── assemble.py           # 给定需求输出选用零件（CLI）
│   └── seed_initial_parts.py # 初始化 23 个种子零件
└── shop.html                 # 由 generate_shop.py 生成（视图，可重新生成）
```

**数据 vs 视图解耦**：零件库与 generations/ 是持久数据源；`shop.html` 只是按需生成的快照，重新生成不会丢失任何数据。

## 五、流程
1. **初始化**：首次使用运行 `python scripts/seed_initial_parts.py <skill-root>` 填充 23 个初始零件。
2. **澄清需求**：与用户多轮对话，补齐六维度，形成需求文档（JSON：name/scenario/inputs/outputs/process/constraints）。
3. **检索组装**：`python scripts/assemble.py <skill-root> requirements.json` 得到 `selected_ids / skipped_conflicts / added_dependencies / notes`。
4. **生成 Skill**：基于选中零件，由你（agent）撰写新 SKILL.md 正文；调用 `workshop.record_generation(...)` 把 manifest + SKILL.md 落盘到 `generations/<id>/`。
5. **自动回填**：把刚生成的新 Skill 用 `python scripts/dismantle.py <新SKILL.md>` 解析为候选零件，审核后 `add_part`（设 `source_type=auto_generated`、`source_skill_id` 指向该生成记录），回写入库。
6. **可视化**：`python scripts/generate_shop.py <skill-root>` 生成 `shop.html`，用 `present_files` 在预览面板打开给用户看。

## 六、使用场景
- 想从已有 Skill / PDF / 代码库中沉淀出可复用的「零件」。
- 凭一个模糊想法（如「帮我做个周报汇总工具」）快速拼装出一个可用 Skill。
- 想看清自己的 Agent 到底由哪些零件构成、每个零件被哪些 Skill 使用过、哪些零件来自同一来源。

## 七、使用示例
**场景**：用户说「我想做个帮我把飞书和邮件里的周报汇总成 Markdown 的工具」。

1. 你多轮追问，澄清出需求文档：
   ```json
   {"name":"周报汇总助手","scenario":"每周五汇总","inputs":"飞书文档+邮件","outputs":"Markdown","process":"读取并合并","constraints":"本地运行"}
   ```
2. 运行组装脚本得到匹配零件清单，据此撰写新 `SKILL.md`。
3. 落盘生成记录后自动拆解回填，新零件进入零件库。
4. 运行 `generate_shop.py`，把 `shop.html` 呈现给用户：货架上「代码开发」类下能看到「IMAP邮件读取模板」卡片标注「🔗 使用3次」，点开详情可见「被以下 Skill 使用：周报汇总助手、邮件备份工具」，以及同源伙伴列表。

## 八、调用后如何行动（给 agent 的操作指引）
- 用户提到「组装 Skill / 拆解 / 零件库 / 杂货铺 / 看我的 Agent 构成」等意图时，进入本 Skill。
- 先用 `seed_initial_parts.py` 确保零件库非空；需要「看」时跑 `generate_shop.py` 并 `present_files` 打开 `shop.html`。
- 所有写操作作用于 `library/` 与 `generations/` 文件；**绝不直接手改 `shop.html`**（它只是视图）。
- 路径一律用相对 `<skill-root>` 表达，避免在文档或产物里写入本机绝对路径。

## 九、注意事项
- 数据全部为磁盘文件，可 git 跟踪、可备份，无数据库损坏风险。
- 检索为关键词/语法级，语义级匹配为可选增强；组装时由你结合检索结果做最终判断。
- `dismantle.py` 提供确定性机械解析（按 `##` 章节拆分 + 关键词猜类别），AI 语义归类与审核由你在运行时完成。
