"""
ReportTool — 汇总所有步骤结果，生成复现完成报告。

此工具由编排器直接调用，不经过 ReAct 决策。
"""

from app.tools import BaseTool, ToolResult


class ReportTool(BaseTool):
    """汇总所有步骤结果，生成复现完成报告。此工具由编排器直接调用，不经过ReAct决策。"""
    name = "report_tool"
    description = "汇总复现报告。参数: goal(目标), steps(步骤结果列表), paper_info(论文信息), source_url(源码地址), errors(错误列表), paper_content(执行内容)"

    def execute(self, goal: str = "", steps: list = None, paper_info: dict = None,
                source_url: str = "", errors: list = None,
                paper_content: str = "", **kwargs) -> ToolResult:
        steps = steps or []
        paper_info = paper_info or {}
        errors = errors or []

        lines = [f"## 复现报告: {goal}", ""]

        # Paper info
        if paper_info:
            lines.append("### 论文信息")
            if paper_info.get("title"):
                lines.append(f"- 标题: {paper_info['title']}")
            if paper_info.get("authors"):
                lines.append(f"- 作者: {paper_info['authors']}")
            if paper_info.get("year"):
                lines.append(f"- 年份: {paper_info['year']}")
            if paper_info.get("urls"):
                lines.append(f"- 链接: {', '.join(paper_info['urls'][:3])}")
            lines.append("")

        # Source code
        if source_url:
            lines.append("### 源码仓库")
            lines.append(f"- {source_url}")
            if paper_info.get("local_paths"):
                lines.append(f"- 本地路径: {', '.join(paper_info['local_paths'])}")
            lines.append("")

        # Steps summary
        lines.append("### 执行步骤")
        done_count = 0
        fail_count = 0
        for s in steps:
            status_icon = {"success": "[OK]", "failed": "[FAIL]", "skipped": "[SKIP]", "done": "[OK]"}.get(s.get("status"), "[?]")
            desc = s.get("description", "")[:80]
            lines.append(f"- {status_icon} Step {s.get('step_id', '?')}: {desc}")
            if s.get("status") in ("success", "done"):
                done_count += 1
            elif s.get("status") == "failed":
                fail_count += 1
        lines.append("")

        # Show key step outputs (execution, analysis results)
        output_steps = [s for s in steps if s.get("observation") and len(s.get("observation", "")) > 20]
        if output_steps:
            lines.append("### 步骤输出详情")
            for s in output_steps:
                obs = s.get("observation", "")
                desc = s.get("description", "")[:60]
                status = "[OK]" if s.get("status") in ("success", "done") else "[FAIL]"
                lines.append(f"#### {status} Step {s.get('step_id', '?')}: {desc}")
                # Show full observation for execution steps, truncated for others
                if any(kw in s.get("description", "").lower() for kw in
                       ["执行", "run", "execute", "运行", "复现"]):
                    lines.append(obs[:5000])
                else:
                    lines.append(obs[:800])
                lines.append("")

        # Paper / execution content
        if paper_content:
            lines.append("### 执行输出")
            lines.append(paper_content[:5000])
            lines.append("")

        # Errors
        if errors:
            lines.append("### 遇到的问题")
            for e in errors[:10]:
                lines.append(f"- {str(e)[:200]}")
            lines.append("")

        # Summary
        lines.append("### 总结")
        lines.append(f"- 共执行 {len(steps)} 步, 成功 {done_count} 步, 失败 {fail_count} 步")
        if fail_count > 0:
            lines.append(f"- 遇到 {len(errors)} 个错误")
        if source_url:
            lines.append(f"- 源码: {source_url}")

        report = "\n".join(lines)
        return self._ok(report, step_count=len(steps), done_count=done_count, fail_count=fail_count)
