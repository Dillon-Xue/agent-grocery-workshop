---
name: JSON 格式化助手
description: 把用户输入的 JSON 字符串美化排版并校验语法
tags: 开发, 工具
agent_created: true
---

# JSON 格式化助手

把用户输入的 JSON 字符串美化排版并校验语法

## 功能
把用户输入的 JSON 字符串美化排版并校验语法

## 选用的零件
- **日期格式化模板**：datetime 统一处理
- **JSON处理模板**：JSON 序列化/反序列化
- **Pre-commit 钩子集**：.pre-commit-config.yaml：ruff 格式化、安全扫描、secret 检测
- **结构化日志初始化**：JSON 格式输出、上下文注入、采样率的 logging 配置
- **日志规范设计**：结构化日志格式、级别、采样率、脱敏规则的统一规范
- **环境差异检测**：dev/staging/prod 三套环境配置 diff 工具，防止配置漂移
- **requirements模板**：依赖清单格式
- **requests库调用模板**：带超时与重试的 HTTP 请求封装
- **Git Commit 规范**：Conventional Commits 格式 + commit-msg hook 自动校验
- **可观测性三支柱**：Metrics / Logs / Traces 统一采集与关联方案

## 用法
1. 在 WorkBuddy 中通过自然语言触发，或在对话框直接调用。
2. 按上方功能描述提供输入，Skill 返回处理结果。
