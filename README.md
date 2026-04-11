# 编程教练 Agent

一个 AI 驱动的编程学习助手，基于 ReAct Agent 架构，帮助用户通过对话学习编程。

## 核心功能

- **对话问答** — 随时提问，AI 实时解答
- **代码出题与评测** — 自动生成题目，自动评测代码并给出改进建议
- **Wiki 知识库** — RAG 语义检索，AI 自动整理学习资料
- **学习路径规划** — 制定并执行完整的学习计划
- **日程管理** — 安排学习时间和进度
- **能力画像** — 记录用户的知识点掌握程度，智能推荐学习内容

## 技术架构

### Agent 模式

采用 **ReAct (Reasoning + Acting)** 模式：

```
用户输入 → Thought（思考）→ Action（行动）→ Observation（观察）→ ... → Final Answer
```

Agent 配备多个工具（Tools），根据用户问题自动选择调用：

| 工具 | 功能 |
|------|------|
| 日程管理 | 创建、查看、修改、删除学习日程 |
| Wiki 知识库 | 创建知识条目、语义搜索 |
| 代码出题 | 根据需求生成练习题 |
| 代码评测 | 评测用户提交的代码，分析错误类型、复杂度、代码风格 |
| 学习路径 | 创建多步骤学习路径，支持断点续学 |
| 一键学习计划 | 输入需求，自动生成完整学习计划（日程+Wiki+题目+路径） |

### 代码

```
app/
├── agent/
│   ├── agent.py       # ReAct Agent 核心
│   ├── planner.py      # Plan+Execute 规划器（生成学习计划）
│   └── prompt.py       # System Prompt
├── tools/
│   ├── code_tool.py    # 代码出题、评测、用户能力画像
│   ├── wiki_tool.py    # Wiki + RAG 语义检索
│   ├── schedule_tool.py # 日程管理
│   ├── learning_path_tool.py  # 学习路径管理
│   └── plan_and_execute_tool.py  # 一键学习计划入口
├── db/
│   ├── models.py       # SQLAlchemy 模型
│   └── database.py     # 数据库连接
└── core/
    ├── config.py       # 配置（API Key 等）
    ├── auth.py         # 用户认证
    └── context.py      # 用户上下文（线程本地）
```

## 快速开始

### 环境要求

- Python 3.11+
- Zhipu API Key

### 安装

```bash
pip install -r requirements.txt
```

### 配置

创建 `.env` 文件：

```
ZHIPU_API_KEY=your_api_key_here
```

### 运行

**Streamlit Web 界面：**

```bash
streamlit run streamlit_app.py
```

**CLI 模式（使用默认用户）：**

```bash
python -m app.main
```

**Docker 部署：**

```bash
docker-compose up
```

## 用户交互示例

### 对话问答

```
你: 什么是指针？
Agent: 关于 C++ 指针，...
```

### 出题与评测

```
你:出一道链表的题目
Agent: 题目已创建，文件在 workspace/user_1/problem_1.md

你: 提交第1题答案
Agent: 【评测结果】
      ✅ 通过
      📊 复杂度: O(n)
      💡 代码风格得分: 75/100
      【改进建议】...
```

### 一键学习计划

```
你: 帮我创建一个Python学习计划
Agent: 自动创建日程、Wiki、题目、学习路径
      📅 已创建 4 个日程
      📖 已创建 4 篇 Wiki
      💻 已创建 4 道练习题
      🗺️ 学习路径已创建
```

## 数据库

SQLite 数据库（`schedule.db`），包含以下表：

- `users` — 用户账户
- `schedules` — 日程安排
- `wiki` / `wiki_vectors` — 知识库（支持向量检索）
- `code_problems` — 代码题目
- `user_code_answers` — 用户提交记录
- `user_abilities` — 用户能力画像
- `learning_paths` / `path_steps` / `user_path_progress` — 学习路径

## 未来计划

- **前端重构** — FastAPI + React 全新前端（详见上方前端开发指南）
- **自治 Agent 模式** — 在现有 Agentic Workflow 基础上，新增一键执行复杂任务的 Autonomous 模式
