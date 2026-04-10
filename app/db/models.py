from sqlalchemy import Column, Integer, String, Text
from app.db.database import Base

class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    start_date = Column(String)
    end_date = Column(String)

class Wiki(Base):
    __tablename__ = "wiki"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(Text)


class CodeProblem(Base):
    """代码题目"""
    __tablename__ = "code_problems"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(Text)
    difficulty = Column(String)  # easy/medium/hard
    tags = Column(Text)  # JSON: ["数组", "链表"]
    test_cases = Column(Text)  # JSON: [{"input": "...", "expected": "..."}]
    created_at = Column(String)


class UserCodeAnswer(Base):
    """用户代码回答"""
    __tablename__ = "user_code_answers"

    id = Column(Integer, primary_key=True, index=True)
    problem_id = Column(Integer, index=True)
    user_code = Column(Text)
    evaluation = Column(Text)  # JSON: 评测结果
    suggestions = Column(Text)  # 改进建议
    is_correct = Column(Integer)  # 0/1
    submitted_at = Column(String)


class UserAbility(Base):
    """用户能力画像"""
    __tablename__ = "user_abilities"

    id = Column(Integer, primary_key=True, index=True)
    ability_tags = Column(Text)  # JSON: {"指针操作": "薄弱", "链表": "熟练"}
    total_attempted = Column(Integer, default=0)
    total_solved = Column(Integer, default=0)
    updated_at = Column(String)