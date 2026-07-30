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
- ✅ 生成 `shop.html` 解剖图 — 打开即可看到新生成的 Skill 及其全部零件构成

```bash
# 以上全流程由 skill 自动驱动，无需手动执行命令
# 如需单独重新生成解剖图：
python scripts/generate_shop.py .
```

---

> 💡 **核心体验**：你说需求 → 我问清楚 → 自动挑零件 → 组装出新 Skill → 拆解回填让零件库更富 → 下次组装选择更多。越用越强。

