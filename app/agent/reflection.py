from typing import List, Optional

from app.core.llm import get_llm
from app.core.logging import get_logger


class ErrorAnalysis:
    def __init__(self, error_type: str = "unknown", explanation: str = "",
                 severity: str = "medium"):
        self.error_type = error_type
        self.explanation = explanation
        self.severity = severity  # low, medium, high

    def to_dict(self) -> dict:
        return {"error_type": self.error_type, "explanation": self.explanation,
                "severity": self.severity}


class FixSuggestion:
    def __init__(self, action: str, args: dict = None, priority: int = 1,
                 confidence: float = 0.5, description: str = ""):
        self.action = action
        self.args = args or {}
        self.priority = priority
        self.confidence = confidence
        self.description = description

    def to_dict(self) -> dict:
        return {"action": self.action, "args": self.args, "priority": self.priority,
                "confidence": self.confidence, "description": self.description}


class ReflectionResult:
    def __init__(self, level: str = "L1", analysis: ErrorAnalysis = None,
                 fix_suggestions: List[FixSuggestion] = None,
                 lesson: str = "", should_replan: bool = False):
        self.level = level
        self.analysis = analysis or ErrorAnalysis()
        self.fix_suggestions = fix_suggestions or []
        self.lesson = lesson
        self.should_replan = should_replan

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "analysis": self.analysis.to_dict(),
            "fix_suggestions": [f.to_dict() for f in self.fix_suggestions],
            "lesson": self.lesson,
            "should_replan": self.should_replan,
        }


class Reflection:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._llm = get_llm()
        self._log = get_logger("reflection")

    def reflect(self, error: str, step_desc: str = "",
                history: str = "", level: str = "L2") -> ReflectionResult:
        if not self._enabled:
            return ReflectionResult(level=level)

        self._log.info(f"Reflecting [{level}]: {error[:100]}")

        # Pattern-based quick analysis
        analysis = self._analyze_pattern(error)

        # Generate fix suggestions
        fixes = self._suggest_fixes(analysis, step_desc)

        # L2+: use LLM for deeper analysis
        if level in ("L2", "L3"):
            try:
                llm_result = self._llm_reflect(error, step_desc, history)
                if llm_result:
                    analysis = llm_result.analysis or analysis
                    fixes = llm_result.fix_suggestions or fixes
            except Exception as e:
                self._log.warning(f"LLM reflection failed: {e}")

        should_replan = (
            analysis.severity == "high"
            or analysis.error_type in ("not_found", "permanent_failure")
            or len(fixes) == 0
        )

        lesson = self._derive_lesson(analysis, error)

        return ReflectionResult(
            level=level, analysis=analysis, fix_suggestions=fixes,
            lesson=lesson, should_replan=should_replan,
        )

    def _analyze_pattern(self, error: str) -> ErrorAnalysis:
        el = error.lower()
        # Specific patterns first (before generic ones like "not found")
        # Execute-specific errors
        if any(kw in el for kw in [
            "未能从仓库中自动检测到可执行命令",
            "no executable command",
            "未检测到入口",
        ]):
            return ErrorAnalysis("no_entry_point",
                                 "仓库中未找到可自动检测的入口文件（.py/.ipynb），需手动指定命令", "medium")
        elif any(kw in el for kw in ["modulenotfound", "no module named",
                                       "importerror", "导入失败"]):
            return ErrorAnalysis("import_error", "Python 包导入/模块未找到，依赖可能未正确安装", "medium")
        elif any(kw in el for kw in ["filenotfound", "no such file", "未找到文件"]):
            return ErrorAnalysis("missing_file", "执行所需的文件或数据不存在", "medium")
        elif any(kw in el for kw in ["cuda", "gpu", "out of memory", "oom"]):
            return ErrorAnalysis("gpu_error", "GPU/CUDA相关错误，可能需切换CPU模式或检查显存", "medium")
        elif any(kw in el for kw in ["命令未找到", "command not found", "not recognized"]):
            return ErrorAnalysis("cmd_not_found", "执行命令未找到，入口脚本可能不存在", "high")
        # Generic patterns
        elif any(kw in el for kw in ["not found", "404", "不存在", "找不到"]):
            return ErrorAnalysis("not_found", "请求的资源或页面未找到", "high")
        elif any(kw in el for kw in ["timeout", "超时", "timed out"]):
            return ErrorAnalysis("timeout", "请求超时，可能是网络问题或目标服务器无响应", "medium")
        elif any(kw in el for kw in ["permission", "denied", "拒绝", "403"]):
            return ErrorAnalysis("permission", "访问被拒绝", "medium")
        # Git auth errors — check before "connection" to avoid misclassification
        elif any(kw in el for kw in [
            "could not read username", "terminal prompts disabled",
            "authentication failed", "fatal: could not read",
        ]):
            return ErrorAnalysis("auth_error", "Git 认证失败，需要设置 GITHUB_TOKEN 或确认仓库为公开", "high")
        elif any(kw in el for kw in ["connection", "network", "网络", "refused"]):
            return ErrorAnalysis("network", "网络连接失败", "medium")
        elif any(kw in el for kw in ["parse", "json", "解析", "格式"]):
            return ErrorAnalysis("parse_error", "数据解析失败，返回格式异常", "low")
        elif any(kw in el for kw in ["empty", "null", "无结果", "none"]):
            return ErrorAnalysis("empty_result", "查询返回了空结果", "medium")
        elif any(kw in el for kw in ["unknown tool", "no tool"]):
            return ErrorAnalysis("unknown_tool", "调用了不存在的工具", "high")
        # Setup/environment errors
        elif any(kw in el for kw in ["pip", "安装失败", "install failed", "pip install"]):
            return ErrorAnalysis("pip_failed", "pip 依赖安装失败", "medium")
        elif any(kw in el for kw in ["venv", "虚拟环境", "virtual environment"]):
            return ErrorAnalysis("venv_failed", "虚拟环境创建或使用失败", "medium")
        elif any(kw in el for kw in ["requirements", "依赖文件", "未找到.*文件"]):
            return ErrorAnalysis("missing_requirements", "未找到依赖配置文件", "low")
        elif any(kw in el for kw in ["import", "导入", "no module"]):
            return ErrorAnalysis("import_error", "Python 包导入失败，依赖可能未正确安装", "medium")
        elif any(kw in el for kw in ["no repo", "没有.*仓库", "多个仓库"]):
            return ErrorAnalysis("ambiguous_repo", "仓库选择不明确，需要用户指定", "low")
        else:
            return ErrorAnalysis("unknown", f"未分类错误: {error[:100]}", "medium")

    def _suggest_fixes(self, analysis: ErrorAnalysis, step_desc: str) -> List[FixSuggestion]:
        suggestions = {
            "not_found": [
                FixSuggestion("search_tool",
                              {"query": step_desc, "source": "arxiv"},
                              1, 0.8, "切换到 arXiv 学术搜索"),
                FixSuggestion("search_tool",
                              {"query": step_desc, "source": "web"},
                              2, 0.6, "使用通用网页搜索重试"),
                FixSuggestion("fetch_tool",
                              {"url": ""}, 3, 0.3, "尝试直接访问已知论文网站"),
            ],
            "timeout": [
                FixSuggestion("fetch_tool", {"url": "", "timeout": 60},
                              1, 0.6, "增加超时时间重试"),
                FixSuggestion("search_tool", {"source": "simple"},
                              2, 0.5, "使用更简单的搜索方式"),
            ],
            "network": [
                FixSuggestion("search_tool", {"source": "wikipedia"},
                              1, 0.7, "尝试 Wikipedia 搜索"),
                FixSuggestion("fetch_tool", {}, 2, 0.4, "等待片刻后重试"),
            ],
            "empty_result": [
                FixSuggestion("search_tool",
                              {"query": step_desc, "source": "web"},
                              1, 0.7, "扩大搜索范围"),
                FixSuggestion("search_tool",
                              {}, 2, 0.4, "缩短搜索关键词重试"),
            ],
            # Setup/environment fixes
            "pip_failed": [
                FixSuggestion("setup_tool",
                              {"repo_name": "", "python": ""},
                              1, 0.8, "去掉版本号限制后重试安装（如 tensorflow==1.15.4 → tensorflow）"),
                FixSuggestion("setup_tool",
                              {}, 2, 0.5, "重新创建venv后逐个安装依赖包"),
                FixSuggestion("setup_tool",
                              {"python": "python3.8"}, 3, 0.4,
                              "尝试使用 Python 3.8 创建虚拟环境（兼容旧版包）"),
            ],
            "venv_failed": [
                FixSuggestion("setup_tool",
                              {}, 1, 0.6, "删除旧venv后重新创建"),
                FixSuggestion("setup_tool",
                              {"python": ""}, 2, 0.4, "尝试使用其他Python解释器"),
            ],
            "missing_requirements": [
                FixSuggestion("setup_tool",
                              {}, 1, 0.6, "尝试从setup.py/pyproject.toml安装"),
                FixSuggestion("fetch_tool",
                              {"url": ""}, 2, 0.3, "检查仓库README中的手动安装说明"),
            ],
            "import_error": [
                FixSuggestion("setup_tool",
                              {}, 1, 0.6, "重新安装失败的依赖包"),
                FixSuggestion("setup_tool",
                              {"repo_name": ""}, 2, 0.4, "检查Python版本兼容性后重试"),
            ],
            "ambiguous_repo": [
                FixSuggestion("clone_tool",
                              {"repo_url": ""}, 1, 0.5, "先确认/克隆目标仓库"),
                FixSuggestion("setup_tool",
                              {"repo_name": ""}, 2, 0.7, "指定仓库名后重试"),
            ],
            "no_entry_point": [
                FixSuggestion("execute_tool",
                              {"script": ""}, 1, 0.7,
                              "查看仓库文件列表，指定正确的入口脚本名（如 denoising.ipynb）"),
                FixSuggestion("execute_tool",
                              {"command": ""}, 2, 0.5,
                              "直接指定完整执行命令"),
            ],
            # Execute error fixes
            "missing_file": [
                FixSuggestion("execute_tool",
                              {"command": ""}, 1, 0.5, "检查数据文件路径后重试"),
                FixSuggestion("fetch_tool",
                              {"url": ""}, 2, 0.3, "查看README了解数据准备步骤"),
            ],
            "gpu_error": [
                FixSuggestion("execute_tool",
                              {"command": ""}, 1, 0.6, "尝试添加 --device cpu 参数重试"),
                FixSuggestion("execute_tool",
                              {}, 2, 0.3, "检查CUDA/cuDNN安装或使用CPU"),
            ],
            "auth_error": [
                FixSuggestion("clone_tool",
                              {"repo_url": ""}, 1, 0.8,
                              "使用 GITHUB_TOKEN 环境变量重试克隆"),
                FixSuggestion("clone_tool",
                              {"repo_url": ""}, 2, 0.4,
                              "确认仓库为公开仓库，或设置有效的 GitHub 凭据"),
            ],
            "cmd_not_found": [
                FixSuggestion("execute_tool",
                              {"script": ""}, 1, 0.6, "重新分析仓库入口文件，指定正确的脚本名"),
                FixSuggestion("setup_tool",
                              {}, 2, 0.3, "仓库结构异常，可能需要先配置环境"),
            ],
        }
        return suggestions.get(analysis.error_type, [
            FixSuggestion("search_tool",
                          {"query": step_desc}, 1, 0.5, "重新搜索"),
        ])

    def _llm_reflect(self, error: str, step_desc: str, history: str) -> Optional[ReflectionResult]:
        prompt = f"""分析以下执行错误并提供修复方案。

步骤: {step_desc}
错误: {error}
历史: {history or "无"}

输出 JSON:
{{
    "error_type": "错误类别",
    "explanation": "通俗解释",
    "severity": "low/medium/high",
    "fix_suggestions": [{{"action": "工具名", "args": {{}}, "priority": 1, "confidence": 0.8, "description": "方案描述"}}],
    "lesson": "经验教训"
}}"""
        resp = self._llm.generate_structured(prompt)
        analysis = ErrorAnalysis(
            error_type=resp.get("error_type", "unknown"),
            explanation=resp.get("explanation", ""),
            severity=resp.get("severity", "medium"),
        )
        fixes = [
            FixSuggestion(
                action=f.get("action", ""),
                args=f.get("args", {}),
                priority=f.get("priority", 1),
                confidence=f.get("confidence", 0.5),
                description=f.get("description", ""),
            )
            for f in resp.get("fix_suggestions", [])
        ]
        return ReflectionResult(
            level="L2", analysis=analysis, fix_suggestions=fixes,
            lesson=resp.get("lesson", ""),
        )

    def _derive_lesson(self, analysis: ErrorAnalysis, error: str) -> str:
        lessons = {
            "auth_error": "GitHub 认证失败，请确保设置了 GITHUB_TOKEN 环境变量，或使用公开仓库地址",
            "not_found": f"搜索 '{error[:50]}...' 未找到结果，下次可以尝试不同来源或更通用的搜索词",
            "timeout": "网络请求超时，考虑增加超时时间或检查网络连接",
            "network": "网络连接有问题，检查网络状态并使用备用数据源",
            "empty_result": "查询返回空结果，尝试调整搜索关键词或范围",
            "parse_error": "数据格式异常，需要更健壮的解析逻辑",
            "unknown_tool": "工具调用错误，检查工具注册表",
            "pip_failed": "pip安装失败，可能是网络问题或包不兼容，尝试单独安装或使用镜像源",
            "venv_failed": "虚拟环境创建失败，检查Python路径是否正确，或删除旧venv后重试",
            "missing_requirements": "未找到requirements.txt，尝试从setup.py/pyproject.toml安装或查看README手动说明",
            "import_error": "包导入失败，可能是版本不兼容或缺少系统依赖",
            "no_entry_point": "该仓库可能使用Jupyter notebooks或非标准入口文件，需手动指定脚本名",
            "ambiguous_repo": "workspace中有多个仓库，需要明确指定要配置的仓库名",
        }
        return lessons.get(analysis.error_type, f"遇到错误: {analysis.explanation}，需进一步分析")
