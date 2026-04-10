from sqlalchemy import Column, Integer, String, Text
from app.db.database import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    created_at = Column(String)


class Schedule(Base):
    """日程表"""
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String)
    start_date = Column(String)
    end_date = Column(String)


class Wiki(Base):
    """Wiki表"""
    __tablename__ = "wiki"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String, index=True)
    content = Column(Text)


class WikiVector(Base):
    """Wiki向量表"""
    __tablename__ = "wiki_vectors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    wiki_id = Column(Integer, index=True)
    title = Column(String)
    content = Column(Text)
    embedding = Column(Text)  # JSON 序列化的 float 列表


class CodeProblem(Base):
    """代码题目表"""
    __tablename__ = "code_problems"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String)
    description = Column(Text)
    difficulty = Column(String)  # easy/medium/hard
    tags = Column(Text)  # JSON: ["数组", "链表"]
    test_cases = Column(Text)  # JSON: [{"input": "...", "expected": "..."}]
    created_at = Column(String)


class UserCodeAnswer(Base):
    """用户代码回答表"""
    __tablename__ = "user_code_answers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    problem_id = Column(Integer, index=True)
    user_code = Column(Text)
    evaluation = Column(Text)  # JSON: 评测结果
    suggestions = Column(Text)  # 改进建议
    is_correct = Column(Integer)  # 0/1
    submitted_at = Column(String)


class UserAbility(Base):
    """用户能力画像表"""
    __tablename__ = "user_abilities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True)
    ability_tags = Column(Text)  # JSON: {"指针操作": "薄弱", "链表": "熟练"}
    total_attempted = Column(Integer, default=0)
    total_solved = Column(Integer, default=0)
    updated_at = Column(String)


class LearningPath(Base):
    """学习路径表"""
    __tablename__ = "learning_paths"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String)
    description = Column(Text)
    created_at = Column(String)


class PathStep(Base):
    """学习路径步骤表"""
    __tablename__ = "path_steps"

    id = Column(Integer, primary_key=True, index=True)
    path_id = Column(Integer, index=True)
    order = Column(Integer)
    title = Column(String)
    description = Column(Text)
    wiki_ids = Column(Text)  # JSON: [1, 2] 相关Wiki
    problem_ids = Column(Text)  # JSON: [3] 相关题目
    schedule_id = Column(Integer)  # 关联的日程ID


class UserPathProgress(Base):
    """用户学习路径进度表"""
    __tablename__ = "user_path_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    path_id = Column(Integer, index=True)
    current_step_order = Column(Integer, default=0)  # 当前在第几步（0-based）
    is_completed = Column(Integer, default=0)  # 是否已完成整条路径
    started_at = Column(String)
    completed_at = Column(String)
