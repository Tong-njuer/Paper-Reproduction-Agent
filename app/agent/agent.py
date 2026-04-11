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
from app.tools.learning_path_tool import (
    create_learning_path,
    start_learning_path,
    complete_current_step,
    get_learning_path_progress,
    list_learning_paths,
    get_learning_path_detail,
    recommend_next_learning
)
from app.tools.plan_and_execute_tool import (
    create_learning_plan,
    preview_learning_plan
)
from app.agent.prompt import SYSTEM_PROMPT
import re

ALL_TOOLS = [
    create_schedule, get_all_schedules, update_schedule, delete_schedule,
    create_wiki, get_all_wikis, search_wiki, get_wiki_detail, delete_wiki,
    create_code_problem, list_code_problems, get_problem_detail,
    submit_and_grade_code, get_user_ability_profile,
    create_learning_plan, preview_learning_plan,
    create_learning_path, start_learning_path, complete_current_step,
    get_learning_path_progress, list_learning_paths, get_learning_path_detail,
    recommend_next_learning
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
        "final": final.group(1).rstrip() if final else None,
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
    """
    【ReAct Agent 工厂函数】

    创建的 agent 使用 ReAct 模式：
    1. 模型输出 Thought（思考）
    2. 根据 Thought 决定是否需要执行 Action（工具调用）
    3. 执行工具后获得 Observation（观察结果）
    4. 用 Observation 更新上下文，重复直到 Final Answer

    每次调用 agent() 是一次完整的 ReAct 推理过程。
    """

    def agent(input_text: str, conversation_history: list = None, verbose: bool = True) -> str:
        model = ChatOpenAI(
            model="glm-5.1",
            openai_api_key=ZHIPU_API_KEY,
            openai_api_base="https://open.bigmodel.cn/api/paas/v4",
            temperature=0
        )

        # ========== [Context Injection] 获取用户能力上下文 ==========
        from app.core.context import get_current_user_id
        from app.tools.code_tool import get_user_ability_profile
        user_id = get_current_user_id()
        ability_context = ""
        if user_id:
            try:
                ability_context = get_user_ability_profile()
            except:
                ability_context = ""

        # ========== [Context Injection] 初始化对话 ==========
        # 如果有用户能力信息，先注入作为上下文
        if ability_context and ability_context != "用户未登录":
            context_msg = HumanMessage(content=f"[用户能力背景]\n{ability_context}\n\n请在回答时结合上述用户能力背景，对基础薄弱的知识点多加解释。")
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                context_msg,
            ]
        else:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
            ]

        # 【Memory】添加对话历史（实现跨消息记忆）
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(HumanMessage(content=content))

        # 【User Input】添加当前消息
        messages.append(HumanMessage(content=input_text))

        # ========== [ReAct Loop] 开始 ReAct 推理循环 ==========
        max_steps = 15  # ReAct 需要多轮推理，增加步数上限

        for step in range(max_steps):
            # 【ReAct Step】模型输出 Thought
            ai_msg = model.invoke(messages)
            content = ai_msg.content
            messages.append(ai_msg)

            parsed = parse_response(content)

            # 【ReAct Verbose 输出】只显示关键链
            if verbose:
                print(f"\n--- Step {step + 1} ---")
                # 截断长内容
                if parsed["thought"]:
                    thought = parsed["thought"][:100] + "..." if len(parsed["thought"]) > 100 else parsed["thought"]
                    print(f"[Thought] {thought}")
                if parsed["action"]:
                    print(f"[Action] {parsed['action']}")
                if parsed["action_input"]:
                    args_preview = parsed["action_input"][:80] + "..." if len(parsed["action_input"]) > 80 else parsed["action_input"]
                    print(f"[Action Input] {args_preview}")
                if parsed["final"]:
                    final_preview = parsed["final"][:100] + "..." if len(parsed["final"]) > 100 else parsed["final"]
                    print(f"[Final] {final_preview}")
                print("-" * 20)

            # ========== 情况 1：模型直接输出 Final Answer，结束 ==========
            if parsed["final"]:
                return parsed["final"]

            # ========== 情况 2：模型输出 Thought + Action + Action Input ==========
            # 执行工具，获取 Observation
            if parsed["action"] and parsed["action_input"]:
                tool_name = parsed["action"]
                tool_args = parsed["action_input"]

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
