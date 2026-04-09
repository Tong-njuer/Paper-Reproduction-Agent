from langchain.tools import tool
from app.db.database import SessionLocal
from app.db.models import Wiki


@tool
def create_wiki(title: str, content: str) -> str:
    """
    创建一个Wiki条目

    参数:
    - title: Wiki标题（例如：C++入门）
    - content: Wiki内容（学习资料或说明）
    """
    print("\n[DEBUG] create_wiki CALLED")

    with SessionLocal() as db:
        wiki = Wiki(title=title, content=content)
        db.add(wiki)
        db.commit()
        db.refresh(wiki)

        return f"Wiki创建成功: [{wiki.id}] {title}"
    
@tool
def get_all_wikis() -> str:
    """
    获取所有Wiki条目
    """
    print("\n[DEBUG] get_all_wikis CALLED")

    with SessionLocal() as db:
        wikis = db.query(Wiki).all()

        if not wikis:
            return "目前没有任何Wiki内容"

        return "\n".join(
            f"[{w.id}] {w.title}"
            for w in wikis
        )
    
@tool
def get_wiki_detail(wiki_id: int) -> str:
    """
    获取指定Wiki的详细内容

    参数:
    - wiki_id: Wiki ID
    """
    print("\n[DEBUG] get_wiki_detail CALLED")

    with SessionLocal() as db:
        wiki = db.query(Wiki).filter(Wiki.id == wiki_id).first()

        if not wiki:
            return f"未找到ID为 {wiki_id} 的Wiki"

        return f"{wiki.title}\n\n{wiki.content}"
    
@tool
def delete_wiki(wiki_id: int) -> str:
    """
    删除一个Wiki条目
    """
    with SessionLocal() as db:
        wiki = db.query(Wiki).filter(Wiki.id == wiki_id).first()

        if not wiki:
            return f"未找到ID为 {wiki_id} 的Wiki"

        db.delete(wiki)
        db.commit()

        return f"Wiki删除成功: [{wiki_id}] {wiki.title}"