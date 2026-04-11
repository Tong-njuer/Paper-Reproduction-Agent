"""
Wiki 工具 - RAG 实现（纯 NumPy 向量检索，无 ChromaDB 依赖）

架构：
1. create_wiki  →  内容存入 SQL，embedding 存入 SQL
2. search_wiki  →  query 转向量 → 余弦相似度检索 → 返回 top-k
"""

import os
import re
import json
from typing import Optional

import numpy as np
from langchain_openai import OpenAIEmbeddings
from langchain.tools import tool
from sqlalchemy import Column, Integer, String, Text, Float

from app.db.database import SessionLocal, engine
from app.db.models import Base, Wiki, WikiVector
from app.core.context import get_current_user_id

# ========== Embedding 配置 ==========
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")

_embedding_model = OpenAIEmbeddings(
    model="embedding-2",
    openai_api_key=ZHIPU_API_KEY,
    openai_api_base="https://open.bigmodel.cn/api/paas/v4"
)


def get_embedding(text: str) -> list[float]:
    """调用 Zhipu API 获取文本的向量表示。"""
    vec = _embedding_model.embed_query(text)
    return vec


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ========== 初始化表 ==========

def _ensure_tables():
    """确保 wiki_vectors 表存在。"""
    Base.metadata.create_all(bind=engine)


def _check_user():
    """检查用户是否登录"""
    user_id = get_current_user_id()
    if not user_id:
        return None, "用户未登录"
    return user_id, None


def _log(tool: str, msg: str, detail: str = None):
    if detail:
        detail = detail[:50] + "..." if len(detail) > 50 else detail
        print(f"[{tool}] {msg} | {detail}")
    else:
        print(f"[{tool}] {msg}")

@tool
def create_wiki(title: str, content: str) -> str:
    """
    创建一个 Wiki 条目，同时生成并存储向量。

    参数:
    - title: Wiki 标题
    - content: Wiki 内容
    """
    _log("WIKI", "创建Wiki", title)

    user_id, err = _check_user()
    if err:
        return err

    _ensure_tables()

    # 1. 存入 SQL 数据库
    with SessionLocal() as db:
        wiki = Wiki(user_id=user_id, title=title, content=content)
        db.add(wiki)
        db.commit()
        db.refresh(wiki)
        wiki_id = wiki.id

    # 2. 生成向量并存储
    try:
        combined_text = f"{title}\n\n{content}"
        embedding = get_embedding(combined_text)

        with SessionLocal() as db:
            vec = WikiVector(
                user_id=user_id,
                wiki_id=wiki_id,
                title=title,
                content=content,
                embedding=json.dumps(embedding)
            )
            db.add(vec)
            db.commit()
            _log("WIKI", "Wiki向量已存储", f"ID={wiki_id}, dim={len(embedding)}")
    except Exception as e:
        _log("WIKI", "向量存储失败", str(e))

    return f"Wiki创建成功: [{wiki_id}] {title}"


@tool
def search_wiki(query: str, top_k: int = 3) -> str:
    """
    【RAG 核心】语义检索 Wiki 内容。

    参数:
    - query: 用户的自然语言问题
    - top_k: 返回最相关的条目数量（默认 3 条）
    """
    _log("WIKI", "检索Wiki", f"query={query[:30]}...")

    user_id, err = _check_user()
    if err:
        return err

    _ensure_tables()

    try:
        # 1. 把 query 转成向量
        query_vec = get_embedding(query)

        # 2. 从数据库加载当前用户的 wiki 向量
        with SessionLocal() as db:
            vectors = db.query(WikiVector).filter(WikiVector.user_id == user_id).all()

        if not vectors:
            return "Wiki 知识库为空，请先创建 Wiki 内容。"

        # 3. 计算每个 wiki 的相似度
        results = []
        for vec in vectors:
            emb = json.loads(vec.embedding)
            score = cosine_similarity(query_vec, emb)
            results.append((score, vec))

        # 4. 按相似度降序排列，取 top_k
        results.sort(key=lambda x: x[0], reverse=True)
        results = results[:top_k]

        # 5. 格式化输出（返回完整内容，不截断）
        output_parts = []
        for rank, (score, vec) in enumerate(results):
            output_parts.append(
                f"--- 检索结果 {rank + 1} ---\n"
                f"标题: {vec.title} [WikiID: {vec.wiki_id}] (相似度: {round(score, 4)})\n"
                f"完整内容:\n{vec.content}"
            )

        return "\n\n".join(output_parts)

    except Exception as e:
        _log("WIKI", "检索失败", str(e))
        return f"检索失败: {e}"


@tool
def get_all_wikis() -> str:
    """获取所有 Wiki 条目（仅标题列表）。"""
    _log("WIKI", "查看所有Wiki")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        wikis = db.query(Wiki).filter(Wiki.user_id == user_id).all()

        if not wikis:
            return "目前没有任何Wiki内容"

        return "\n".join(
            f"[{w.id}] {w.title}"
            for w in wikis
        )


@tool
def delete_wiki(wiki_id: int) -> str:
    """删除一个 Wiki 条目（同时删除 SQL 数据和向量）。"""
    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        wiki = db.query(Wiki).filter(
            Wiki.id == wiki_id,
            Wiki.user_id == user_id
        ).first()
        if not wiki:
            return f"未找到ID为 {wiki_id} 的Wiki"

        title = wiki.title
        db.delete(wiki)

        # 同时删除向量
        vec = db.query(WikiVector).filter(
            WikiVector.wiki_id == wiki_id,
            WikiVector.user_id == user_id
        ).first()
        if vec:
            db.delete(vec)

        db.commit()
        return f"Wiki删除成功: [{wiki_id}] {title}"


@tool
def get_wiki_detail(wiki_id: int) -> str:
    """
    获取指定 Wiki 的完整内容。

    参数:
    - wiki_id: Wiki ID（在 search_wiki 的检索结果中可以找到 WikiID）
    """
    _log("WIKI", "查看Wiki详情", f"wiki_id={wiki_id}")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        wiki = db.query(Wiki).filter(
            Wiki.id == wiki_id,
            Wiki.user_id == user_id
        ).first()

        if not wiki:
            return f"未找到ID为 {wiki_id} 的Wiki"

        return f"# {wiki.title}\n\n{wiki.content}"
