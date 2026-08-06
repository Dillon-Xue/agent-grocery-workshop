---
name: 代码注释生成器
description: 为给定的 Python 函数生成中文 docstring 注释
tags: 开发, Python
agent_created: true
---

# 代码注释生成器

为给定的 Python 函数生成中文 docstring 注释

## 功能
为给定的 Python 函数生成中文 docstring 注释

## 选用的零件
- **契约测试生成器**：根据 OpenAPI Spec 自动生成 Provider/Consumer 契约测试用例
- **单元测试 fixtures 工厂**：pytest fixture 工厂：Mock DB、Fake HTTP、临时文件的通用生成器
- **测试数据工厂**：Faker 集成的批量假数据生成器（用户/订单/商品）
- **性能调优手册**：CPU/内存/IO/IOPS 瓶颈定位与优化策略
- **测试数据构造模板**：模拟数据生成
- **Secret 轮换脚本**：定期更换 API Key / DB Password 并更新各环境配置的安全工具
- **环境差异检测**：dev/staging/prod 三套环境配置 diff 工具，防止配置漂移
- **Ruff Lint 配置**：统一代码风格：行长度、导入排序、命名规范的 ruff.toml
- **健康检查端点**：/healthz /readyz /livez 三级探针实现（依赖检查 + 就绪判断）
- **Prometheus 指标导出**：自定义 Counter/Histogram/Summary 指标注册与 /metrics 端点

## 用法
1. 在 WorkBuddy 中通过自然语言触发，或在对话框直接调用。
2. 按上方功能描述提供输入，Skill 返回处理结果。
