# ============================================================
# 反思模块
# ============================================================
# 用于错误分析和策略调整的自我反思模块。
# 实现三层反思能力:
#   L1: 错误解释
#   L2: 修复建议
#   L3: 长期策略优化
#
# Console Output:
#   - Error analysis
#   - Reflection insights
#   - Strategy adjustments
# ============================================================

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.core.llm import get_llm
from app.core.context import ExecutionContext


class ErrorAnalysis(BaseModel):
    """
    结构化的错误分析。

    Attributes:
        error_type: 错误类别（如 'missing_dependency', 'syntax_error'）
        error_subtype: 具体子类型
        explanation: 通俗易懂的错误解释
        severity: 严重程度（low, medium, high）
    """
    error_type: str = "unknown"
    error_subtype: str = ""
    explanation: str = ""
    severity: str = "medium"


class FixSuggestion(BaseModel):
    """
    错误修复建议。

    Attributes:
        action: 建议的行动（工具名称）
        args: 行动参数
        priority: 尝试顺序（1 = 最高）
        confidence: 此方案可行的置信度（0-1）
    """
    action: str
    args: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 1
    confidence: float = 0.5


class ReflectionResult(BaseModel):
    """
    完整的反思结果。

    Attributes:
        level: 反思级别（L1, L2, L3）
        analysis: 错误分析
        fix_suggestions: 可能的修复方案列表
        lesson: 供将来参考的经验教训
        should_replan: 是否应触发重新规划
    """
    level: str = "L1"
    analysis: Optional[ErrorAnalysis] = None
    fix_suggestions: List[FixSuggestion] = Field(default_factory=list)
    lesson: str = ""
    should_replan: bool = False


class Reflexion:
    """
    自我反思模块。

    分析失败和错误:
    1. 解释出了什么问题（L1）
    2. 建议如何修复（L2）
    3. 为未来学习（L3）

    Attributes:
        llm: 用于分析的 LLM 接口
        enabled: 是否启用反思功能
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize Reflexion module.

        Args:
            enabled: Whether to enable reflexion features
        """
        self.llm = get_llm()
        self.enabled = enabled
        print(f"[REFLECT] Reflexion initialized (enabled: {enabled})")

    def reflect(
        self,
        error: str,
        context: ExecutionContext,
        level: str = "L2",
    ) -> ReflectionResult:
        """
        对错误或失败进行反思。

        Args:
            error: 错误消息或观察
            context: 当前执行上下文
            level: 反思级别（L1, L2 或 L3）

        Returns:
            ReflectionResult: 结构化的反思输出
        """
        if not self.enabled:
            print("[!]  Reflexion disabled, returning empty result")
            return ReflectionResult(level=level)

        print(f"\n[REFLECT] Reflexion: Analyzing error at level {level}")
        print(f"   Error: {error[:100]}...")

        # Build analysis prompt
        prompt = self._build_reflection_prompt(error, context, level)

        if self.llm.is_available():
            try:
                response = self.llm.generate_structured(prompt)
                result = self._parse_reflection_response(response, level)
            except Exception as e:
                print(f"[!]  LLM reflection failed: {e}")
                result = self._create_fallback_reflection(error, level)
        else:
            result = self._create_demo_reflection(error, level)

        # Print reflection
        self._print_reflection(result)

        return result

    def analyze_error_type(self, error: str) -> ErrorAnalysis:
        """
        Analyze error type and generate structured analysis.

        Args:
            error: The error message

        Returns:
            ErrorAnalysis: Structured error analysis
        """
        error_lower = error.lower()

        # Simple pattern matching for common error types
        if "missing" in error_lower or "not found" in error_lower:
            error_type = "missing_dependency"
            explanation = "A required resource or dependency was not found"
        elif "syntax" in error_lower or "parse" in error_lower:
            error_type = "syntax_error"
            explanation = "There is a syntax error in the code or input"
        elif "timeout" in error_lower or "timed out" in error_lower:
            error_type = "timeout"
            explanation = "Operation timed out - may be too slow or hanging"
        elif "permission" in error_lower or "denied" in error_lower:
            error_type = "permission_error"
            explanation = "Permission was denied for the operation"
        elif "memory" in error_lower or "out of memory" in error_lower:
            error_type = "resource_error"
            explanation = "System ran out of memory"
        else:
            error_type = "unknown"
            explanation = "An unknown error occurred"

        return ErrorAnalysis(
            error_type=error_type,
            error_subtype="",
            explanation=explanation,
            severity="medium",
        )

    def get_fix_suggestions(self, error: str, error_type: str) -> List[FixSuggestion]:
        """
        Generate fix suggestions based on error type.

        Args:
            error: The error message
            error_type: Categorized error type

        Returns:
            List of FixSuggestion objects
        """
        suggestions = []

        if error_type == "missing_dependency":
            suggestions = [
                FixSuggestion(
                    action="code_tool",
                    args={"command": "pip install missing_package"},
                    priority=1,
                    confidence=0.8,
                ),
                FixSuggestion(
                    action="wiki_tool",
                    args={"query": "installation instructions"},
                    priority=2,
                    confidence=0.6,
                ),
            ]
        elif error_type == "syntax_error":
            suggestions = [
                FixSuggestion(
                    action="code_tool",
                    args={"command": "python -m py_compile"},
                    priority=1,
                    confidence=0.7,
                ),
            ]
        elif error_type == "timeout":
            suggestions = [
                FixSuggestion(
                    action="schedule_tool",
                    args={"action": "increase_timeout"},
                    priority=1,
                    confidence=0.6,
                ),
            ]
        else:
            suggestions = [
                FixSuggestion(
                    action="code_tool",
                    args={"command": "echo 'Retry with debugging'"},
                    priority=1,
                    confidence=0.4,
                ),
            ]

        return suggestions

    def _build_reflection_prompt(
        self,
        error: str,
        context: ExecutionContext,
        level: str,
    ) -> str:
        """
        Build prompt for reflection analysis.

        Args:
            error: The error
            context: Execution context
            level: Reflection level

        Returns:
            str: Formatted prompt
        """
        recent = context.steps[-5:] if context.steps else []
        history = "\n".join(
            f"- {s.action}: {s.observation[:50]}" for s in recent
        ) if recent else "No history"

        prompt_level_instruction = {
            "L1": "Explain what went wrong in simple terms",
            "L2": "Explain what went wrong AND suggest how to fix it",
            "L3": "Explain what went wrong, how to fix it, AND what to learn for the future",
        }

        prompt = f"""You are a self-reflection agent. Analyze the following error and provide insights.

Current Goal: {context.goal}

Error:
{error}

Recent History:
{history}

Your reflection task ({level}):
{prompt_level_instruction.get(level, 'Provide analysis')}

Output format (JSON):
{{
    "analysis": {{
        "error_type": "category of error",
        "error_subtype": "specific type",
        "explanation": "plain language explanation",
        "severity": "low/medium/high"
    }},
    "fix_suggestions": [
        {{
            "action": "tool_name",
            "args": {{"arg": "value"}},
            "priority": 1,
            "confidence": 0.8
        }}
    ],
    "lesson": "What to learn from this for future attempts",
    "should_replan": true/false
}}
"""
        return prompt

    def _parse_reflection_response(
        self,
        response: Dict[str, Any],
        level: str,
    ) -> ReflectionResult:
        """
        Parse LLM reflection response.

        Args:
            response: LLM JSON response
            level: Reflection level

        Returns:
            ReflectionResult: Parsed result
        """
        analysis_data = response.get("analysis", {})
        fix_data = response.get("fix_suggestions", [])

        analysis = ErrorAnalysis(
            error_type=analysis_data.get("error_type", "unknown"),
            error_subtype=analysis_data.get("error_subtype", ""),
            explanation=analysis_data.get("explanation", ""),
            severity=analysis_data.get("severity", "medium"),
        )

        fixes = [
            FixSuggestion(
                action=f.get("action", "unknown"),
                args=f.get("args", {}),
                priority=f.get("priority", 1),
                confidence=f.get("confidence", 0.5),
            )
            for f in fix_data
        ]

        return ReflectionResult(
            level=level,
            analysis=analysis,
            fix_suggestions=fixes,
            lesson=response.get("lesson", ""),
            should_replan=response.get("should_replan", False),
        )

    def _create_fallback_reflection(self, error: str, level: str) -> ReflectionResult:
        """
        Create fallback reflection when LLM unavailable.

        Args:
            error: Error message
            level: Reflection level

        Returns:
            ReflectionResult: Simple fallback
        """
        analysis = self.analyze_error_type(error)
        fixes = self.get_fix_suggestions(error, analysis.error_type)

        return ReflectionResult(
            level=level,
            analysis=analysis,
            fix_suggestions=fixes,
            lesson=f"遇到 {analysis.error_type} 错误，需要根据具体情况处理",
            should_replan=True,
        )

    def _create_demo_reflection(self, error: str, level: str) -> ReflectionResult:
        """Create demo reflection for demonstration."""
        return ReflectionResult(
            level=level,
            analysis=ErrorAnalysis(
                error_type="demo_mode",
                explanation="[DEMO] 演示模式下的反思",
                severity="low",
            ),
            fix_suggestions=[],
            lesson="[DEMO] 这是演示模式的反思结果",
            should_replan=False,
        )

    def _print_reflection(self, result: ReflectionResult) -> None:
        """
        Print reflection result to console.

        Args:
            result: The reflection result
        """
        print("\n" + "=" * 50)
        print(f"[REFLECT] Reflection Result ({result.level})")
        print("=" * 50)

        if result.analysis:
            print(f"\n[PIN] Analysis:")
            print(f"   Type:      {result.analysis.error_type}")
            print(f"   Severity: {result.analysis.severity}")
            print(f"   Explain:  {result.analysis.explanation}")

        if result.fix_suggestions:
            print(f"\n[FIX] Fix Suggestions:")
            for i, fix in enumerate(result.fix_suggestions[:3], 1):
                print(f"   {i}. [{fix.action}] Confidence: {fix.confidence:.0%}")
                print(f"      Args: {fix.args}")

        if result.lesson:
            print(f"\n[LEARN] Lesson: {result.lesson}")

        if result.should_replan:
            print(f"\n[!]  Recommendation: Replan suggested")

        print("=" * 50 + "\n")
