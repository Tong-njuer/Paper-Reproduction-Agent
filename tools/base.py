# ============================================================
# Tool 基类定义
# ============================================================
"""
工具基类定义。

设计思路：
- 所有工具必须继承 Tool 基类
- 统一的接口定义
- 支持异步执行
- 详细的参数和结果定义
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ParameterType(Enum):
    """参数类型枚举"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    CODE = "code"                     # 代码类型
    FILE_PATH = "file_path"          # 文件路径类型


@dataclass
class ToolParameter:
    """
    工具参数定义

    描述一个工具参数的类型和约束。
    """
    name: str                          # 参数名称
    description: str                   # 参数描述
    param_type: ParameterType          # 参数类型
    required: bool = True             # 是否必需
    default: Any = None               # 默认值
    # 对于array/object类型，定义元素类型
    items: dict[str, Any] | None = None
    # 约束条件
    min_value: float | None = None   # 最小值
    max_value: float | None = None   # 最大值
    pattern: str | None = None       # 正则表达式（string类型）
    enum_values: list[Any] | None = None  # 枚举值


@dataclass
class ToolResult:
    """
    工具执行结果

    所有工具执行后都返回此类型。
    """
    success: bool                      # 是否成功
    output: str                        # 输出内容
    error: str | None = None          # 错误信息
    # 执行统计
    execution_time_ms: float | None = None  # 执行耗时
    # 附加数据
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success_result(
        cls,
        output: str,
        execution_time_ms: float | None = None,
        **metadata
    ) -> "ToolResult":
        """创建成功结果"""
        return cls(
            success=True,
            output=output,
            metadata=metadata,
            execution_time_ms=execution_time_ms,
        )

    @classmethod
    def error_result(
        cls,
        error: str,
        output: str = "",
        execution_time_ms: float | None = None,
        **metadata
    ) -> "ToolResult":
        """创建错误结果"""
        return cls(
            success=False,
            output=output,
            error=error,
            metadata=metadata,
            execution_time_ms=execution_time_ms,
        )


class Tool(ABC):
    """
    工具抽象基类

    所有Agent工具必须继承此类。
    定义了工具的基本接口。

    设计原则：
    - 工具是独立的执行单元
    - 支持异步执行
    - 每次执行都有详细日志
    - 失败时提供有意义的错误信息

    使用示例：
    ```python
    class MyTool(Tool):
        @property
        def name(self) -> str:
            return "my_tool"

        @property
        def description(self) -> str:
            return "执行某个操作"

        @property
        def parameters(self) -> list[ToolParameter]:
            return [
                ToolParameter(
                    name="input",
                    description="输入数据",
                    param_type=ParameterType.STRING,
                )
            ]

        async def execute(self, input: str, **kwargs) -> ToolResult:
            # 实际执行逻辑
            return ToolResult.success_result("done")
    ```
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        工具名称

        用于注册和通过名称调用。
        应使用snake_case命名。
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        工具描述

        用于LLM理解工具用途。
        应该清晰描述工具的功能和使用场景。
        """
        pass

    @property
    def parameters(self) -> list[ToolParameter]:
        """
        工具参数定义

        返回工具需要的参数列表。
        默认返回空列表（无参数）。
        """
        return []

    @property
    def examples(self) -> list[dict[str, Any]]:
        """
        使用示例

        返回工具的使用示例。
        用于生成提示和文档。
        """
        return []

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        执行工具

        主入口方法，执行具体的工具逻辑。

        Args:
            **kwargs: 参数（由parameters定义）

        Returns:
            ToolResult: 执行结果
        """
        pass

    def validate_params(self, **kwargs) -> tuple[bool, str | None]:
        """
        验证参数

        在执行前验证参数是否合法。
        默认实现检查必需参数。

        Args:
            **kwargs: 参数

        Returns:
            (is_valid, error_message)
        """
        # 检查必需参数
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return False, f"Missing required parameter: {param.name}"

        # 检查类型（简化实现）
        for param in self.parameters:
            if param.name in kwargs:
                value = kwargs[param.name]
                if not self._validate_type(value, param):
                    return False, f"Invalid type for {param.name}"

        return True, None

    def _validate_type(self, value: Any, param: ToolParameter) -> bool:
        """验证参数类型"""
        type_mapping = {
            ParameterType.STRING: str,
            ParameterType.INTEGER: int,
            ParameterType.FLOAT: (int, float),
            ParameterType.BOOLEAN: bool,
            ParameterType.ARRAY: list,
            ParameterType.OBJECT: dict,
        }

        expected = type_mapping.get(param.param_type)
        if expected is None:
            return True  # CODE, FILE_PATH 等不检查

        return isinstance(value, expected)

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"
