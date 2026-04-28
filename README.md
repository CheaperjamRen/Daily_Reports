# Daily_Reports

每日 GitHub AI 高 Stars 项目自动日报系统。

## 功能概述

- 每天 **北京时间 12:00**（UTC 04:00）自动运行，无需人工干预
- 通过 GitHub Search API 爬取 AI / ML / 生成式 AI 等相关话题下 Stars 数超过 1000 的热门项目
- 与前一日追踪数据对比，自动分类：**重大更新**、**小幅增长**、**全新项目**
- 使用 **GitHub Copilot Free**（通过 GitHub Models API）对新项目和重大更新项目进行中文深度分析，**无需额外 API Key**
- 日报以 Markdown 格式存储于 `reports/` 目录；追踪表格保存于 `data/tracked_repos.csv`

## 日报结构

每份日报分为三部分：

| 部分 | 内容 |
|------|------|
| **一、已追踪项目动态** | 对前日已入库项目进行追踪；若 Stars 单日增长 ≥200 或增长率 ≥15% 则视为重大更新，附带深度分析 |
| **二、新发现高 Stars 项目深度解析** | 对首次发现的高 Stars 项目进行深度解读（读取 README），介绍项目是什么、用了哪些技术、有何价值 |
| **三、Stars 增长追踪（小幅更新）** | 以表格形式展示已追踪但无重大更新项目的 Stars 增长速度 |

## 快速配置

### 1. Fork 本仓库

点击右上角 **Fork** 按钮，将本仓库 fork 到你的 GitHub 账户下。

### 2. 确认已开启 GitHub Copilot Free

深度分析功能由 **GitHub Models**（GitHub Copilot 内置的模型推理服务）驱动，使用的是 `gpt-4o-mini` 模型。
工作流运行时自动获取的 `GITHUB_TOKEN` 即可调用该服务——**不需要任何额外的 API Key 或 Secret 配置**。

> 前提：仓库所有者账户已开启 [GitHub Copilot Free](https://github.com/features/copilot)（免费计划即可）。

### 3. 手动触发（可选）

前往 **Actions → Daily AI Projects Report**，点击 **Run workflow** 立即生成今日日报。

## 文件结构

```
Daily_Reports/
├── .github/
│   └── workflows/
│       └── daily_report.yml    # GitHub Actions 定时工作流
├── data/
│   └── tracked_repos.csv       # 项目追踪数据表（每日自动更新）
├── reports/
│   └── YYYY-MM-DD.md           # 每日日报
└── scripts/
    ├── fetch_repos.py          # 核心脚本：爬取、对比、生成报告
    └── requirements.txt        # Python 依赖
```

## 爬取范围

当前搜索话题标签（均要求 Stars > 1000）：

`llm` · `ai` · `artificial-intelligence` · `machine-learning` · `deep-learning` · `generative-ai` · `chatgpt` · `stable-diffusion` · `openai` · `neural-network` · `rag` · `agent`

如需修改搜索范围或阈值，编辑 `scripts/fetch_repos.py` 顶部的配置常量即可。