from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from app.core.config import ZHIPU_API_KEY
from app.tools.schedule_tool import create_schedule, get_all_schedules, update_schedule, delete_schedule
from app.agent.prompt import SYSTEM_PROMPT

ALL_TOOLS = [create_schedule, get_all_schedules, update_schedule, delete_schedule]


def create_agent():
    def agent(input_text: str, verbose: bool = True) -> str:
        model = ChatOpenAI(
            model="glm-4",
            openai_api_key=ZHIPU_API_KEY,
            openai_api_base="https://open.bigmodel.cn/api/paas/v4",
            temperature=0
        ).bind_tools(ALL_TOOLS)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=input_text),
        ]

        max_steps = 10
        for step in range(max_steps):
            if verbose:
                print(f"\n--- Step {step + 1} ---")
                print(f"[User] {input_text}")

            ai_msg = model.invoke(messages)
            if verbose:
                print(f"[Model] {ai_msg.content if ai_msg.content else '(no text response)'}")
                if ai_msg.tool_calls:
                    print(f"[Tool Calls] {[c['name'] for c in ai_msg.tool_calls]}")

            messages.append(ai_msg)

            if not ai_msg.tool_calls:
                return ai_msg.content or "Agent没有返回任何内容"

            for call in ai_msg.tool_calls:
                tool_name = call["name"]
                tool_args = call["args"]
                if verbose:
                    print(f"[Calling Tool] {tool_name} with args: {tool_args}")
                for t in ALL_TOOLS:
                    if t.name == tool_name:
                        result = t.invoke(tool_args)
                        if verbose:
                            print(f"[Tool Result] {result}")
                        messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
                        break

        return "已达到最大步数限制"

    return agent
