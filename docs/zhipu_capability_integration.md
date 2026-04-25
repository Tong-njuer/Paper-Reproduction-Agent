# Zhipu 平台 LLM 及 API 能力在 Agent 项目中的应用方案

## 1. 官方能力概览

参考 [智谱AI官方 Function Calling 文档](https://docs.bigmodel.cn/cn/guide/capabilities/function-calling)：
- 智谱 LLM 支持 Function Calling（函数调用），可让大模型直接调用开发者注册的函数，实现“工具调用”能力。
- 支持同步/异步调用、参数结构化传递、函数描述、返回结构化结果。
- 支持多轮对话、上下文记忆、函数调用链路。
- 支持 Python/RESTful API 接入。

## 2. 本地 Agent 项目可用的 Zhipu 能力

### 2.1 LLM 推理能力
- 直接调用智谱 LLM（如 GLM-4/GLM-3-Turbo）进行自然语言理解、推理、摘要、结构化抽取。
- 用于：论文理解、任务拆解、代码解释、错误分析、反思建议等。

### 2.2 Function Calling 工具调用能力
- 可将本地实现的工具（如 code_tool、wiki_tool 等）注册为“函数”，通过 LLM function calling 机制由大模型自动选择和调用。
- 支持结构化参数、返回值，便于与 Agent 框架的 ToolResult 对接。
- 用于：代码执行、文档检索、计划管理、环境搭建等自动化操作。

### 2.3 多轮对话与上下文记忆
- 支持多轮对话上下文，便于 Agent 记忆历史步骤、失败原因、用户补充信息。
- 可结合本地 memory.py，增强 Agent 的长期/短期记忆能力。

### 2.4 结构化输出与 JSON 解析
- 支持直接输出结构化 JSON，便于 Planner、ReAct、Reflexion 等模块消费。
- 用于：任务计划、工具参数、测试结果、错误分类等。

### 2.5 API 兼容性
- 支持 Python SDK（zhipuai）、RESTful API，便于在 Docker、本地、云端等多环境部署。
- 可结合本地 config.py 配置 API Key、模型类型、超时等参数。

## 3. 推荐落地点

| Agent 模块         | 可用 Zhipu 能力            | 说明                                |
| ------------------ | -------------------------- | ----------------------------------- |
| core/llm.py        | LLM 推理、Function Calling | 已有 GLM 封装，建议补充函数调用能力 |
| agent/planner.py   | LLM 推理、结构化输出       | 任务拆解、计划生成                  |
| agent/react.py     | Function Calling           | 工具选择与参数结构化传递            |
| agent/reflexion.py | LLM 推理、结构化输出       | 错误分析、修复建议                  |
| agent/memory.py    | 多轮对话、上下文记忆       | 记忆检索与注入                      |
| tools/             | Function Calling           | 工具注册与调用                      |
| streamlit_app.py   | LLM 推理                   | UI 端自然语言交互                   |

## 4. 典型实现建议

1. 在 core/llm.py 增加对 Function Calling 的支持，自动将工具注册为函数，LLM 可根据上下文自动选择调用。
2. 在 react.py 中，优先走 function_calling 路径，回退到本地工具注册表。
3. 所有工具实现严格结构化输入输出，便于 LLM 解析和调用。
4. 结合 memory.py，将历史步骤、失败原因注入 LLM 上下文，提升多轮推理效果。
5. 支持 API Key、模型类型、超时等参数的灵活配置，兼容本地和云端部署。

## 5. 参考链接
- 智谱 Function Calling 官方文档：https://docs.bigmodel.cn/cn/guide/capabilities/function-calling
- 智谱 Python SDK：https://github.com/zhpmatrix/ChatGLM-API
- 项目本地接口规范：docs/tool_interface.md

---

> 本文档总结了智谱平台 LLM 及 Function Calling 能力在本 Agent 项目中的可用实现点，建议后续开发优先补齐 function calling 路径，提升工具层自动化与智能化水平。
