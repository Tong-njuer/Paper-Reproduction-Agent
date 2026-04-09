from langchain_openai import ChatOpenAI
from app.core.config import ZHIPU_API_KEY

def get_llm():
    return ChatOpenAI(
        model="glm-4",
        openai_api_key=ZHIPU_API_KEY,
        openai_api_base="https://open.bigmodel.cn/api/paas/v4",
        temperature=0
    )