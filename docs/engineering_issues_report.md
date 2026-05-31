# 论文复现 Agent 初步问题报告

调试一段时间代码，发现几个问题，记录一下。

## 1. 每次对话都从头开始，上下文不延续

**伪多轮对话**：用户每说一句话，系统就当成一个全新的"复现任务"。Planner 会从零生成一整套流水线——搜索仓库、克隆、运行——走完才算完。

但用户跑完一个项目后说"再跑另一个脚本"或者"帮我看看这个报错"，Agent 完全不记得自己已经克隆过这个项目。它只会机械地重启 `Step 1: 搜索目标仓库...`，然后卡死。

**关键词路由**：`Planner._fallback_plan` 的意图判断靠简单的字符串匹配，检测到"复现"、"论文"就走学术搜索管线。碰上 `ML-From-Scratch` 这种纯工程项目，它还是会去 arXiv 搜论文，然后被一堆不相关的干扰信息带偏。

## 2. 建虚拟环境不看项目需求

`execute_session_tool` 直接用宿主机默认的 Python 版本（比如 python3.11）创建 venv。那些老论文的代码（Python 3.7、TensorFlow 1.x、PyTorch 1.x）在新版 Python 下连 pip install 都跑不过去。

按理说 Agent 应该先扫一遍 `setup.py`、`requirements.txt` 或者 `README.md`，看看项目需要什么 Python 版本，再去找对应的解释器。这个环节目前完全缺失。

## 3. 遇到致命错误就死循环重试

底层 API 返回 401 这种致命错误时，Planner 的降级逻辑没反应过来。它只会反复拼接"重试: 重试: 搜索..."然后硬重启。之前给这个死循环打了补丁，但错误处理这块的设计还是太脆了。

## 4. 配置解析逻辑有漏洞

`config.py` 解析 API_KEY 时用了简单的 `or` 逻辑。就算配了 `LLM_PROVIDER=zhipu`，只要环境变量里有 `DEEPSEEK_API_KEY`，它就会把这把 key 发给智谱的服务器，然后认证全挂。

我本地修复了一下，现在会根据 provider 动态绑定对应的 key。

---

## 后面可以做的事

1. **加个意图分类层**：用户消息进 Planner 之前，先让大模型快速判断一下。分三类：
   - 学术复现 → 走全量计划
   - 工程测试 → 跳过文献流，直接查 GitHub
   - 会话跟进 → 不生成新计划，基于当前目录单步执行

2. **execute_session_tool 加环境侦察环节**：建 venv 之前，先让 LLM 读一下项目的包管理文件，判断需要什么 Python 版本，再找对应的解释器来创建环境。如果装了 pyenv 可以直接用。

3. **把 Plan 改成动态状态机**：别搞成四个 Step 跑完就结束的链式任务。支持在任意节点暂停、接收用户指令、临时插入新步骤。

---

## 5. 跨步骤上下文断裂 — python_env_tool 获取不到克隆路径

**现象**：复现 "Attention Is All You Need" 时，Step 4 克隆成功（`tensor2tensor`），但 Step 5 `python_env_tool` 报错"仓库路径不存在: /app/workspace/annotated-transformer"。

**根因分析**（共 5 个独立问题叠加）：

### 根因 1：`_extract_result_info` 没有处理 clone_tool

`clone_tool` 成功返回后，输出中包含 `本地路径: /app/workspace/tensor2tensor`，但 `_extract_result_info()` 只从 `source_tool` / setup 类步骤提取路径，没有为 `clone_tool` 写提取逻辑。结果 `_step_context["planned_repo_path"]` 始终为空。

**修复**：在 `_extract_result_info` 中新增 `clone_tool` 分支，解析 `本地路径` 并写入 `planned_repo_path`。

### 根因 2：`python_env_tool._resolve_repo` 在多仓库时不会自动选择

当 workspace 中有多个仓库且没有传入 `repo_name` 时，`_resolve_repo` 直接返回错误"请指定 repo_name"，不会尝试推测用户想操作哪个仓库。

**修复**：新增 `_pick_most_recent_repo()` 方法，按 `.git/` 目录的修改时间排序，自动选中最近操作过的仓库。

### 根因 3：`_enrich_args` 对 python_env_tool 注入不够强硬

虽然我给 `python_env_tool` 加了 `_enrich_args`，但它只在 `planned_repo_path` 存在且 LLM **没有**生成 repo_name 时才注入。LLM 一旦生成了错的 repo_name（如 "annotated-transformer"），就不会被覆盖。

**修复**：`_enrich_args` 改为**强制注入** — 有 `planned_repo_path` 就直接赋值 `repo_path` 并移除 `repo_name`。

### 根因 4：ReAct LLM 会幻觉出错误的 repo_name

`ReActEngine.decide()` 调用 LLM 生成 `action_args`，LLM 在没有上下文的情况下编造了 "annotated-transformer" 作为仓库名。而 `_default_args` 返回的是 `{"action": "recon"}`（不含 repo_name），但 LLM 的输出优先级更高。

**修复**：配合根因 3 的强制注入，LLM 的 `repo_name` 幻觉被直接覆盖。

### 根因 5：Reflection 对 ambiguous_repo 的修复建议是 clone_tool，被跨工具拦截

`reflection.py` 的 `_suggest_fixes` 对 `ambiguous_repo` 的修复建议是 `clone_tool`（重新克隆），但 `orchestrator._allow_cross_tool_fix` 拒绝了从 `python_env_tool` 到 `clone_tool` 的切换。结果陷入了"失败→反射→修复被拒绝→再失败"的死循环。

**修复**：将 `ambiguous_repo` 的修复建议改为 `list_workspace_tool`（列出仓库供选择）和 `python_env_tool`（auto-detect 最 recent 仓库），绕过跨工具拦截。

### 错误追踪链路

```
Step 4 克隆成功（本地路径: /app/workspace/tensor2tensor）
  → _extract_result_info 未提取路径 [根因1]
  → planned_repo_path = ""  [根因1]
Step 5 python_env_tool
  → LLM 幻觉出 repo_name = "annotated-transformer" [根因4]
  → _enrich_args 看到 planned_repo_path 为空，无法覆盖 [根因3]
  → _resolve_repo 找不到该路径 → Error
重试:
  → 现在 workspace 有 2 个仓库（ML-From-Scratch + tensor2tensor）
  → LLM 再次幻觉，未传 repo_name
  → _resolve_repo 发现多个仓库，返回 ambiguous_repo [根因2]
  → Reflection 建议 clone_tool，被跨工具拦截 [根因5]
  → 死循环直到 max retries
```

### 已实施的修复

| 修复                  | 文件                                                   | 变更                                                                                   |
| --------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| ① clone_tool 提取路径 | `orchestrator.py:_extract_result_info`                 | 新增 `clone_tool` 分支解析 `本地路径` → `planned_repo_path`                            |
| ② 多仓库自动选择      | `python_env_tool.py`                                   | 新增 `_pick_most_recent_repo()`，改 `_resolve_repo()` 当多仓库时按 `.git` mtime 选最近 |
| ③ 强制注入 repo_path  | `orchestrator.py:_enrich_args`                         | `python_env_tool` 分支：有 context 就直接赋值 `repo_path`、移除 `repo_name`            |
| ④ LLM 幻觉抑制        | `react.py:_default_args` + `react.py:_fallback_decide` | python_env_tool 的默认 args 不再包含 repo_name/path                                    |
| ⑤ Reflection 修复建议 | `reflection.py:_suggest_fixes`                         | `ambiguous_repo` 建议改为 `list_workspace_tool` + `python_env_tool`                    |

---

## 6. Step 5 等待 LLM 响应超时（2分钟+）

**现象**：`python_env_tool` 步骤（Step 5）卡住，LLM 调用耗时超过 2 分钟触发 API timeout 重试：
```
13:59:43 → Request: model=glm-4.7 temp=0.7 max_tokens=65536 prompt_len=3213
14:01:48 → WARNING: API timeout (attempt 1/3), retrying in 10s...
```

**根因**：`ReActEngine.decide()` 对所有工具（包括参数完全确定的工具）都调用 LLM。23 个工具的 prompt + 累积历史记录使 LLM 响应极慢，且 source_tool 的 `_build_decision_prompt` 中错误地鼓励 LLM 从历史中提取 URL 并传入 `urls` 参数。

**修复**：

| 修复                        | 文件                              | 变更                                                                            |
| --------------------------- | --------------------------------- | ------------------------------------------------------------------------------- |
| ① 确定性工具绕过 LLM        | `react.py`                        | 新增 `_DETERMINISTIC_TOOLS` 集合，7 个工具直接走 `_build_forced_step`，跳过 LLM |
| ② 精简 LLM prompt           | `react.py:_build_decision_prompt` | 从"列出全部 23 个工具"改为仅显示当前工具；`source_tool` 规则明确禁止预填 urls   |
| ③ `_build_forced_step` 增强 | `react.py`                        | python_env_tool 时从历史记录 URL 推导 repo_name 作为默认值                      |

### 效果
- `python_env_tool` 步骤：**LLM 调用耗时从 ~120s → 0s**（不再调用 LLM）
- 其他确定性工具同理：`cleanup_env_tool`、`list_workspace_tool`、`check_repo_tool`、`config_tool`、`stats_tool`、`list_reports_tool`
- LLM prompt 大小从 ~2000 chars（23 工具描述）降为 ~80 chars（仅当前工具）
