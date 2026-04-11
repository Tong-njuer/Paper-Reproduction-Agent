# 编程教练 Agent

编程学习助手，通过 AI Agent 帮助用户学习编程，包含出题、答题评测、知识库管理、学习路径规划等功能。

## 项目结构

```
agent/
├── app/
│   ├── agent/          # Agent 核心（ReAct 逻辑）
│   ├── tools/          # 工具函数（日程、Wiki、代码、路径）
│   ├── db/             # 数据库模型
│   ├── core/           # 配置、认证、上下文
│   └── main.py         # CLI 入口
├── streamlit_app.py    # Streamlit 旧版前端（将被废弃）
└── requirements.txt
```

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env  # 配置 ZHIPU_API_KEY
streamlit run streamlit_app.py  # 旧版前端
```

---

# 前端开发指南（FastAPI + React）

## 系统架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  React Frontend │     │  FastAPI Backend │     │  现有 Python    │
│  (Port 5173)    │ ←──→│  (Port 8000)    │ ←──→│  Agent 逻辑     │
│                 │     │                 │     │  app/agent/    │
│  - Vite + React │     │  - API 路由封装  │     │  app/tools/     │
│  - Ant Design   │     │  - Session 管理 │     │  app/db/        │
│  - Monaco Editor│     │  - 流式输出     │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**核心原则**：React 只做 UI 和状态管理，所有业务逻辑复用现有 Python 代码，FastAPI 负责粘合。

## 页面结构

```
App
├── LoginPage          # 登录 / 注册
├── MainLayout         # 登录后主布局
│   ├── Header         # 顶栏：用户信息、登出
│   ├── Sidebar        # 侧边栏（6 个板块）
│   │   ├── ChatTab       # 对话区
│   │   ├── ScheduleTab   # 日程安排
│   │   ├── WikiTab       # 知识库
│   │   ├── PathTab       # 学习路径
│   │   ├── CodeTab       # 代码工作区
│   │   └── WorkflowTab   # 内部工作流
│   └── MainContent    # 各 Tab 内容
└── SettingsPage      # 设置（可选，后期做）
```

## API 规范

所有接口前缀 `/api`，认证通过 Cookie 或 Header 传递 `user_id`。

### 1. 对话

```
POST /api/chat
Body: { "message": "出一道链表题目", "history": [...] }
Response: { "response": "题目创建成功..." }

请求 history 格式：
[
  { "role": "user", "content": "用户消息" },
  { "role": "assistant", "content": "助手消息" }
]

返回的 response 是模型的完整回答（包含 Final Answer）。
```

### 2. 日程

```
GET /api/schedules
Response: "[1] 日程标题 (2024-01-01 ~ 2024-01-07)\n[2] ..."

POST /api/schedules
Body: { "title": "学习链表", "start_date": "2024-01-01", "end_date": "2024-01-07" }
Response: "日程创建成功: [ID]"

PUT /api/schedules/{id}
Body: { "title"?: "...", "start_date"?: "...", "end_date"?: "..." }

DELETE /api/schedules/{id}
```

### 3. Wiki

```
GET /api/wikis
Response: "[1] C++指针\n[2] Python入门"

POST /api/wikis
Body: { "title": "标题", "content": "内容" }
Response: "Wiki创建成功: [ID]"

GET /api/wikis/{id}
Response: "# 标题\n\n内容"

DELETE /api/wikis/{id}
```

### 4. 学习路径

```
GET /api/learning-paths
Response: "[1] C++入门之路 (3个步骤)\n[2] Python进阶 (5个步骤)"

POST /api/learning-paths
Body: { "title": "...", "description": "...", "steps": "[{\"title\":...}]" }
Response: "学习路径创建成功: [ID]"

GET /api/learning-paths/{id}
Response: "# 路径标题\n\n总步骤数: 3\n👉 步骤1: 指针基础...\n   步骤2: ..."

GET /api/learning-paths/{id}/progress
Response: "=== 路径名 ===\n进度: 2/3\n【当前步骤】..."

POST /api/learning-paths/{id}/start
POST /api/learning-paths/{id}/complete-step
```

### 5. 代码（重点改动）

```
GET /api/code-problems
Response: "[1] 链表基础 (难度: easy, 标签: 链表)\n..."

GET /api/code-problems/{id}
Response: "# 链表基础\n**难度**: easy\n**标签**: 链表\n\n## 题目描述\n...\n## 测试用例\n..."

POST /api/code-problems/submit/{id}
Body: { "code": "struct ListNode {\n    int val;\n    ...\n}" }
Response:
"""
【评测结果】
❌ 未通过 - ...
🔍 错误类型: 逻辑错误
   原因: ...
📊 复杂度: 时间 O(n), 空间 O(1)
💡 代码风格得分: 65/100
🏷️ 能力变化: 链表(一般 → 薄弱)

【改进建议】
  • 注意空指针判断
"""
```

### 6. 内部工作流

```
POST /api/agent/execute-tool
Body: { "tool_name": "create_code_problem", "args": {...} }
Response: { "output": "题目创建成功: [1] ..." }

GET /api/workflow/logs
Response: "[WORKFLOW] 最近的工作流输出..."
```

### 7. 用户认证

```
POST /api/auth/register
Body: { "username": "...", "password": "..." }
Response: { "success": true, "message": "注册成功" }

POST /api/auth/login
Body: { "username": "...", "password": "..." }
Response: { "success": true, "user_id": 1 }
```

## 前端任务顺序

### Phase 1：基础框架
- 搭建 React + Vite + TypeScript 项目
- 配置路由（React Router）
- 登录 / 注册页面
- MainLayout 框架（Header + Sidebar + Content）

### Phase 2：对话界面
- 对话列表 UI（消息气泡）
- 调用 `/api/chat` 接口
- 展示模型返回结果
- 对话历史管理（传入 history）

### Phase 3：数据展示（Schedule / Wiki / Path）
- 调用各 GET 接口获取数据
- 列表展示 + 详情弹窗或内嵌展示
- 日程支持增删改
- Wiki 支持创建和删除
- 学习路径支持开始、完成步骤

### Phase 4：代码工作区（较大改动）
- 题目列表
- Monaco Editor 代码编辑区
- 提交按钮 → 调用 `/api/code-problems/submit/{id}`
- 展示评测结果

### Phase 5：内部工作流
- 实时获取 `/api/workflow/logs`
- 推荐使用 SSE（Server-Sent Events）实现流式输出
- 类似终端的展示区域

### Phase 6：完善
- 用户个人中心
- 设置页面
- 响应式适配

## 技术选型建议

| 模块 | 推荐方案 | 说明 |
|------|----------|------|
| 框架 | React 18 + Vite + TypeScript | 快、类型安全 |
| UI 组件 | Ant Design 或 shadcn/ui | 快速出活 |
| 状态管理 | Zustand | 轻量，比 Redux 简单 |
| 路由 | React Router v6 | 标准方案 |
| 代码编辑器 | Monaco Editor | VSCode 同款，支持多语言 |
| 实时通信 | SSE | 比 WebSocket 简单，适合单向流 |

## 关键设计说明

### 1. 代码工作区（旧 → 新）

**旧流程（Streamlit）**：
```
用户编辑本地 workspace/problem_1.md → 对模型说"提交第1题"
→ agent 调用 submit_and_grade_code → 读取文件 → 评测
```

**新流程（React）**：
```
用户在前端 Monaco Editor 写代码 → 点"提交"
→ POST /api/code-problems/submit/{id}，body 带 code 字段
→ FastAPI 调用评测逻辑（不读文件）→ 返回评测结果
```

**FastAPI 层改动**：
```python
# 伪代码示例
@app.post("/api/code-problems/submit/{id}")
async def submit_code(problem_id: int, code: str):
    # 直接接收代码，不读文件
    # 调用抽取出的 grade_code 函数
    return grade_code_from_code(problem_id, user_code=code)
```

### 2. 内部工作流展示

当前 agent.py 中大量 `print()` 输出到终端，前端需要捕获这些输出：

**方案 A（推荐，改动小）**：捕获 stdout
```python
import io, sys
old = sys.stdout
sys.stdout = captured = io.StringIO()
# 调用 agent
sys.stdout = old
result = captured.getvalue()  # 包含所有 print 输出
return {"logs": result}
```

**方案 B**：Agent 改为生成器，yield 每一步，实现真正流式。

### 3. 用户上下文

现有代码使用线程本地变量：
```python
from app.core.context import set_current_user_id, get_current_user_id
```

FastAPI 层需要在每个请求中设置用户上下文：
```python
@app.middleware
async def set_user_context(request: Request, call_next):
    user_id = request.headers.get("X-User-ID")  # 或从 cookie 获取
    if user_id:
        set_current_user_id(int(user_id))
    response = await call_next(request)
    return response
```

## 推荐的目录结构（前端）

```
frontend/
├── src/
│   ├── api/           # API 请求封装
│   │   ├── chat.ts
│   │   ├── schedule.ts
│   │   ├── wiki.ts
│   │   ├── path.ts
│   │   └── code.ts
│   ├── components/    # 通用组件
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   └── CodeEditor.tsx
│   ├── pages/         # 页面
│   │   ├── Login.tsx
│   │   ├── Chat.tsx
│   │   ├── Schedule.tsx
│   │   ├── Wiki.tsx
│   │   ├── Path.tsx
│   │   ├── Code.tsx
│   │   └── Workflow.tsx
│   ├── stores/        # Zustand stores
│   │   ├── authStore.ts
│   │   ├── chatStore.ts
│   │   └── ...
│   ├── App.tsx
│   └── main.tsx
├── package.json
└── vite.config.ts
```

## 环境变量

前端需要配置：
```
VITE_API_BASE_URL=http://localhost:8000/api
```

## 注意事项

1. **不要改动 app/agent/、app/tools/、app/db/ 下的现有代码** — 业务逻辑保持不变
2. **API 响应格式** — 现有工具返回的是字符串，前端需要按字符串解析（或后端统一处理成 JSON）
3. **用户隔离** — 所有数据查询都按 user_id 隔离，API 层负责注入 user_id
4. **代码评测** — 需要后端新增接口接收前端代码，而非读文件
