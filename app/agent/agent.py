from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from app.core.config import ZHIPU_API_KEY
from app.tools.schedule_tool import create_schedule, get_all_schedules, update_schedule, delete_schedule
from app.tools.wiki_tool import (
    create_wiki,
    get_all_wikis,
    search_wiki,
    get_wiki_detail,
    delete_wiki
)
from app.tools.code_tool import (
    create_code_problem,
    list_code_problems,
    get_problem_detail,
    submit_and_grade_code,
    get_user_ability_profile
)
from app.agent.prompt import SYSTEM_PROMPT
import re

ALL_TOOLS = [
    create_schedule, get_all_schedules, update_schedule, delete_schedule,
    create_wiki, get_all_wikis, search_wiki, get_wiki_detail, delete_wiki,
    create_code_problem, list_code_problems, get_problem_detail,
    submit_and_grade_code, get_user_ability_profile
]


def parse_response(text):
    """
    解析模型输出，提取 ReAct 各组件。

    标准 ReAct 每次只输出一个组件（Thought / Action / Final Answer）。
    因此解析逻辑如下：

    1. 先找 Thought（推理）
    2. 再找 Action + Action Input（行动）
    3. 最后找 Final Answer（结束）
    """
    # re.DOTALL 让 . 能匹配换行符，否则多行内容会截断
    thought = re.search(r"Thought:(.*)", text, re.DOTALL)
    action = re.search(r"Action:(.*)", text)
    action_input = re.search(r"Action Input:(.*)", text)
    # Final Answer 可能包含多行 markdown，务必加 re.DOTALL
    final = re.search(r"Final Answer:(.*)", text, re.DOTALL)

    return {
        # Thought 可能是多行的，取第一行作为当前推理
        "thought": thought.group(1).strip() if thought else None,
        # Action 和 Action Input 必须同时出现才有效
        "action": action.group(1).strip() if action else None,
        "action_input": action_input.group(1).strip() if action_input else None,
        "final": final.group(1).strip() if final else None,
    }


def execute_tool(action: str, action_input: str) -> str:
    """根据 action 名称和参数执行对应工具，返回原始结果。"""
    try:
        # 将 JSON 字符串解析为字典
        args = eval(action_input)
    except Exception as e:
        return f"参数解析失败: {e}"

    for tool in ALL_TOOLS:
        if tool.name == action:
            return tool.invoke(args)

    return f"未找到工具: {action}"


def create_agent():
    def agent(input_text: str, verbose: bool = True) -> str:
        model = ChatOpenAI(
            model="glm-5.1",
            openai_api_key=ZHIPU_API_KEY,
            openai_api_base="https://open.bigmodel.cn/api/paas/v4",
            temperature=0
        )

        # ========== 初始化对话 ==========
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=input_text),
        ]

        max_steps = 15  # ReAct 需要多轮推理，增加步数上限

        for step in range(max_steps):
            # ========== 第 N 步：模型输出 Thought ==========
            ai_msg = model.invoke(messages)
            content = ai_msg.content
            messages.append(ai_msg)

            if verbose:
                print(f"\n====== Step {step + 1} ======")
                print(content)
                print("======================")

            parsed = parse_response(content)

            # ========== 情况 1：模型直接输出 Final Answer，结束 ==========
            if parsed["final"]:
                if verbose:
                    print(f"[Final Answer] {parsed['final']}")
                return parsed["final"]

            # ========== 情况 2：模型输出 Thought + Action + Action Input ==========
            # 执行工具，获取 Observation
            if parsed["action"] and parsed["action_input"]:
                tool_name = parsed["action"]
                tool_args = parsed["action_input"]

                if verbose:
                    print(f"[Action] {tool_name}")
                    print(f"[Action Input] {tool_args}")

                result = execute_tool(tool_name, tool_args)

                # ========== 关键区别 ==========
                # 标准 ReAct：把 Observation 作为 ToolMessage 加回对话，
                # 让模型在下一轮中自己推理（Thought）Observation 的含义，
                # 然后决定是继续 Action 还是输出 Final Answer。
                # 这样模型能"看到"Observation 并基于它继续思考。
                messages.append(
                    ToolMessage(content=result, tool_call_id=tool_name)
                )

                if verbose:
                    print(f"[Observation] {result}")

                # 不要自动跳到下一轮，让模型先推理 Observation
                # 继续循环，模型会输出下一个 Thought

            # ========== 情况 3：只有 Thought，没有 Action ==========
            # 这说明模型在推理阶段，还没有决定下一步做什么
            # 这种情况不应该在标准 ReAct 中出现，因为我们要求每次都输出 Action
            # 如果出现，可能是模型误解了格式，提示它继续
            elif parsed["thought"] and not parsed["action"]:
                # 要求模型输出 Action
                messages.append(
                    HumanMessage(content="你已经有了 Thought，现在请输出 Action 和 Action Input。")
                )

        return "已达到最大步数限制"

    return agent
