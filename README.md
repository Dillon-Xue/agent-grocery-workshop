# 零件杂货铺 (Grocery Workshop)

> 一个把 Agent 拆成「零件」、又能把零件「组装」回新 Skill 的本地工作台。零服务、零数据库，零件库越用越满。

## 一、名称
零件杂货铺（Grocery Workshop）

## 二、描述
通过多轮澄清需求、从零件库检索匹配、冲突二选一 + 依赖补全，自动拼装新 Skill，并以一张自包含 HTML「解剖图」可视化全部零件与生成记录。核心价值是**透明化**（看清 Agent 内部构造）、**积累性**（拆解与生成形成正向循环）、**可控性**（全自动组装 + 完整溯源，不黑盒）。

## 三、功能
- 零件库管理：6 大类 / 二级类组织，增删改查。
- 多轮需求澄清：覆盖目标 / 场景 / 输入 / 输出 / 流程 / 约束六维度。
- 自动检索匹配：中文二元语法 + 英文分词的关键词检索。
- 冲突检测：互斥零件二选一，跳过项写入说明。
- 依赖补全：自动补齐 `depends_on` 闭包。
- 组装生成：输出选用零件清单 + 组装说明 + 新 Skill 文件 + manifest。
- 自动拆解回填：新 Skill 生成后自动解析回零件库，闭环积累。
- 解剖图可视化：平铺 + 折叠、悬停浮窗、详情页（反向关联 + 同源伙伴）、生成记录板块。

## 四、架构
纯文件 + 脚本，无服务、无数据库。agent 自身即引擎，脚本承担确定性机械工作。

```
<skill-root>/
├── SKILL.md
├── README.md
├── library/          # 零件库（数据永久保留，按 ASCII 子目录分 6 大类）
├── generations/      # 每次组装产物（manifest.json + SKILL.md）
├── scripts/
│   ├── workshop.py           # 核心库
│   ├── generate_shop.py      # 渲染 shop.html
│   ├── dismantle.py          # 解析 SKILL.md → 候选零件
│   ├── assemble.py           # 需求 → 选用零件（CLI）
│   └── seed_initial_parts.py # 23 个种子零件
└── shop.html         # 由脚本生成（视图，可重新生成）
```

**数据 / 视图解耦**：零件库与 generations/ 是唯一数据源；`shop.html` 只是按需生成的快照，重新生成不会丢失数据。

## 五、流程
1. 初始化：`python scripts/seed_initial_parts.py <skill-root>`
2. 澄清需求：多轮对话产出需求文档 JSON。
3. 检索组装：`python scripts/assemble.py <skill-root> requirements.json`
4. 生成 Skill：撰写新 SKILL.md 并 `record_generation(...)` 落盘。
5. 自动回填：对新 Skill 跑 `dismantle.py`，审核后 `add_part`（`source_type=auto_generated`）。
6. 可视化：`python scripts/generate_shop.py <skill-root>` → 用预览面板打开 `shop.html`。

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
4. `generate_shop.py` 生成 `shop.html`：货架上「代码开发」类下「IMAP邮件读取模板」卡片标注「🔗 使用3次」，详情页可见「被以下 Skill 使用：周报汇总助手、邮件备份工具」及同源伙伴。

## 快速开始
```bash
# 1. 初始化零件库
python scripts/seed_initial_parts.py .

# 2. 把模糊需求写成 requirements.json 后组装
python scripts/assemble.py . requirements.json

# 3. 生成解剖图并在浏览器/预览面板打开
python scripts/generate_shop.py .
```

## 测试
核心逻辑（检索 / 冲突 / 依赖 / 反向关联 / 同源 / 渲染 / 拆解 / 种子）均覆盖自动化测试，运行：
```bash
python -m pytest tests -q
```

## 目录约定
- 类别中文写在每个零件 JSON 的 `category` 字段；磁盘子目录用 ASCII（requirements/design/coding/testing/tools/reference）以避免跨平台编码问题。
- 零件 JSON 字段：`id / name / description / category / sub_category / type / content / content_format / version / source_type / source_skill_id / source_skill_name / metadata / depends_on / conflicts_with`。
