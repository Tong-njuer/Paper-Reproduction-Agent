import os
from dotenv import load_dotenv

load_dotenv()

ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")

# ========== ChromaDB 配置 ==========
# ChromaDB 是本地向量数据库，持久化存储在这里
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "chroma_data")