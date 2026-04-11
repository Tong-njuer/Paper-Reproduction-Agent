"""
Plan and Execute 工具 - 一键创建完整学习计划
"""

import json

from langchain.tools import tool
from app.agent.planner import generate_learning_plan, execute_learning_plan
from app.core.context import get_current_user_id


def _check_user():
    """检查用户是否登录"""
    user_id = get_current_user_id()
    if not user_id:
        return None, "用户未登录"
    return user_id, None


def _tool_executor(tool_name: str, kwargs: dict) -> str:
    """执行指定工具"""
    from app.agent.agent import ALL_TOOLS
    for t in ALL_TOOLS:
        if t.name == tool_name:
            return t.invoke(kwargs)
    return f"未找到工具: {tool_name}"


@tool
def create_learning_plan(user_request: str) -> str:
    """
    【一键创建学习计划】

    当用户说"我想要XXX的学习路径"时使用此工具。它会：
    1. 规划完整的学习路径（日程 + Wiki + 题目）
    2. 自动创建所有内容
    3. 返回创建结果汇总

    参数:
    - user_request: 用户的学习需求描述，如"Python数据分析"或"C++入门"
    """
    print(f"\n[DEBUG] create_learning_plan CALLED, request={user_request}")

    user_id, err = _check_user()
    if err:
        return err

    # 生成计划
    plan = generate_learning_plan(user_request)
    if not plan:
        return "计划生成失败，请稍后重试或换个描述方式"

    print(f"[DEBUG] Plan generated: {plan.get('path_title', 'N/A')}")

    # 执行计划
    result = execute_learning_plan(plan, _tool_executor)

    return result


@tool
def preview_learning_plan(user_request: str) -> str:
    """
    【预览学习计划】（不执行，只展示计划）

    当用户想看看学习计划长什么样但还没决定是否创建时使用。

    参数:
    - user_request: 用户的学习需求描述
    """
    print(f"\n[DEBUG] preview_learning_plan CALLED, request={user_request}")

    user_id, err = _check_user()
    if err:
        return err

    # 生成计划
    plan = generate_learning_plan(user_request)
    if not plan:
        return "计划生成失败，请稍后重试或换个描述方式"

    # 只展示，不执行
    parts = [
        f"# 📋 学习计划预览",
        f"",
        f"**路径名称**: {plan.get('path_title', 'N/A')}",
        f"**路径描述**: {plan.get('path_description', 'N/A')}",
        f"",
        f"## 步骤概览",
    ]

    for i, step in enumerate(plan.get("steps", []), 1):
        parts.append(f"\n### 步骤 {i}: {step.get('step_title', 'N/A')}")
        parts.append(f"- 描述: {step.get('step_description', 'N/A')}")

        if step.get("schedule"):
            s = step["schedule"]
            parts.append(f"- 📅 日程: {s.get('title', '')} ({s.get('start_date', '')} ~ {s.get('end_date', '')})")

        if step.get("wiki"):
            w = step["wiki"]
            parts.append(f"- 📖 Wiki: {w.get('title', '')}")

        if step.get("problem"):
            p = step["problem"]
            parts.append(f"- 💻 题目: {p.get('title', '')} (难度: {p.get('difficulty', '')})")

    parts.append(f"\n---\n如需创建此计划，请对我说「创建这个学习计划」")
    return "\n".join(parts)
