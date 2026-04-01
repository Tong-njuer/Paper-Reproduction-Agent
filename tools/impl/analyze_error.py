# ============================================================
# AnalyzeErrorTool - 错误分析工具
# ============================================================
"""
analyze_error 工具实现。

功能：
- 分析错误信息
- 定位错误位置
- 提供修复建议
- 解释错误原因
"""

from typing import Any

from tools.base import Tool, ToolParameter, ParameterType, ToolResult


class AnalyzeErrorTool(Tool):
    """
    错误分析工具

    分析代码执行中的错误，提供：
    - 错误类型和原因
    - 错误位置定位
    - 修复建议
    - 相关知识点
    """

    @property
    def name(self) -> str:
        return "analyze_error"

    @property
    def description(self) -> str:
        return (
            "分析代码错误信息，定位问题原因，提供修复建议。"
            "适用于运行时错误、编译错误等。"
            "返回错误分析和解决建议。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="error_message",
                description="错误信息",
                param_type=ParameterType.STRING,
                required=True,
            ),
            ToolParameter(
                name="code",
                description="相关代码（可选）",
                param_type=ParameterType.CODE,
                required=False,
            ),
            ToolParameter(
                name="language",
                description="编程语言",
                param_type=ParameterType.STRING,
                required=False,
                default="python",
            ),
            ToolParameter(
                name="context",
                description="额外的上下文信息",
                param_type=ParameterType.STRING,
                required=False,
            ),
        ]

    @property
    def examples(self) -> list[dict[str, Any]]:
        return [
            {
                "description": "分析Python错误",
                "error_message": "IndexError: list index out of range",
                "language": "python",
            },
        ]

    async def execute(
        self,
        error_message: str,
        code: str | None = None,
        language: str = "python",
        context: str | None = None,
        **kwargs
    ) -> ToolResult:
        """
        分析错误

        Args:
            error_message: 错误信息
            code: 相关代码
            language: 编程语言
            context: 额外上下文

        Returns:
            ToolResult: 错误分析结果
        """
        try:
            # 分析错误
            analysis = await self._analyze_error(
                error_message=error_message,
                code=code,
                language=language,
                context=context,
            )

            return ToolResult.success_result(
                output=analysis,
                metadata={
                    "language": language,
                    "error_type": self._classify_error(error_message),
                },
            )

        except Exception as e:
            return ToolResult.error_result(
                error=f"Analysis error: {str(e)}"
            )

    async def _analyze_error(
        self,
        error_message: str,
        code: str | None,
        language: str,
        context: str | None,
    ) -> str:
        """
        执行实际的错误分析

        简化实现：返回通用分析
        TODO: 使用LLM进行更智能的分析
        """
        error_type = self._classify_error(error_message)

        analysis_parts = [
            f"## 错误分析报告",
            f"",
            f"### 错误类型",
            f"{error_type}",
            f"",
            f"### 错误信息",
            f"```",
            f"{error_message}",
            f"```",
            f"",
        ]

        # 根据错误类型添加建议
        suggestions = self._get_suggestions(error_type)
        if suggestions:
            analysis_parts.extend([
                f"### 可能的原因",
                *suggestions,
                f"",
            ])

        # 添加代码位置（如果能解析）
        location = self._extract_location(error_message)
        if location:
            analysis_parts.extend([
                f"### 错误位置",
                f"{location}",
                f"",
            ])

        analysis_parts.extend([
            f"### 修复建议",
            f"1. 检查错误信息中的具体描述",
            f"2. 查看错误位置附近的代码",
            f"3. 确保输入数据符合预期格式",
            f"4. 添加适当的错误处理",
        ])

        return "\n".join(analysis_parts)

    def _classify_error(self, error_message: str) -> str:
        """分类错误类型"""
        error_lower = error_message.lower()

        if "index" in error_lower and "out of range" in error_lower:
            return "IndexError - 索引越界"
        elif "key" in error_lower and "not found" in error_lower:
            return "KeyError - 键不存在"
        elif "type" in error_lower and "error" in error_lower:
            return "TypeError - 类型错误"
        elif "attribute" in error_lower:
            return "AttributeError - 属性错误"
        elif "syntax" in error_lower:
            return "SyntaxError - 语法错误"
        elif "indentation" in error_lower:
            return "IndentationError - 缩进错误"
        elif "name" in error_lower and "not defined" in error_lower:
            return "NameError - 名称未定义"
        elif "import" in error_lower:
            return "ImportError - 导入错误"
        elif "value" in error_lower:
            return "ValueError - 值错误"
        else:
            return "UnknownError - 未知错误"

    def _extract_location(self, error_message: str) -> str | None:
        """提取错误位置"""
        # 尝试匹配行号
        import re
        pattern = r'line (\d+)'
        match = re.search(pattern, error_message)
        if match:
            return f"第 {match.group(1)} 行"
        return None

    def _get_suggestions(self, error_type: str) -> list[str]:
        """获取针对特定错误类型的建议"""
        suggestions_map = {
            "IndexError": [
                "- 数组或列表索引超出范围",
                "- 可能访问了空容器的元素",
                "- 循环索引计算错误",
            ],
            "KeyError": [
                "- 字典中不存在指定的键",
                "- 检查键名是否拼写正确",
                "- 使用 get() 方法提供默认值",
            ],
            "TypeError": [
                "- 操作使用了不兼容的类型",
                "- 函数参数类型不匹配",
                "- 尝试对不可迭代对象进行迭代",
            ],
            "AttributeError": [
                "- 对象没有该属性或方法",
                "- 检查属性名拼写",
                "- 确认对象类型是否正确",
            ],
        }

        # 提取基础错误类型
        base_type = error_type.split(" - ")[0] if " - " in error_type else error_type
        return suggestions_map.get(base_type, [])
