# ============================================================
# 编程教练 Agent 系统 - 架构设计文档
# ============================================================
#
# 本文档详细描述了"编程教练 Agent 系统"的整体架构设计，
# 包括核心模块职责、数据结构、推理流程等。
#
# ============================================================

## 1. 项目整体架构说明

### 1.1 系统定位

本系统是一个**多模式编程教练 Agent**，旨在帮助用户提升编程能力。
不同于简单的代码问答工具，本系统具备：
- **主动规划能力**：根据用户水平制定训练计划
- **多轮推理**：通过 ReAct/Reflexion 实现复杂问题解决
- **工具调用**：执行代码、分析错误、生成测试
- **自我反思**：从失败中学习并调整策略
- **用户建模**：理解用户水平，个性化教学

### 1.2 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                        UI 层                                 │
│                   (Gradio / Web UI)                          │
├─────────────────────────────────────────────────────────────┤
│                     API 层                                   │
│                  (FastAPI Controller)                        │
├─────────────────────────────────────────────────────────────┤
│                   Service 层                                 │
│              (Agent Service + Log Service)                  │
├─────────────────────────────────────────────────────────────┤
│                    Agent 层                                  │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐         │
│  │ Planner │ │ Executor│ │ Evaluator│ │ Reflector│         │
│  └─────────┘ └─────────┘ └──────────┘ └──────────┘         │
│  ┌─────────────────────────────────────────────────┐        │
│  │              Reasoning Engine                    │        │
│  │        (ReAct / Reflexion / ToT)                │        │
│  └─────────────────────────────────────────────────┘        │
│  ┌─────────────────────────────────────────────────┐        │
│  │              Mode Manager                        │        │
│  │  (Algorithm/Design/Project/Refactor/Learning)  │        │
│  └─────────────────────────────────────────────────┘        │
├─────────────────────────────────────────────────────────────┤
│                    Tool 层                                   │
│  ┌─────────────────────────────────────────────────┐        │
│  │              Tool Registry                       │        │
│  │  run_code | generate_tests | analyze_error ...  │        │
│  └─────────────────────────────────────────────────┘        │
├─────────────────────────────────────────────────────────────┤
│                  Execution 层                               │
│              (Docker Sandbox Runner)                        │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 核心设计原则

1. **模块解耦**：Agent各组件独立，便于单独测试和扩展
2. **可追溯性**：每一步推理都记录在Trace中，支持可视化
3. **插件式工具**：工具通过Registry统一管理，可动态添加
4. **多模式支持**：不同训练场景使用不同策略
5. **扩展优先**：保留充足的扩展空间

---

## 2. 目录结构

```
programming-coach-agent/
│
├── agent/                          # Agent核心模块
│   ├── __init__.py
│   ├── base.py                    # Agent基类，定义通用接口
│   ├── planner.py                 # Planner：训练计划制定
│   ├── executor.py                # Executor：执行任务
│   ├── evaluator.py               # Evaluator：评估结果
│   ├── reflector.py               # Reflector：反思与调整
│   ├── user_model.py              # UserModel：用户画像
│   │
│   ├── reasoning/                 # 推理机制实现
│   │   ├── __init__.py
│   │   ├── base.py               # 推理基类
│   │   ├── react.py              # ReAct推理
│   │   ├── reflexion.py          # Reflexion推理
│   │   └── registry.py           # 推理机制注册器
│   │
│   └── modes/                     # 多模式支持
│       ├── __init__.py
│       ├── base.py               # 模式基类
│       ├── algorithm_mode.py     # 算法训练模式
│       ├── design_mode.py        # 设计训练模式
│       ├── project_mode.py        # 项目引导模式
│       ├── refactor_mode.py      # 重构模式
│       └── learning_path_mode.py # 学习路径模式
│
├── tools/                          # 工具系统
│   ├── __init__.py
│   ├── base.py                    # Tool基类定义
│   ├── registry.py                # 工具注册器
│   ├── result.py                  # 工具执行结果
│   │
│   ├── impl/                      # 工具具体实现
│   │   ├── __init__.py
│   │   ├── run_code.py           # 代码执行工具
│   │   ├── generate_tests.py     # 测试生成工具
│   │   ├── analyze_error.py      # 错误分析工具
│   │   ├── code_linter.py        # 代码检查工具
│   │   ├── design_analyzer.py     # OOP分析工具
│   │   └── project_planner.py     # 项目拆解工具
│   │
│   └── prompts/                   # 工具相关提示词
│       ├── run_code_prompt.py
│       └── ...
│
├── execution/                      # 执行环境
│   ├── __init__.py
│   ├── base.py                    # 执行器基类
│   ├── docker_runner.py           # Docker隔离执行
│   └── pool.py                    # 容器池管理
│
├── service/                        # 服务层
│   ├── __init__.py
│   ├── agent_service.py           # Agent服务
│   ├── trace_service.py           # Trace记录服务
│   └── user_service.py            # 用户管理服务
│
├── controller/                     # 控制器层
│   ├── __init__.py
│   └── agent_controller.py        # API端点
│
├── dto/                            # 数据传输对象
│   ├── __init__.py
│   ├── request.py                 # 请求DTO
│   ├── response.py                # 响应DTO
│   └── trace.py                   # Trace相关DTO
│
├── logs/                           # 日志与追踪
│   ├── __init__.py
│   └── trace_logger.py            # Trace记录器
│
├── ui/                             # 前端
│   ├── __init__.py
│   ├── gradio_app.py              # Gradio界面
│   └── static/                    # 静态资源
│
├── tests/                          # 测试
│   ├── __init__.py
│   ├── test_agent/
│   ├── test_tools/
│   └── test_modes/
│
├── config.py                       # 配置管理
├── main.py                         # 入口文件
├── requirements.txt
├── .env.example
└── docker-compose.yml
```

---

## 3. 核心模块说明

### 3.1 agent/ 模块

#### 3.1.1 base.py - Agent基类
所有Agent的基类，定义通用接口：
- `plan()`: 制定计划
- `execute()`: 执行任务
- `evaluate()`: 评估结果
- `reflect()`: 反思调整

#### 3.1.2 planner.py - Planner
职责：制定训练计划
- 分析用户当前水平
- 生成个性化训练计划
- 拆解大目标为小步骤

#### 3.1.3 executor.py - Executor
职责：执行具体任务
- 调用工具执行代码
- 管理执行状态
- 处理执行结果

#### 3.1.4 evaluator.py - Evaluator
职责：评估执行结果
- 验证代码正确性
- 评估代码质量
- 检查是否符合要求

#### 3.1.5 reflector.py - Reflector
职责：反思与策略调整
- 分析失败原因
- 总结经验教训
- 调整后续策略

#### 3.1.6 user_model.py - UserModel
职责：用户画像管理
- 记录用户技能水平
- 跟踪学习进度
- 偏好设置管理

### 3.2 reasoning/ 模块

#### 3.2.1 react.py - ReAct推理
ReAct (Reasoning + Acting) 模式：
```
Thought: 分析当前情况
Action: 选择工具执行
Observation: 观察结果
→ 循环直到完成
```

#### 3.2.2 reflexion.py - Reflexion推理
Reflexion 模式：
- 基于失败的自我改进
- 维护执行历史
- 抽象经验总结

### 3.3 modes/ 模块

| 模式 | 描述 | 特点 |
|------|------|------|
| AlgorithmMode | 算法训练 | 出题→写代码→测试→调试→优化 |
| DesignMode | 设计训练 | OOP结构分析、模式应用 |
| ProjectMode | 项目引导 | 从0到1逐步构建 |
| RefactorMode | 代码重构 | 质量提升、坏味道识别 |
| LearningPathMode | 学习路径 | 长期能力规划 |

### 3.4 tools/ 模块

#### 3.4.1 base.py - Tool基类
所有工具的基类，定义：
- `name`: 工具名称
- `description`: 工具描述
- `parameters`: 参数定义
- `execute()`: 执行方法

#### 3.4.2 registry.py - 工具注册器
- 注册/注销工具
- 按名称查找工具
- 工具列表管理

#### 3.4.3 核心工具

| 工具 | 功能 |
|------|------|
| run_code | 在隔离环境中执行代码 |
| generate_tests | 自动生成测试用例 |
| analyze_error | 分析错误原因 |
| code_lint | 代码质量检查 |
| design_analyzer | OOP结构分析 |
| project_planner | 任务拆解规划 |

### 3.5 execution/ 模块

职责：代码执行环境管理
- `DockerRunner`: 使用Docker容器执行代码
- `Pool`: 容器池管理，支持并发

### 3.6 service/ 模块

#### 3.6.1 agent_service.py
Agent服务主入口，协调各组件工作

#### 3.6.2 trace_service.py
Trace记录服务，保存推理过程

#### 3.6.3 user_service.py
用户管理服务

---

## 4. Agent核心流程（伪代码）

```
Agent执行流程:

1. 接收用户请求
   └─> 确定训练模式

2. 用户建模
   └─> 查询用户画像
   └─> 更新用户水平

3. 制定计划 (Planner)
   └─> 分析任务目标
   └─> 拆解为可执行步骤

4. 循环执行 (Executor + Reasoning)
   ┌─────────────────────────────────────┐
   │  for each step in plan:             │
   │                                     │
   │  # ReAct 推理循环                   │
   │  while not finished:                │
   │      Thought: 分析当前状态          │
   │      Action: 选择并执行工具         │
   │      Observation: 获取结果          │
   │      # Reflexion 反思              │
   │      if failed:                    │
   │          Reflect: 总结教训          │
   │          Adjust: 调整策略           │
   │                                     │
   │  # 评估结果                          │
   │  Evaluation: 检查是否达标           │
   │  if not satisfied:                 │
   │      goto 3 # 重新计划               │
   └─────────────────────────────────────┘

5. 输出结果
   └─> 返回答案 + Trace记录
```

---

## 5. Tool接口设计

### 5.1 Tool基类

```python
class Tool(ABC):
    """工具基类，所有工具必须继承此类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，用于注册和调用"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述，用于LLM理解工具用途"""
        pass

    @property
    def parameters(self) -> list[Parameter]:
        """工具参数定义"""
        return []

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具，返回结果"""
        pass
```

### 5.2 ToolResult结构

```python
@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool                    # 是否成功
    output: str                      # 输出内容
    error: str | None                # 错误信息
    metadata: dict                  # 附加信息（执行时间等）
```

---

## 6. Step/Trace数据结构（核心）

### 6.1 Step - 单步执行记录

```python
@dataclass
class Step:
    """Agent执行过程中的单一步骤"""
    step_id: str                    # 步骤唯一ID
    trace_id: str                   # 所属Trace ID

    # 推理信息
    thought: str                    # 当前思考
    action: str                    # 执行的动作
    action_input: dict              # 动作输入参数

    # 工具调用
    tool_name: str | None          # 调用的工具名
    tool_input: dict | None        # 工具输入
    tool_output: ToolResult | None # 工具输出

    # 状态
    observation: str               # 观察结果
    status: StepStatus             # pending/running/completed/failed
    error: str | None              # 错误信息

    # 反思（可选）
    reflection: str | None        # 反思内容

    # 时间戳
    created_at: datetime
    completed_at: datetime | None
```

### 6.2 Trace - 完整执行链

```python
@dataclass
class Trace:
    """完整的Agent执行Trace"""
    trace_id: str                   # 唯一标识
    session_id: str                 # 会话ID
    user_id: str                    # 用户ID

    # 上下文
    mode: TrainingMode              # 训练模式
    task_description: str          # 任务描述
    user_level: UserLevel          # 用户水平

    # 执行步骤
    steps: list[Step]              # 所有步骤

    # 最终结果
    final_output: str | None       # 最终输出
    success: bool                  # 是否成功

    # 元数据
    started_at: datetime
    completed_at: datetime | None
    total_duration: float | None   # 总耗时（秒）

    # 统计信息
    tool_usage: dict[str, int]     # 工具使用统计
    error_count: int               # 错误次数
```

### 6.3 Trace可视化数据结构

```python
@dataclass
class TraceTimeline:
    """用于前端Timeline展示的数据结构"""
    trace_id: str
    total_steps: int

    # 步骤概览（简洁信息，用于Timeline）
    steps_summary: list[StepSummary]

    # 详细数据（展开查看）
    steps_detail: list[StepDetail]

    # 统计
    statistics: TraceStatistics


@dataclass
class StepSummary:
    """步骤概要 - 用于Timeline展示"""
    step_id: int
    thought_preview: str           # 思考预览（截取）
    action_preview: str            # 动作预览
    status: str
    duration: float


@dataclass
class StepDetail:
    """步骤详情 - 展开时显示"""
    step_id: int
    full_thought: str
    full_action: str
    tool_calls: list[ToolCall]
    full_observation: str
    reflection: str | None
```

---

## 7. 多模式设计说明

### 7.1 模式基类

```python
class TrainingMode(ABC):
    """训练模式基类"""

    @property
    @abstractmethod
    def mode_name(self) -> str:
        """模式名称"""

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """模式对应的系统提示词"""

    @abstractmethod
    def get_tools(self) -> list[type[Tool]]:
        """该模式需要使用的工具"""

    @abstractmethod
    def create_agent_components(self) -> AgentComponents:
        """创建该模式专用的Agent组件"""
```

### 7.2 各模式差异

| 模式 | Planner策略 | Executor重点 | Evaluator标准 | 反思重点 |
|------|-------------|--------------|---------------|----------|
| Algorithm | 出题+拆解 | 代码实现+测试 | 通过率+复杂度 | 算法优化方向 |
| Design | 结构分析 | 模式应用 | SOLID原则 | 设计模式选择 |
| Project | 里程碑规划 | 迭代开发 | 功能完整性 | 架构决策 |
| Refactor | 问题识别 | 渐进重构 | 质量评分 | 坏味道避免 |
| Learning | 能力评估 | 练习执行 | 掌握程度 | 学习方法 |

---

## 8. Agent可视化数据流设计

### 8.1 数据流概述

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   前端 UI   │────▶│  FastAPI    │────▶│Agent Service│
│  (Gradio)   │◀────│ Controller  │◀────│             │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                    ┌──────────────────────────┘
                    ▼
┌─────────────────────────────────────────────────────┐
│              Trace Service                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│  │  Step   │  │  Step   │  │  Step   │  ...        │
│  │  Log    │  │  Log    │  │  Log    │              │
│  └────┬────┘  └────┬────┘  └────┬────┘              │
│       └────────────┼────────────┘                   │
│                    ▼                                 │
│            ┌─────────────┐                           │
│            │    Trace    │                           │
│            └─────────────┘                           │
└─────────────────────────────────────────────────────┘
```

### 8.2 前端展示结构

```javascript
// 前端Timeline数据结构
{
  trace_id: "trace_xxx",
  steps: [
    {
      id: 1,
      type: "thought",          // 思考节点
      content: "我需要先理解题目...",
      status: "completed"
    },
    {
      id: 2,
      type: "action",           // 动作节点
      content: "调用 run_code 工具",
      tool: "run_code",
      status: "running"         // 执行中
    },
    {
      id: 3,
      type: "observation",      // 观察节点
      content: "代码执行成功，输出:...",
      status: "pending"
    }
  ],
  // 实时更新：WebSocket 或 轮询
}
```

### 8.3 API端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/agent/run` | POST | 启动Agent任务 |
| `/api/trace/{id}` | GET | 获取Trace详情 |
| `/api/trace/{id}/stream` | GET | SSE流式获取Trace更新 |
| `/api/trace/{id}/timeline` | GET | 获取Timeline展示数据 |

---

## 9. 扩展性设计

### 9.1 扩展点

1. **新推理机制**: 在 `reasoning/` 添加新类，实现 `ReasoningEngine` 接口
2. **新工具**: 在 `tools/impl/` 添加新工具类，注册到 `ToolRegistry`
3. **新训练模式**: 在 `modes/` 添加新模式类
4. **新LLM Provider**: 在 `llm/` 添加新Provider

### 9.2 插件机制

```python
# 工具注册示例
tool_registry.register("my_tool", MyCustomTool)

# 推理机制注册示例
reasoning_registry.register("my_reasoning", MyReasoningEngine)
```

---

## 10. 后续开发建议

### 10.1 优先级排序

1. **Phase 1 - 核心框架**: Agent基类 + ReAct推理 + run_code工具
2. **Phase 2 - 算法模式**: 实现AlgorithmMode + 代码执行
3. **Phase 3 - Trace系统**: 实现可视化记录
4. **Phase 4 - Gradio UI**: 对接前端
5. **Phase 5 - 多模式**: 其他训练模式
6. **Phase 6 - Reflexion**: 反思机制
7. **Phase 7 - 用户建模**: 个性化学习

### 10.2 注意事项

- 所有新增模块需添加单元测试
- 保持模块间接口稳定
- 及时更新本文档
