"""
Planner Agent - 学习计划规划器
使用 Plan + Execute 模式，让 Agent 创建学习路径时自动完成日程、Wiki、题目
"""

import json
from datetime import datetime, timedelta

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import ZHIPU_API_KEY


PLANNER_PROMPT = """你是一个学习计划规划专家。当用户说想要学习某个主题时，你需要为他规划一个完整的编程学习路径。

【任务】
用户想学习: {user_request}

请规划一个完整的编程学习计划，包括：

1. **路径结构**：这条学习路径包含几个步骤，每个步骤的主题是什么
2. **日程安排**：每个步骤需要多长时间（用 create_schedule 的日期格式）
3. **Wiki 资料**：每个步骤需要什么学习资料（创建 Wiki 的 title 和 content 概要）
4. **练习题目**：每个步骤需要什么练习题（创建 CodeProblem 的要素）

【输出格式】
请以 JSON 格式输出，结构如下：
{{
    "path_title": "学习路径名称",
    "path_description": "路径描述",
    "steps": [
        {{
            "step_title": "步骤1标题",
            "step_description": "步骤描述",
            "schedule": {{
                "title": "日程标题",
                "start_date": "YYYY-MM-DD",
                "end_date": "YYYY-MM-DD"
            }},
            "wiki": {{
                "title": "Wiki标题",
                "content_summary": "Wiki内容概要"
            }},
            "problem": {{
                "title": "题目标题",
                "description": "题目描述概要",
                "difficulty": "easy/medium/hard",
                "tags": ["标签1", "标签2"]
            }}
        }}
    ]
}}

【重要】
- 生成 3-5 个步骤比较合适
- start_date 从今天开始，按顺序安排
- 每个步骤的 Wiki 和题目要与该步骤的主题匹配
- difficulty 根据步骤在路径中的位置递增（前面简单，后面复杂）
- 输出纯 JSON，不要有其他内容
"""


def call_llm(prompt: str) -> str:
    """调用 LLM"""
    llm = ChatOpenAI(
        model="glm-4",
        openai_api_key=ZHIPU_API_KEY,
        openai_api_base="https://open.bigmodel.cn/api/paas/v4",
        temperature=0.3
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content.strip()


def parse_json_response(text: str) -> dict:
    """从 LLM 输出中提取 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except:
        pass

    # 尝试提取 ```json ... ``` 块
    import re
    json_match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass

    # 尝试提取 { ... } 块
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass

    return None


def generate_learning_plan(user_request: str) -> dict | None:
    """生成学习计划"""
    prompt = PLANNER_PROMPT.format(user_request=user_request)
    response = call_llm(prompt)
    return parse_json_response(response)


def execute_learning_plan(plan: dict, tool_executor) -> str:
    """
    执行学习计划
    tool_executor: 一个函数，接收 (tool_name, kwargs) 并执行，返回结果
    """
    results = {
        "schedules": [],
        "wikis": [],
        "problems": [],
        "path_id": None
    }

    step_wiki_ids = []
    step_problem_ids = []
    step_schedules = []

    # 第一步：创建所有日程
    for step in plan["steps"]:
        sched = step.get("schedule", {})
        if sched:
            title = sched.get("title", "学习日程")
            start = sched.get("start_date", datetime.now().strftime("%Y-%m-%d"))
            end = sched.get("end_date", (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"))

            result = tool_executor("create_schedule", {
                "title": title,
                "start_date": start,
                "end_date": end
            })
            results["schedules"].append(result)
            print(f"[PLAN] Created schedule: {title}")

            # 从结果中提取 schedule_id（如果工具返回了的话）
            import re
            sid_match = re.search(r"日程创建成功: \[(\d+)\]", result)
            if sid_match:
                step_schedules.append(int(sid_match.group(1)))

    # 第二步：创建所有 Wiki
    for i, step in enumerate(plan["steps"]):
        wiki_data = step.get("wiki", {})
        if wiki_data:
            title = wiki_data.get("title", f"学习资料 - {step.get('step_title', '')}")
            content = wiki_data.get("content_summary", step.get("step_description", ""))

            result = tool_executor("create_wiki", {
                "title": title,
                "content": content
            })
            results["wikis"].append(result)
            print(f"[PLAN] Created wiki: {title}")

            wid_match = re.search(r"Wiki创建成功: \[(\d+)\]", result)
            if wid_match:
                step_wiki_ids.append(int(wid_match.group(1)))

    # 第三步：创建所有题目
    for i, step in enumerate(plan["steps"]):
        prob_data = step.get("problem", {})
        if prob_data:
            # 生成测试用例
            test_cases = _generate_test_cases(prob_data.get("title", ""), prob_data.get("tags", []))

            result = tool_executor("create_code_problem", {
                "title": prob_data.get("title", f"练习题 - {step.get('step_title', '')}"),
                "description": prob_data.get("description", step.get("step_description", "")),
                "difficulty": prob_data.get("difficulty", "medium"),
                "tags": json.dumps(prob_data.get("tags", [])),
                "test_cases": json.dumps(test_cases)
            })
            results["problems"].append(result)
            print(f"[PLAN] Created problem: {prob_data.get('title', '')}")

            pid_match = re.search(r"题目创建成功: \[(\d+)\]", result)
            if pid_match:
                step_problem_ids.append(int(pid_match.group(1)))

    # 第四步：创建学习路径（关联所有内容）
    steps_for_path = []
    for i, step in enumerate(plan["steps"]):
        steps_for_path.append({
            "title": step.get("step_title", f"步骤{i+1}"),
            "description": step.get("step_description", ""),
            "wiki_ids": [step_wiki_ids[i]] if i < len(step_wiki_ids) else [],
            "problem_ids": [step_problem_ids[i]] if i < len(step_problem_ids) else []
        })

    path_result = tool_executor("create_learning_path", {
        "title": plan.get("path_title", "学习路径"),
        "description": plan.get("path_description", ""),
        "steps": json.dumps(steps_for_path)
    })
    results["path_id"] = path_result
    print(f"[PLAN] Created learning path")

    return _format_plan_summary(plan, results)


def _generate_test_cases(title: str, tags: list) -> list:
    """根据题目信息生成测试用例"""
    # 使用 LLM 生成测试用例
    prompt = f"""根据以下编程练习信息，生成 3 个测试用例。

题目: {title}
标签: {', '.join(tags)}

请以 JSON 数组格式输出测试用例，每个用例包含 input 和 expected 字段：
[
    {{"input": "输入1", "expected": "期望输出1"}},
    ...
]

要求：
- input 尽量简洁，符合 ACM 竞赛风格
- 覆盖基本情况和边界情况
- 只输出 JSON，不要有其他内容
"""
    response = call_llm(prompt)
    try:
        return parse_json_response(response) or [
            {"input": "1 2", "expected": "3"},
            {"input": "5 3", "expected": "8"},
            {"input": "10 20", "expected": "30"}
        ]
    except:
        return [
            {"input": "1 2", "expected": "3"},
            {"input": "5 3", "expected": "8"},
            {"input": "10 20", "expected": "30"}
        ]


def _format_plan_summary(plan: dict, results: dict) -> str:
    """格式化计划执行结果摘要"""
    parts = [
        "=" * 50,
        "🎉 学习计划创建完成！",
        "=" * 50,
        f"\n📚 路径名称: {plan.get('path_title', '学习路径')}",
        f"📝 路径描述: {plan.get('path_description', '')}",
    ]

    parts.append(f"\n📅 已创建 {len(results['schedules'])} 个日程")
    for i, s in enumerate(plan["steps"]):
        sched = s.get("schedule", {})
        if sched:
            parts.append(f"  {i+1}. {sched.get('title', '')} ({sched.get('start_date', '')} ~ {sched.get('end_date', '')})")

    parts.append(f"\n📖 已创建 {len(results['wikis'])} 篇 Wiki")
    for i, s in enumerate(plan["steps"]):
        wiki = s.get("wiki", {})
        if wiki:
            parts.append(f"  {i+1}. {wiki.get('title', '')}")

    parts.append(f"\n💻 已创建 {len(results['problems'])} 道练习题")
    for i, s in enumerate(plan["steps"]):
        prob = s.get("problem", {})
        if prob:
            parts.append(f"  {i+1}. {prob.get('title', '')} (难度: {prob.get('difficulty', '')})")

    parts.append(f"\n🗺️  学习路径已创建，可对我说「开始学习路径X」开始学习")
    parts.append("=" * 50)

    return "\n".join(parts)
