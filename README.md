# Agent Demo（论文复现方向）

## 快速开始

请先阅读 [docs/getting_started.md](docs/getting_started.md)，按文档完成：

1. 安装依赖
2. 运行测试
3. 启动 CLI 或 Streamlit UI

推荐最小命令：

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m app.main --mode demo
```

---

# 📘 Autonomous Agent Core 设计说明书（无 Tool 部分）

---

# 一、设计目标（Design Goals）

本系统旨在构建一个**通用的自治 Agent Core**，具备以下能力：

### 🎯 核心目标

1. **自主规划能力（Planning）**

   * 能将复杂目标拆解为子任务
   * 支持动态重规划（replanning）

2. **交互式决策能力（ReAct）**

   * 基于环境反馈持续决策
   * 支持多步推理与行动循环

3. **自我修正能力（Reflexion）**

   * 能分析失败原因
   * 能调整策略并避免重复错误

4. **状态感知与记忆能力（Memory）**

   * 跟踪历史行为与结果
   * 支持长期策略优化

---

# 二、总体架构（Architecture Overview）

```id="agent_arch"
                ┌──────────────┐
                │    Goal      │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │   Planner    │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │   ReAct Loop │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │ Observation  │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │  Reflexion   │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │   Memory     │
                └──────────────┘
```

---

# 三、核心模块设计（Core Components）

---

# 3.1 Planner（规划模块）

## 📌 职责

* 将高层目标拆解为可执行子任务
* 根据执行反馈动态调整计划

---

## 📥 输入

* `goal`：用户目标
* `context`：当前状态（历史、错误、进度）

---

## 📤 输出

```json
[
  {"step_id": 1, "description": "安装依赖"},
  {"step_id": 2, "description": "运行训练脚本"}
]
```

---

## 🧠 设计要点

### ✅ 支持动态规划

* 允许根据失败进行replan

### ✅ 不绑定具体工具

* 只描述“做什么”，不描述“怎么做”

---

## 🔄 Replanning触发条件

* 连续失败
* 环境变化
* 新信息出现

---

# 3.2 ReAct Engine（行动决策模块）

## 📌 职责

* 在每一步决定“下一步行动”
* 基于Observation进行推理

---

## 🔁 工作模式（核心循环）

```id="react_loop"
Thought → Action → Observation → Thought → ...
```

---

## 📥 输入

* 当前计划
* 历史行为
* 最新Observation

---

## 📤 输出

```json
{
  "thought": "需要先运行代码测试环境",
  "action": "run_code",
  "args": {
    "command": "python train.py"
  }
}
```

---

## 🧠 设计要点

### ✅ 局部决策（step-level reasoning）

* 不依赖全局计划精确性

### ✅ 支持探索（exploration）

* 可以尝试不同路径

---

# 3.3 Reflexion（自我反思模块）

## 📌 职责（最关键模块🔥）

* 分析失败原因
* 提供修复策略
* 更新Agent行为

---

## 📥 输入

* Observation（尤其是错误）
* 当前策略

---

## 📤 输出

```json
{
  "analysis": "缺少依赖numpy",
  "fix_action": {
    "action": "install_package",
    "args": {"package": "numpy"}
  },
  "lesson": "运行前应检查依赖"
}
```

---

## 🧠 设计要点

### ✅ 结构化错误理解

* 使用error schema（type/subtype）

### ✅ 可学习性

* 将经验写入Memory

---

## 🔥 Reflexion的三层能力

| 层级 | 能力             |
| ---- | ---------------- |
| L1   | 错误解释         |
| L2   | 修复建议         |
| L3   | 策略优化（长期） |

---

# 3.4 Memory（记忆模块）

## 📌 职责

* 存储历史行为与结果
* 支持策略改进

---

## 🧠 Memory类型

### 1️⃣ Short-term Memory

```json
{
  "last_action": "...",
  "last_error": "..."
}
```

---

### 2️⃣ Long-term Memory

```json
{
  "common_errors": [
    {"error": "missing numpy", "fix": "pip install numpy"}
  ]
}
```

---

## 📌 作用

* 避免重复错误
* 提高效率

---

# 3.5 State Manager（状态管理）

## 📌 职责

* 管理Agent当前状态
* 支持可视化

---

## 📊 状态示例

```json
{
  "step": 3,
  "plan_progress": "running experiment",
  "last_action": "...",
  "status": "error"
}
```

---

# 四、Agent运行流程（Execution Flow）

---

## 🔁 主循环

```id="main_loop"
while not done:

    1. Planner → 生成/更新计划
    
    2. ReAct → 决定行动
    
    3. 执行（Tool Layer）
    
    4. 获取Observation
    
    5. 若失败 → Reflexion
    
    6. 更新Memory
    
    7. 判断是否终止
```

---

## 📌 终止条件

* 任务成功
* 达到最大步数
* 多次失败无法修复

---

# 五、模块协同机制（Coordination）

---

## 🔗 Planner 与 ReAct

* Planner提供方向
* ReAct做局部决策

---

## 🔗 ReAct 与 Reflexion

* ReAct负责执行
* Reflexion负责纠错

---

## 🔗 Reflexion 与 Memory

* Reflexion生成经验
* Memory存储经验

---

# 六、关键设计原则（Key Principles）

---

## ✅ 1. 解耦（Decoupling）

* Agent Core 不依赖具体工具

---

## ✅ 2. 结构化（Structured Output）

* 所有模块输出JSON格式

---

## ✅ 3. 可解释性（Interpretability）

* 每一步都有 thought / action / reflection

---

## ✅ 4. 可扩展性（Extensibility）

* 可添加新模块（如多Agent）

---

## ✅ 5. 试错驱动（Trial-and-Error Driven）

* 系统通过失败不断优化

---

# 七、可视化设计（Visualization）

---

## CLI示例

```id="cli_demo"
[Step 3]
Thought: 尝试运行代码
Action: python train.py
Observation: ERROR missing numpy

[Reflection]
→ 安装numpy

[Next Action]
pip install numpy
```

---

## Web可视化（推荐）

* 状态流图（Graph）
* 行为日志
* 错误演化过程

---

# 八、扩展能力（Advanced Features）

---

## ⭐ 1. 多策略探索

* 同一问题尝试多种方案

---

## ⭐ 2. 自适应规划

* Planner基于历史优化

---

## ⭐ 3. 元学习（Meta-learning）

* 优化自身prompt或策略

---

# 九、总结（可直接写报告）

> 本Agent Core通过集成Planner、ReAct与Reflexion三大核心模块，实现了从目标分解、动态决策到错误驱动优化的完整闭环。系统采用结构化接口与模块解耦设计，使其具备良好的扩展性与跨任务适应能力。
