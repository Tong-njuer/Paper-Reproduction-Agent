# 论文复现助手 — 文档索引

## 项目概述

一个基于 LLM 的论文复现代理系统，支持自动搜索论文、克隆代码、配置环境、复现实验。

## 文档列表

| 文档                                                         | 说明                  |
| ------------------------------------------------------------ | --------------------- |
| [README](../README.md)                                       | 项目概述与快速开始    |
| [chainlit.md](chainlit.md)                                   | Chainlit 界面配置说明 |
| [engineering_issues_report.md](engineering_issues_report.md) | 工程问题记录          |
| [anti-ai-generated.md](anti-ai-generated.md)                 | 反 AI 生成内容声明    |

## 目录结构

```index
agent/
├── app/                    # 主应用代码
│   ├── agent/              # Agent 核心模块
│   │   ├── orchestrator.py # 编排器（执行计划）
│   │   ├── planner.py      # 规划器（生成计划）
│   │   ├── react.py        # ReAct 决策引擎
│   │   ├── reflection.py   # 反思模块
│   │   ├── memory.py       # 记忆模块
│   │   ├── intent_classifier.py  # 意图分类
│   │   ├── state.py        # 状态管理
│   │   └── result.py       # 执行结果模型
│   ├── tools/              # 工具集
│   │   ├── search_tool.py  # 论文搜索
│   │   ├── fetch_tool.py   # 论文获取
│   │   ├── source_tool.py  # 源码查找
│   │   ├── clone_tool.py   # 仓库克隆
│   │   ├── python_env_tool.py  # Python 环境配置
│   │   ├── execute_session_tool.py  # 会话式执行
│   │   ├── ... (更多工具)
│   │   ├── report_tool.py  # 报告生成
│   │   └── report_store.py # 报告存储
│   ├── core/               # 核心基础设施
│   │   ├── config.py       # 配置管理
│   │   ├── llm.py          # LLM 接口
│   │   └── logging.py      # 日志
│   ├── chainlit_app.py     # Chainlit 前端入口
│   ├── chainlit_helpers.py # 前端辅助函数
│   └── __init__.py
├── docs/                   # 文档
├── data/                   # 数据
│   ├── memory/             # 长期记忆
│   └── reports/            # 执行报告
├── logs/                   # 日志
├── workspace/              # 工作区（克隆的仓库）
├── tests/                  # 测试
├── Dockerfile              # 构建镜像
└── docker-compose.yml      # 运行编排
```
