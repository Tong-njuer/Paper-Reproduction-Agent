"""
Chainlit 界面辅助函数

包含消息格式化、摘要生成、事件展示等 UI 相关工具函数。
从 chainlit_app.py 中拆分，降低主文件复杂度。
"""

from typing import Any, Dict, List, Optional


# ── 常量 ──

H_BAR = "━"
SECTION = lambda title: f"\n{H_BAR * 3} {title} {H_BAR * (50 - len(title))}"

STATUS_ICONS = {
    "thinking": "🤖", "planning": "📋", "searching": "🔍",
    "fetching": "📄", "source": "🔗", "cloning": "📥",
    "env": "🐍", "executing": "⚙️", "reporting": "📝",
}

# 工具名 → 阶段标签映射（用于状态更新）
PHASE_MAP = {
    "search_tool": "searching",
    "fetch_tool": "fetching",
    "source_tool": "source",
    "clone_tool": "cloning",
    "python_env_tool": "env",
    "execute_session_tool": "executing",
}

PROVIDER_MODELS = {
    "deepseek": ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro"],
    "zhipu": ["glm-4-plus", "glm-4-flash", "glm-4", "glm-3-turbo"],
}

NO_AGENT_TOOL_NAMES = {
    "list_reports_tool", "view_report_tool", "search_reports_tool",
    "delete_report_tool", "check_repo_tool", "workspace_cleanup_tool",
    "config_tool", "stats_tool",
}


# ── 摘要生成 ──

def build_agent_summary(result: Optional[Dict], all_step_events: List[Dict]) -> str:
    """从 agent 执行结果和步骤事件中生成用户可见的摘要消息。"""
    if not result:
        return "❌ 执行失败，请查看上方 step 面板了解详情。"

    # 基础信息
    success = result.get("success", False)
    goal = result.get("goal", "")[:100]
    source_url = result.get("source_url", "")
    errors = result.get("errors", [])
    steps_info = result.get("steps", [])

    # 统计
    total = max(len(steps_info), 1)
    done = sum(1 for s in steps_info if s.get("status") in ("success", "done"))
    failed = sum(1 for s in steps_info if s.get("status") == "failed")
    paper_info = result.get("paper_info", {})

    parts = []
    emoji = "✅" if success else "⚠️"
    parts.append(f"{emoji} **{'复现完成' if success else '复现未完整通过'}**")

    if goal:
        parts.append(f"目标: `{goal}`")
    if paper_info.get("title"):
        title = paper_info["title"][:100]
        parts.append(f"论文: {title}")
    if source_url:
        parts.append(f"源码: [{source_url}]({source_url})")
    if errors:
        err_summary = errors[0] if len(errors) == 1 else f"{len(errors)} 个错误"
        parts.append(f"错误: {err_summary[:200]}")

    parts.append(f"步骤: {done}/{total} 完成" + (f", {failed} 失败" if failed else ""))

    # 添加各步骤的简略描述
    step_lines = []
    for s in steps_info:
        sid = s.get("step_id", "?")
        desc = s.get("description", "")[:60]
        st = s.get("status", "?")
        icon = {"success": "✅", "done": "✅", "failed": "❌", "skipped": "⏭️", "active": "⏳"}.get(st, "❓")
        step_lines.append(f"  {icon} Step {sid}: {desc}")
    if step_lines:
        parts.append("")
        parts.extend(step_lines)

    # 若有完整报告，提示用户
    summary = result.get("summary", "")
    if len(summary) > 300:
        parts.append("")
        parts.append("*📋 完整复现报告见下方*")

    return "\n".join(parts)


def format_step_event_lines(events: List[Dict]) -> List[str]:
    """将 step 事件列表格式化为可读文本行。"""
    result: List[str] = []
    for ev in events:
        t = ev.get("type", "")
        if t == "step_start":
            desc = ev.get("description", "")
            rid = ev.get("retry_count", 0)
            tag = f" [重试 #{rid}]" if ev.get("retry") else ""
            result.append(f"📍 Step {ev.get('step_id', '?')}{tag}: {desc}")
        elif t == "react":
            thought = ev.get("thought", "")
            action = ev.get("action", "")
            args = ev.get("action_args", {})
            if thought:
                result.append(f"  💭 {thought[:200]}")
            if action:
                result.append(f"  action: {action}({args})")
        elif t == "observation":
            obs = ev.get("observation", "")
            status = ev.get("status", "")
            if obs:
                result.append(f"  → {obs[:300]}")
                if len(obs) > 300:
                    result.append(f"  ... ({len(obs)} chars)")
        elif t == "error":
            result.append(f"  ❌ {ev.get('message', '')}")
    return result
