# Tool 实现接口规范

## 概述

本文档定义了在 Agent 框架中实现 Tool 的规范和要求。Tool 是 Agent 执行具体操作的媒介，所有 Tool 必须严格遵循本规范以确保与框架的无缝对接。

---

## 1. 文件结构

```text
app/tools/
├── __init__.py          # 工具基类和注册表（已存在）
├── paper_tool.py        # 论文读取与结构化抽取
├── source_tool.py       # 源码候选发现/下载/完整性分析
├── repo_index_tool.py   # 仓库索引、检索、文件读取
├── sandbox_tool.py      # 沙箱工作区与环境准备
├── test_tool.py         # 静态检查/单测/烟雾测试/指标对比
├── doc_tool.py          # 文档写入与复现报告生成
├── code_tool.py         # 代码执行工具
├── wiki_tool.py         # 文档搜索工具
├── schedule_tool.py     # 计划管理工具
└── learning_path_tool.py # 学习路径工具
```

---

## 2. 基类定义

所有 Tool 必须继承 `BaseTool`，位于 `app/tools/__init__.py`：

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any, Dict, Optional

class ToolResult(BaseModel):
    """Tool 执行结果的标准格式"""
    success: bool                              # 是否成功
    output: Optional[str] = None              # 成功时的输出
    error: Optional[str] = None               # 失败时的错误信息
    metadata: Dict[str, Any] = {}             # 额外的元数据

class BaseTool(ABC):
    """所有 Tool 的抽象基类"""

    name: str = "base_tool"                  # 工具唯一标识名
    description: str = "Base tool"            # 工具描述（用于 LLM 理解）

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """执行工具的核心方法"""
        pass

    def validate_args(self, **kwargs) -> bool:
        """验证输入参数（可选重写）"""
        return True
```

---

## 3. Tool 实现模板

```python
from app.tools import BaseTool, ToolResult

class CodeTool(BaseTool):
    """
    代码执行工具

    Attributes:
        name: 工具名称，必须唯一
        description: 描述，用于 LLM 理解工具用途
    """

    name = "code_tool"
    description = "Execute Python/Shell code and return results"

    def execute(self, **kwargs) -> ToolResult:
        """
        执行代码

        Args:
            command: 要执行的命令
            timeout: 超时时间（秒），可选

        Returns:
            ToolResult: 包含执行结果的标准化对象
        """
        # 1. 提取参数
        command = kwargs.get("command", "")
        timeout = kwargs.get("timeout", 30)

        # 2. 参数验证
        if not command:
            return ToolResult(
                success=False,
                error="Missing required argument: command"
            )

        # 3. 执行逻辑
        try:
            import subprocess
            result = subprocess.run(
                command,
                shell=True,
                timeout=timeout,
                capture_output=True,
                text=True
            )

            # 4. 返回结果
            if result.returncode == 0:
                return ToolResult(
                    success=True,
                    output=result.stdout,
                    metadata={
                        "returncode": result.returncode,
                        "stderr": result.stderr
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    output=result.stdout,
                    error=f"Command failed with returncode {result.returncode}: {result.stderr}"
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Command timed out after {timeout} seconds"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Unexpected error: {str(e)}"
            )
```

---

## 4. 参数传递机制

ReAct 引擎通过 `action_args` 字典传递参数：

```python
# ReAct 决策返回的格式
{
    "thought": "需要执行Python代码来测试环境",
    "action": "code_tool",           # 工具名称（必须与注册表中一致）
    "action_args": {                  # 传递给 tool.execute() 的参数
        "command": "python --version",
        "timeout": 30
    }
}
```

框架调用方式：

```python
tool = get_tool(action_name)          # 从注册表获取工具
result = tool.execute(**action_args)  # 解包传递参数
```

---

## 5. 工具注册

实现完 Tool 后，必须注册到 `TOOL_REGISTRY`：

```python
# app/tools/__init__.py

from app.tools.code_tool import CodeTool

TOOL_REGISTRY: Dict[str, BaseTool] = {
    "code_tool": CodeTool(),           # 注册新工具
    "wiki_tool": WikiToolPlaceholder(),
    "schedule_tool": ScheduleToolPlaceholder(),
    "learning_path_tool": LearningPathToolPlaceholder(),
}
```

---

## 6. 返回值规范

### 6.1 成功情况

```python
ToolResult(
    success=True,
    output="命令输出内容",
    metadata={"key": "value"}  # 可选
)
```

### 6.2 失败情况

```python
ToolResult(
    success=False,
    error="错误描述信息"
)
```

### 6.3 重要提示

- `success=True` 时 `error` 应为 `None`
- `success=False` 时 `output` 可选（通常为 `None`）
- 避免返回空字符串作为错误信息

---

## 7. 已有工具占位符

| 工具名称             | 描述                             | 状态   |
| -------------------- | -------------------------------- | ------ |
| `paper_tool`         | 论文读取与复现要素抽取           | 已实现 |
| `source_tool`        | 源码候选发现、下载与完整性分析   | 已实现 |
| `repo_index_tool`    | 仓库目录索引、文本检索、文件读取 | 已实现 |
| `sandbox_tool`       | 运行工作区创建与环境准备         | 已实现 |
| `test_tool`          | 测试执行与指标对比               | 已实现 |
| `doc_tool`           | 文档与复现报告生成               | 已实现 |
| `code_tool`          | 执行代码                         | 已实现 |
| `wiki_tool`          | 文档搜索                         | 已实现 |
| `schedule_tool`      | 计划管理                         | 已实现 |
| `learning_path_tool` | 学习路径                         | 已实现 |

---

## 8. 单元测试

实现 Tool 后，建议在 `tests/` 目录下添加测试：

```python
# tests/test_code_tool.py
import pytest
from app.tools.code_tool import CodeTool

def test_code_tool_success():
    tool = CodeTool()
    result = tool.execute(command="echo 'hello'")

    assert result.success is True
    assert "hello" in result.output

def test_code_tool_failure():
    tool = CodeTool()
    result = tool.execute(command="exit 1")

    assert result.success is False
    assert result.error is not None
```

---

## 9. LLM Prompt 中的工具描述

LLM 通过工具描述理解每个工具的能力。在 `app/agent/react.py` 的 `_build_decision_prompt` 中会传递：

```text
Available Tools:
paper_tool, source_tool, repo_index_tool, sandbox_tool, test_tool, doc_tool,
code_tool, wiki_tool, schedule_tool, learning_path_tool
```

因此 `BaseTool.description` 必须清晰描述：

- 工具能做什么
- 需要什么参数
- 返回什么结果

---

## 10. 错误处理规范

```python
# 推荐：使用 try-except 捕获所有可能的异常
def execute(self, **kwargs) -> ToolResult:
    try:
        # 业务逻辑
        return ToolResult(success=True, output="...")
    except SpecificException as e:
        return ToolResult(success=False, error=f"Specific error: {e}")
    except Exception as e:
        # 避免裸 except，但 Tool 中可以接受
        return ToolResult(success=False, error=f"Unexpected error: {str(e)}")
```

---

## 11. 示例：完整工具实现

参考 `app/tools/code_tool.py` 的占位符实现，真正的实现需要：

1. 继承 `BaseTool`
2. 设置 `name` 和 `description`
3. 实现 `execute` 方法
4. 返回 `ToolResult`
5. 注册到 `TOOL_REGISTRY`

---

## 12. 新工具 Action 参数模板

为提升 ReAct 决策稳定性，建议按以下模板生成 `action_args`：

```json
{
    "paper_tool": {"action": "extract", "text": "..."},
    "source_tool": {"action": "analyze_source", "source_path": "..."},
    "repo_index_tool": {"action": "search_text", "root_path": "...", "query": "..."},
    "sandbox_tool": {"action": "detect_environment", "project_path": "..."},
    "test_tool": {"action": "run_unit_tests", "project_path": "..."},
    "doc_tool": {"action": "generate_repro_report", "output_path": "...", "goal": "..."}
}
```

说明：

- `paper_tool/source_tool/repo_index_tool/sandbox_tool/test_tool/doc_tool/schedule_tool` 都是多 action 工具，务必显式传 `action`。
- `code_tool/wiki_tool/learning_path_tool` 可直接传主参数。

---

## 13. 本地安装与测试

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

UI 启动：

```bash
streamlit run app/streamlit_app.py
```
