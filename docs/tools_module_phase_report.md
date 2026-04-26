# Tools 模块阶段性工作报告

## 1. 文档目标与范围

本报告仅覆盖当前仓库中的 tools 模块，聚焦以下内容：

1. 模块设计与接口约束。
2. 测试方案与测试结果。
3. 各工具当前功能现状、边界与已知风险。

不包含 Agent 的 Planner/ReAct/Reflexion 提示词策略与状态机逻辑。

---

## 2. 阶段结论

当前 tools 模块已形成可独立运行的工程化能力：

1. 统一抽象与注册中心已落地。
2. 10 个核心工具均已实现并注册。
3. 已具备两套测试：基础回归测试 + tools-only 隔离测试。
4. 最新测试结果全部通过。

本阶段可认为 tools 模块已达到“可用且可回归”的里程碑状态。

---

## 3. 模块设计

## 3.1 统一接口层

tools 模块使用统一契约：

1. `BaseTool`：所有工具继承，统一 `execute(**kwargs)` 入口。
2. `ToolResult`：标准返回结构，包含 `success`、`output`、`error`、`metadata`。
3. `_success/_error`：统一成功失败封装，降低重复代码。
4. `TOOL_REGISTRY`：集中注册与分发。

该设计带来的收益：

1. ReAct 调用方式稳定，便于模型生成 action_args。
2. 失败语义一致，便于后续错误分类与审计。
3. 各工具可独立测试，不依赖 Agent 主流程。

## 3.2 工具分层

当前工具可按职责分为四层：

1. 采集与解析层：`paper_tool`、`source_tool`、`wiki_tool`。
2. 仓库与环境层：`repo_index_tool`、`sandbox_tool`。
3. 执行与验证层：`code_tool`、`test_tool`。
4. 沉淀与编排辅助层：`doc_tool`、`schedule_tool`、`learning_path_tool`。

## 3.3 安全与稳健性设计

已实现的关键防护：

1. `code_tool` 危险命令关键词拦截（默认阻断高风险命令）。
2. `repo_index_tool` 文件读取路径穿越防护（限制在 root_path 内）。
3. 命令执行工具统一支持超时参数，避免长时间阻塞。
4. 网络请求工具具备超时与异常捕获，返回可机读错误信息。

---

## 4. 各工具功能现状

下表为当前功能状态快照。

| 工具                 | 核心能力                                     | 当前状态 | 说明                                         |
| -------------------- | -------------------------------------------- | -------- | -------------------------------------------- |
| `paper_tool`         | 文本/PDF/URL/标识解析，结构化抽取            | 已实现   | 以启发式抽取为主，适合流程联调与中等复杂文本 |
| `source_tool`        | 候选仓库发现、克隆、归档下载、源码完整性分析 | 已实现   | 支持候选打分和完整性检查                     |
| `repo_index_tool`    | 目录索引、文件读取、文本检索、仓库摘要       | 已实现   | 支持 hash、范围读取、检索上限                |
| `sandbox_tool`       | 工作区创建、环境探测、安装计划、venv 创建    | 已实现   | 支持多语言清单探测和安装命令生成             |
| `test_tool`          | 命令执行、静态检查、单测、烟雾测试、指标对比 | 已实现   | 指标比较支持容差逻辑                         |
| `doc_tool`           | 文档写入、日志追加、JSON 产物、复现报告生成  | 已实现   | 已支持结构化报告落盘                         |
| `code_tool`          | 命令执行与基础安全控制                       | 已实现   | 支持 cwd/env/timeout 和执行元数据            |
| `wiki_tool`          | Wikipedia 搜索与摘要提取                     | 已实现   | 测试中已进行网络请求 mock                    |
| `schedule_tool`      | 计划创建、更新、查询、列表、超时建议         | 已实现   | 本地 JSON 存储，支持进度状态流转             |
| `learning_path_tool` | 学习路径分阶段生成                           | 已实现   | 支持 markdown/json 输出                      |

---

## 5. 测试设计与执行结果

## 5.1 测试分层

当前采用两套测试：

1. `tests/test_tools.py`：基础回归测试，验证主流程和关键动作。
2. `tests/test_tools_only.py`：tools-only 隔离测试，不依赖 agent/prompt。

其中 tools-only 测试使用合成论文夹具：

- `tests/fixtures/synthetic_paper_with_code.md`

该夹具包含：

1. 论文结构段落（Abstract/Method/Datasets/Metrics）。
2. 外部源码线索（GitHub 与 arXiv URL）。
3. Python 代码片段，便于 paper/source/repo/test 工具联动验证。

## 5.2 最新执行结果

本阶段重新执行结果如下：

1. `python -m unittest discover -s tests -p "test_tools.py" -v`
   - 结果：20/20 通过。
2. `python -m unittest discover -s tests -p "test_tools_only.py" -v`
   - 结果：24/24 通过。

总计：44 个 tools 相关测试全部通过。

## 5.3 覆盖要点

已覆盖的关键场景：

1. 正常路径：各工具核心 action 的成功执行。
2. 参数校验：缺失参数和非法参数分支。
3. 安全防护：危险命令拦截、路径穿越阻断。
4. 文件副作用：文档/日志/JSON 报告落盘验证。
5. 数据对比：指标容差内通过与容差外失败。
6. 网络依赖隔离：wiki 工具使用 mock，提升稳定性。

---

## 6. 现阶段能力边界

当前 tools 模块可以稳定支撑“从输入到产物落盘”的执行链路，但仍存在边界：

1. `paper_tool` 仍以启发式规则抽取为主，复杂论文结构（多栏、表格、公式）精度有限。
2. `source_tool` 的真实网络下载/克隆在离线或受限网络下会受影响。
3. `test_tool` 的 `compare_metrics` 目前是字段对齐 + 容差策略，尚未内建更复杂统计检验。
4. `code_tool` 使用关键词拦截危险命令，属于基础安全层，尚未引入更细粒度策略沙箱。
5. `schedule_tool` 基于本地 JSON，适合单实例场景，暂不支持并发协作。

---

## 7. 下一阶段建议（仅 tools 侧）

建议按优先级推进以下改进：

1. 提升 `paper_tool` 的结构化抽取精度：增强章节识别与表格/公式处理。
2. 为 `source_tool` 增加更细的错误码与重试策略（例如 DNS/403/超时分类）。
3. 为 `test_tool` 增加结果 schema 校验与更丰富比较策略（绝对阈值、相对阈值、缺失值策略）。
4. 为 `code_tool` 增加可配置白名单/黑名单机制与审计标签。
5. 将 tools-only 测试纳入 CI 必跑项，保障迭代稳定性。

---

## 8. 附录：当前工具清单

当前注册的工具如下：

1. `paper_tool`
2. `source_tool`
3. `repo_index_tool`
4. `sandbox_tool`
5. `test_tool`
6. `doc_tool`
7. `code_tool`
8. `wiki_tool`
9. `schedule_tool`
10. `learning_path_tool`

---

报告日期：2026-04-26
