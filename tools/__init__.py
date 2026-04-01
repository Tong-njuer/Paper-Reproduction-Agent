# ============================================================
# tools/ 模块
# ============================================================
"""
工具系统模块。

设计原则：
- 统一的Tool接口
- 插件式工具注册
- 详细的执行日志

核心组件：
- base.py: Tool基类定义
- registry.py: 工具注册器
- result.py: 工具执行结果

内置工具（impl/）：
- run_code: 代码执行
- generate_tests: 测试生成
- analyze_error: 错误分析
- code_linter: 代码检查
- design_analyzer: 设计分析
- project_planner: 项目规划
"""

from tools.base import Tool, ToolParameter, ToolResult
from tools.registry import ToolRegistry

__all__ = [
    "Tool",
    "ToolParameter",
    "ToolResult",
    "ToolRegistry",
]
