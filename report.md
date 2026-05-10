# 论文复现助手 — Agent 系统架构设计详解

## 一、系统概述

**论文复现助手**是一个基于多 LLM 提供商（DeepSeek / Zhipu AI）的对话式 AI Agent 系统。用户通过自然语言描述一篇论文或一个 GitHub 仓库，Agent 能够自主完成**搜索论文 → 查找源码 → 克隆仓库 → 配置环境 → 执行复现 → 生成报告**的全流程。

前端使用 **Chainlit** 构建对话界面，后端实现了一套完整的 **Planner → ReAct → Reflection → Memory** 四阶段 Agent 架构。

---

## 二、整体架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      chainlit_app.py (前端)                      │
│  意图分类 → 上下文增强 → Agent执行 → 流式输出 → 报告展示          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Orchestrator (核心引擎)                        │
│                                                                 │
│   run(goal) → 1.Plan → 2.Execute Loop → 3.Error Recovery → 4.Report  │
│                                                                 │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│   │ Planner  │  │  ReAct   │  │Reflection│  │  Memory  │       │
│   │ 任务分解  │  │ 推理执行  │  │ 错误反思  │  │ 双轨记忆  │       │
│   └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                           │                                     │
│               ┌───────────┴───────────┐                         │
│               │    Tool Registry      │                         │
│               │  (18个注册工具)        │                         │
│               └───────────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   app/core/ (基础设施层)                          │
│   Config (Pydantic配置) │ LLMInterface (API封装) │ Logging (日志) │
└─────────────────────────────────────────────────────────────────┘
```

### 分层架构

| 层次 | 目录 | 职责 |
|------|------|------|
| **表现层** | `app/chainlit_app.py` | 用户交互、流式展示、意图分类 |
| **编排层** | `app/agent/orchestrator.py` | Agent 主循环、步骤调度、状态管理 |
| **决策层** | `app/agent/planner.py`, `react.py`, `reflection.py` | 任务规划、推理执行、错误反思 |
| **记忆层** | `app/agent/memory.py` | 短期/长期记忆管理 |
| **工具层** | `app/tools/` | 18 个可调用工具 |
| **基础层** | `app/core/` | LLM 接口、配置、日志 |

---

## 三、Agent 核心循环（Orchestrator）

`Orchestrator.run(goal)` 是整个系统的主入口，约 910 行代码，实现了完整的 Agent 生命周期。

### 3.1 阶段一：规划（Planning）

```
用户输入目标 → Planner.create_plan(goal, context) → Plan {steps: [...]}
```

**Planner** 的策略分为三层，优先级依次递减：

**第一层：辅助意图检测** (`_detect_auxiliary_intent`)

对于非复现类的简单查询（如"查看报告""列出工作区""系统配置"），直接用正则匹配路由到对应的单一工具，完全不走 LLM，快速响应。目前支持 10+ 种意图模式：
- 报告管理：搜索/列出/查看/删除报告
- 工作区管理：列出仓库、检查仓库、清理仓库
- 系统信息：查看配置、统计信息

**第二层：关键词回退规划** (`_fallback_plan`)

对于明确的复现/部署意图，使用预定义的步骤模板，例如：
- `FULL_REPRODUCTION_PLAN`：search → fetch → source → clone → execute_session → report（6 步全流程）
- `REPRODUCTION_PLAN`：search → fetch → source → report（4 步，仅查找）
- `REPO_REPRODUCTION_PLAN`：search → clone → execute_session → report（有仓库 URL 时跳过 fetch）
- `EXECUTE_ONLY_PLAN`：execute_session → report（仅执行已有仓库）

**第三层：LLM 规划** (`_llm_plan`)

对于模糊意图，将完整的工具注册表作为 prompt 上下文发送给 LLM，由 LLM 生成 PlanStep 列表。

**设计要点：** Planner 为每个步骤绑定 `tool_hint`（指定具体工具名），后续 ReAct 引擎**无权更改工具选择**，只能填充工具参数。这个"计划锁定工具"的设计杜绝了 LLM 幻觉出不存在工具的风险。

### 3.2 阶段二：执行循环（Execute Loop）

```
while not terminated:
    step = plan.get_next_step()        # 获取待执行步骤
    react_step = react.decide(step)    # LLM 推理参数
    enrich_args(react_step)            # 确定性参数注入（反幻觉）
    observation = react.execute(react_step)  # 执行工具
    verify_step_completion(step, observation) # 验证步骤目标达成
```

**关键设计一：Args 富化（Anti-Hallucination）**

`_enrich_args()` 是防止 LLM 幻觉的关键环节。LLM 在推理参数时可能会"编造"URL、命令或路径，而 `_step_context` 字典保存了之前步骤的确定性输出：

```python
# 示例：LLM 幻觉出 github.com/ningyuanshao/SimCLR
# 但 source_tool 已经找到了正确的 github.com/google-research/simclr
# → _enrich_args 会用存储的 URL 覆盖 LLM 的参数
if stored_url and stored_url != llm_url:
    react_step.action_args["repo_url"] = stored_url
```

覆盖范围包括：
- `clone_tool`：source_tool 找到的 repo_url
- `run_tool`：plan_run_tool 规划的命令
- `execute_session_tool`：上一步确定的 repo_path
- `fetch_tool`：search_tool 返回的论文 URL

**关键设计二：步骤验证（Verification）**

工具返回成功 ≠ 步骤成功。`_verify_step_completion()` 对每类工具有专门的验证逻辑：

| 工具 | 验证方式 |
|------|---------|
| clone_tool | 检查磁盘上 `.git` 目录存在 |
| setup_tool | 检查 venv 创建成功 + pip 安装无致命错误 |
| search_tool | 检查返回了论文标题/作者/URL 等实质信息 |
| fetch_tool | 检查返回内容非空 |
| execute_session_tool | 检查输出含 `[SUCCESS]` 标记 |

### 3.3 阶段三：错误恢复（Error Recovery）

错误恢复采用**三级递进**策略，成本从低到高：

```
步骤失败
    │
    ├── ① ErrorHandler（快速确定性修复）
    │   ├── import_error → pip install 缺失模块
    │   ├── venv_failed → 重建虚拟环境
    │   ├── cmd_not_found → 搜索替代入口文件
    │   ├── pip_failed → 升级 pip + 去除版本锁
    │   └── auth_error → 嵌入 GITHUB_TOKEN
    │
    ├── ② Reflection（LLM 深度分析）
    │   ├── L1: 快速模式匹配分析（15+ 种错误模式）
    │   ├── L2: L1 + LLM 深度分析 + 修复建议
    │   └── L3: L2 + 结构级反思（是否触发重规划）
    │
    └── ③ Replan（结构级重规划）
        └── 保留已完成步骤，LLM 重新生成剩余步骤
```

**ErrorHandler 的跨工具修复许可**：`_allow_cross_tool_fix()` 定义了有效的工具切换白名单。例如，在执行时遇到 `import_error`，可以切回 `setup_tool` 重装依赖；但遇到 `parse_error`（LLM 调用失败），不应交给 ErrorHandler 而应交由 Reflection。

### 3.4 阶段四：收尾（Finalize）

所有步骤执行完毕后，自动调用 `ReportTool` 生成结构化报告，并通过 `_save_report()` 持久化到 `data/reports/report_YYYYMMDD_HHMMSS.json`。

---

## 四、状态机设计

`StateManager` 实现了严格的 Agent 生命周期状态机：

```
                    ┌──────────────┐
                    │     IDLE     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   PLANNING   │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────▼───┐  ┌─────▼──────┐  ┌─▼──────────┐
     │  EXECUTING │◄─┤ REFLECTING │  │   FAILED    │
     └──┬────┬────┘  └─────┬──────┘  └─────────────┘
        │    │              │
        │    └──────────────┤
        │                   │
   ┌────▼───────┐    ┌──────▼──────┐
   │  COMPLETED │    │ REPLANNING  │
   └────────────┘    └──────┬──────┘
                            │
                      回 PLANNING / EXECUTING
```

**状态转换规定**：
- `COMPLETED` 和 `FAILED` 是终态，不可再转换
- `EXECUTING` 可以自循环（多步骤连续执行）
- `REFLECTING` 可导向 `EXECUTING`（重试）、`REPLANNING`（重规划）或 `FAILED`
- 非法转换会被日志警告，但不会阻止（防御性宽松策略）

---

## 五、记忆系统（Memory）

采用**双轨记忆**架构，模拟人类的短期/长期记忆：

### 5.1 短期记忆（Short-term Memory）

```python
class Memory:
    short_term: List[StepRecord]   # 最多保留 10 条
```

- 记录最近 N 步的完整执行信息：thought → action → args → observation → status
- 作为 LLM prompt 的上下文注入（取最近 5 条），帮助 LLM 理解当前进度

### 5.2 长期记忆（Long-term Memory）

```python
class Memory:
    long_term: List[LongTermEntry]  # 持久化到 JSON
```

- 存储 `错误模式 → 修复策略` 的映射对
- 持久化到 `data/memory/long_term_memory.json`（当前有 29 条经验）
- 检索时使用关键词评分，返回 top_k 条最相关的经验
- `learn_from_error()` 会原地更新已有条目（增加 `success_count`）或创建新条目

### 5.3 Prompt 注入

`context_for_prompt()` 将近期步骤和长期经验拼接为文本，注入到后续 LLM 调用的 prompt 中：

```
历史记录（最近5步）:
- Step 2 [done] 克隆仓库 google-research/simclr → 路径: workspace/simclr
- Step 3 [failed] 执行复现 → 错误: ModuleNotFoundError: No module named 'tensorflow'

长期经验:
- [tensorflow 版本] 使用 pip install tensorflow==1.15.4 (成功率: 0/1)
```

---

## 六、ReAct 推理引擎

### 6.1 核心设计：工具锁定策略

传统的 ReAct 模式是 LLM 自由选择工具，但容易产生工具幻觉。本系统的关键改进是：

> **Planner 绑定工具 → ReAct 仅推理参数**

```python
def decide(self, goal, step, history, tools_desc, force_tool):
    # force_tool = step.tool_hint（由 Planner 设定，不可改变）
    # LLM 只需要填充 action_args
    prompt = self._build_decision_prompt(...)
    resp = self._llm.generate_structured(prompt)
    action = force_tool  # 强制使用计划指定的工具
    args = resp.get("action_args", {})
    if not args:
        args = self._default_args(step, action)  # 回退到确定性默认值
    return ReActStep(action=action, action_args=args)
```

### 6.2 多层回退机制

ReAct 引擎的参数推断有三层回退：

1. **LLM 生成**：主路径，由 LLM 推理参数
2. **`_default_args()`**：LLM 返回空参数时，根据工具类型从步骤描述中提取（如 `view_report_tool` 从描述中用正则提取 `report_id`）
3. **`_fallback_decide()`**：LLM 调用失败时，完全绕开 LLM，用关键词匹配确定参数

---

## 七、工具系统

### 7.1 工具注册机制

```python
# app/tools/__init__.py

TOOL_REGISTRY: Dict[str, BaseTool] = {}

class BaseTool(ABC):
    name: str          # 工具唯一标识，如 "search_tool"
    description: str   # 工具用途描述，会注入到 Planner/ReAct 的 prompt

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult: ...

    def _ok(self, output, **metadata) -> ToolResult: ...  # 成功结果
    def _fail(self, error, **metadata) -> ToolResult: ... # 失败结果

def register_tool(tool): ...
def get_tool(name) -> BaseTool: ...
def list_available_tools() -> Dict[str, str]: ...  # 返回 {name: description}
```

所有工具在模块导入时通过 `_build_registry()` 自动注册到 `TOOL_REGISTRY`。

### 7.2 工具全景图（18 个工具）

#### 核心复现工具（Active）

| 工具 | 作用 | 输入 |
|------|------|------|
| `search_tool` | 多源搜索论文（arXiv + LLM + Web + Wikipedia） | `query`, `source` |
| `fetch_tool` | 获取论文/网页全文（HTTP + trafilatura 提取） | `url`, `timeout` |
| `source_tool` | 从论文引用中查找官方仓库 URL | `paper_info`, `urls` |
| `clone_tool` | 克隆 Git 仓库到 workspace（多分支回退 + Token 认证） | `repo_url`, `branch` |
| `execute_session_tool` | **核心执行器**：多轮对话式 LLM 循环（建 venv → 装依赖 → 运行 → 诊断） | `repo_name`, `repo_path`, `max_rounds` |
| `error_handler_tool` | 确定性错误修复（安装缺失模块、重建 venv 等 8 种类型） | `error`, `error_type`, `repo_path` |
| `report_tool` | 生成最终汇总报告 | goal, plan, history |

#### 报告管理工具

| 工具 | 作用 | 输入 |
|------|------|------|
| `list_reports_tool` | 列出所有已保存的历史报告 | - |
| `view_report_tool` | 查看某份报告的完整内容 | `report_id` |
| `search_reports_tool` | 搜索历史报告（浅层 + 深层全文搜索） | `query` |
| `delete_report_tool` | 删除指定报告 | `report_id` |

#### 工作区管理工具

| 工具 | 作用 | 输入 |
|------|------|------|
| `list_workspace_tool` | 列出工作区所有克隆的仓库及其状态 | - |
| `check_repo_tool` | 深度检查仓库（git、venv、依赖、入口文件等） | `repo_name`, `repo_path` |
| `workspace_cleanup_tool` | 清理工作区（列举/删除指定/清空） | `repo_name`, `action` |

#### 系统信息工具

| 工具 | 作用 | 输入 |
|------|------|------|
| `config_tool` | 查看当前系统全部配置 | - |
| `stats_tool` | 查看运行统计数据（成功率、错误分析等） | - |

#### 已弃用工具（Planner prompt 中明确禁止使用）

`setup_tool`、`execute_tool`、`read_repo_tool`、`plan_run_tool`、`run_tool` — 被 `execute_session_tool` 替代。

### 7.3 execute_session_tool：核心执行器的设计

这是整个系统最重要的工具，采用**会话式 LLM 循环**替代传统的刚性流水线：

```
传统: setup → plan → execute (3个独立步骤，步骤间无法动态调整)
会话式: [LLM看环境] → [LLM提命令] → [执行] → [LLM看输出] → [LLM调整] → ... → [done]
```

**工作流程：**
1. **环境上下文收集**：读取 README、查找入口文件、检测框架类型、列出依赖文件
2. **构建系统 Prompt**：包含当前环境状态、Python 版本、venv 路径、可用命令等
3. **对话循环**（最多 15 轮）：
   - LLM 输出 JSON：`{"thought": "...", "action": "run", "command": "python train.py"}`
   - 执行命令，捕获 stdout/stderr/exit_code
   - 将输出反馈给 LLM
   - 检测到 `[SUCCESS]` 或 `[FAILED]` 标记时退出
4. **停滞检测**：如果连续 3 次同类命令失败，注入"反思提示"强制 LLM 改变策略
5. **自由格式解析**：当 LLM 不返回 JSON 时，用 5 种正则策略从原始文本中提取命令

---

## 八、LLM 接口设计

### 8.1 多提供商支持

`app/core/config.py` 实现多提供商自动检测：

```python
# 优先级链: DEEPSEEK_API_KEY > ZHIPU_API_KEY > LLM_API_KEY
provider = os.getenv("LLM_PROVIDER", "zhipu").lower()
api_key = (
    os.getenv("DEEPSEEK_API_KEY") or
    os.getenv("ZHIPU_API_KEY") or
    os.getenv("LLM_API_KEY")
)

# 每个提供商的默认配置
provider_defaults = {
    "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1/chat/completions"},
    "zhipu":    {"model": "glm-4-plus", "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions"},
}
```

### 8.2 重试与容错

`LLMInterface.generate()` 实现了 3 次指数退避重试：

| 尝试 | 超时 | 退避间隔 |
|------|------|---------|
| 第 1 次 | 120s | - |
| 第 2 次 | 180s | 10s |
| 第 3 次 | 300s | 20s |

HTTP 429/502/503/504 和连接错误触发重试，JSON 解析错误不重试（格式问题重试无意义）。

### 8.3 结构化输出解析

`generate_structured()` 使用 4 层 JSON 提取策略：
1. 直接 `json.loads` 解析
2. 从 ` ```json ` 代码块提取
3. 从任意 ` ``` ` 代码块提取
4. 花括号匹配提取（处理 LLM 在 JSON 前后加注释的情况）

---

## 九、前端设计（Chainlit）

### 9.1 意图分类

前端首先判断用户输入是"简单问答"还是"Agent 任务"：

```
输入消息 → 关键词匹配（27 个中英文模式）→ 匹配 → Agent 执行
                                              ↓
                                           未匹配 → LLM 二分类 → AGENT / QA
```

**Agent 关键词示例**：复现、运行、部署论文、reproduce、execute、run paper、run the code...

### 9.2 上下文增强

对于跟进的简略消息，自动补充上下文。例如：
- 用户之前找到了 `github.com/google-research/simclr`
- 用户说"克隆这个仓库" → 自动追加 `(已知URL: github.com/google-research/simclr)`

### 9.3 流式输出

Agent 在后台线程运行，通过 `asyncio.Queue` + `loop.call_soon_threadsafe` 桥接到 Chainlit 的异步事件循环：

```
Background Thread          Async Main Loop
     │                          │
     ├─ plan event ──► Queue ──► cl.Step 展示计划
     ├─ step_start ──► Queue ──► Step 名称实时更新
     ├─ react ───────► Queue ──► 展示推理过程
     ├─ observation ─► Queue ──► 展示执行结果 [OK]/[FAIL]
     ├─ reflection ──► Queue ──► 展示反思内容
     └─ done ────────► Queue ──► 发送最终报告
```

### 9.4 动态设置面板

用户可以在对话中切换 LLM 提供商和模型，无需重启：
- 提供商选择器（DeepSeek / Zhipu）
- 模型选择器（根据提供商动态更新列表）
- Agent 参数滑块（最大步数）
- 功能开关（Reflection、Memory）

---

## 十、核心设计模式总结

| 模式 | 应用位置 | 说明 |
|------|---------|------|
| **模块级单例** | `get_config()`, `get_llm()`, `get_report_store()` | 避免重复解析配置和初始化 API 客户端 |
| **策略模式** | `_analyze_pattern()` 15+ 种错误分类 | 不同错误类型触发不同的修复策略 |
| **责任链** | ErrorHandler → Reflection → Replan | 三级递进错误恢复，成本逐级增加 |
| **观察者/回调** | `on_step` / `on_log` / `on_round` 回调 | 解耦前端流式展示与后端引擎 |
| **异步桥接** | `asyncio.Queue` + `loop.call_soon_threadsafe` | 同步 Agent 线程 → 异步 Chainlit UI |
| **命令模式** | `BaseTool.execute(**kwargs) → ToolResult` | 统一的工具调用接口 |
| **注册表模式** | `TOOL_REGISTRY` + `register_tool()` | 运行时工具发现与动态调用 |
| **状态机模式** | `AgentState` + `VALID_TRANSITIONS` + `StateManager` | 约束 Agent 生命周期合法转换 |
| **模板方法** | `Orchestrator.run()` 四阶段流程 | 固定骨架、可插拔组件 |
| **上下文对象** | `_step_context` + `_enrich_args()` | 确定性数据传递，反 LLM 幻觉 |
| **白名单许可** | `_allow_cross_tool_fix()` | 仅许可特定的跨工具重试切换 |
| **双轨记忆** | 短期（内存） + 长期（JSON 持久化） | 模拟人类认知记忆架构 |
| **回退级联** | 关键词回退 → LLM 规划；4 层 JSON 解析 | AI 失败时的优雅降级 |
| **停滞检测** | `execute_session_tool` 连续失败计数 | 检测 LLM 陷入重试循环，注入反思 |

---

## 十一、数据流全景

```
用户: "复现 SimCLR 论文"
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ chainlit_app.py                                              │
│   1. 意图分类 → AGENT                                        │
│   2. 上下文增强 → goal = "复现 SimCLR 论文"                   │
│   3. 启动后台线程，创建 asyncio.Queue                         │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Orchestrator.run("复现 SimCLR 论文")                          │
│                                                              │
│ Phase 1 PLAN:                                                │
│   Planner.create_plan()                                      │
│   → 匹配 "复现" 关键词 → FULL_REPRODUCTION_PLAN              │
│   → [search, fetch, source, clone, execute_session, report]  │
│                                                              │
│ Phase 2 EXECUTE:                                             │
│   Step 1 search_tool("SimCLR")                               │
│     → arXiv 搜索 → LLM 补充 → 返回论文信息                   │
│     → _extract_result_info: 保存 paper_content               │
│                                                              │
│   Step 2 fetch_tool(paper_url)                               │
│     → HTTP GET → trafilatura 提取正文                        │
│                                                              │
│   Step 3 source_tool(paper_info)                             │
│     → 评分排序 → github.com/google-research/simclr           │
│     → _step_context["repo_url"] = "github.com/..."           │
│                                                              │
│   Step 4 clone_tool(repo_url)                                │
│     → _enrich_args: 使用 _step_context 的 URL（防幻觉）       │
│     → git clone → workspace/simclr                           │
│     → _verify_clone: 检查 .git 存在 ✓                        │
│                                                              │
│   Step 5 execute_session_tool("simclr")                      │
│     → 创建 venv → pip install → python main.py               │
│     → LLM 多轮对话: 执行 → 报错 → 诊断 → 修复 → 成功        │
│                                                              │
│   Step 6 report_tool → 汇总全部结果                           │
│                                                              │
│ Phase 4 FINALIZE:                                            │
│   → _save_report() → data/reports/report_20260510_120000.json│
│   → return AgentResult(success=True, ...)                    │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ chainlit_app.py (主线程收尾)                                  │
│   4. 发送 Markdown 总结报告                                   │
│   5. 发送完整报告细节                                         │
│   6. Step 状态设置为 DONE                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 十二、部署与运维

### Docker 部署

```
docker-compose.yml (单一服务 agent)
  ├── 基础镜像: ubuntu:22.04 + Python 3.11 + Python 3.7（兼容旧论文）
  ├── 端口映射: 8000:8000
  ├── 卷挂载:
  │   ├── ./logs → /app/logs
  │   ├── ./data/memory → /app/data/memory
  │   ├── ./data/reports → /app/data/reports
  │   └── ./workspace → /app/workspace
  └── 环境变量: 从 .env 文件注入
```

**重要提示**：Dockerfile 在构建时将代码 COPY 到镜像内，因此代码修改后需要 `docker-compose up --build` 重建镜像才能生效。

### 日志系统

使用 Loguru 库，双输出：
- **stderr**：可配置级别（默认 INFO），彩色输出
- **文件**：每天轮转，DEBUG 级别，保留 7 天，存储在 `logs/agent_YYYY-MM-DD.log`

---

## 十三、设计亮点与权衡

### 亮点

1. **反幻觉三层防护**：Planner 锁定工具名 → `_enrich_args` 覆盖参数 → `_verify_step_completion` 验证结果
2. **三级错误恢复**：低成本的确定性修复优先，高成本的 LLM 反思置后，最大化效率
3. **会话式执行器**：`execute_session_tool` 的 LLM 多轮对话循环，能像人类开发者一样看到错误 → 诊断 → 修复
4. **规划确定性优先**：关键词回退计划先于 LLM 计划，减少 LLM 规划的不确定性
5. **静态/动态配置分离**：Planner 在 LLM prompt 中声明工具清单，工具在 `__init__.py` 中注册即可被 Planner 发现

### 关键权衡

| 权衡点 | 决策 | 理由 |
|--------|------|------|
| Planner 模式 | 关键词优先于 LLM | 常见意图快速响应，减少 API 调用 |
| 工具选择权 | Planner 锁定，ReAct 不选工具 | 防止 LLM 幻觉出不存在的工具 |
| 错误恢复优先级 | 确定性修复 > LLM 反思 > 重规划 | 成本递增，先用便宜的方法 |
| 执行器设计 | 多轮 LLM 会话替代固定流水线 | 更灵活，但 LLM 调用成本更高 |
| 记忆持久化 | JSON 文件而非数据库 | 轻量级，部署简单，但查询能力有限 |
| 前端框架 | Chainlit（主）+ Streamlit（备） | Chainlit 流式体验更好，Streamlit 部署更简单 |

---

## 十四、扩展点与未来方向

1. **工具插件化**：目前工具在 `_build_registry()` 中硬编码注册，可改为基于文件发现或配置文件的插件机制
2. **长期记忆验证**：当前 29 条长期记忆中 `success_count` 均为 0（仅记录，未经验证），可实现经验效果追踪
3. **并行搜索**：`search_tool` 的多数据源可改为并行请求
4. **Docker Sandbox**：当前 execute_session_tool 在宿主机执行命令，可改为 Docker 容器隔离执行
5. **测试体系**：目前项目无测试，可为核心逻辑（Planner、ReAct、StateManager、ErrorHandler）添加单元测试
6. **多 Agent 协作**：可将搜索、执行、错误处理拆分为独立 Agent，通过消息总线通信
