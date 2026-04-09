from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from app.core.config import ZHIPU_API_KEY
from app.tools.schedule_tool import create_schedule, get_all_schedules, update_schedule, delete_schedule
from app.agent.prompt import SYSTEM_PROMPT
import re

ALL_TOOLS = [create_schedule, get_all_schedules, update_schedule, delete_schedule]

def parse_response(text):
    thought = re.search(r"Thought:(.*)", text)
    action = re.search(r"Action:(.*)", text)
    action_input = re.search(r"Action Input:(.*)", text)
    final = re.search(r"Final Answer:(.*)", text)

    return {
        "thought": thought.group(1).strip() if thought else None,
        "action": action.group(1).strip() if action else None,
        "action_input": action_input.group(1).strip() if action_input else None,
        "final": final.group(1).strip() if final else None,
    }


def create_agent():
    def agent(input_text: str, verbose: bool = True) -> str:
        model = ChatOpenAI(
            model="glm-5.1",
            openai_api_key=ZHIPU_API_KEY,
            openai_api_base="https://open.bigmodel.cn/api/paas/v4",
            temperature=0
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=input_text),
        ]

        max_steps = 10
        for step in range(max_steps):
            ai_msg = model.invoke(messages)
            content = ai_msg.content
            messages.append(ai_msg) 
            parsed = parse_response(content)

            # ✅ 如果要调用工具 
            if parsed["action"]:
                print(f"[Action] {parsed['action']}")
                print(f"[Action Input] {parsed['action_input']}")
                tool_name = parsed["action"]
                tool_args = eval(parsed["action_input"])  # 注意安全性

                for t in ALL_TOOLS:
                    if t.name == tool_name:
                        result = t.invoke(tool_args)

                        # 👉 关键：把Observation喂回去
                        messages.append(HumanMessage(content=f"""
                        Observation: {result}

                        请根据以上Observation判断任务是否已经完成：
                        - 如果完成，请输出 Final Answer
                        - 如果未完成，请继续 Thought 和 Action
                        """))
                        break
            
            # ✅ 如果有最终答案，结束
            if parsed["final"]:
                return parsed["final"]  

        return "已达到最大步数限制"

    return agent
