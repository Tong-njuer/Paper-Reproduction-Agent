"""
学习路径工具 - 体系化学习支持
"""

import json
from datetime import datetime
from typing import Optional

from langchain.tools import tool
from app.db.database import SessionLocal
from app.db.models import LearningPath, PathStep, UserPathProgress, Wiki, CodeProblem, Schedule
from app.core.context import get_current_user_id


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
def create_learning_path(
    title: str,
    description: str,
    steps: str
) -> str:
    """
    创建一条完整的学习路径

    参数:
    - title: 路径名称，如"C++入门之路"
    - description: 路径描述
    - steps: JSON数组格式的步骤列表，每个步骤包含：
      - title: 步骤标题
      - description: 步骤描述
      - wiki_ids: 相关Wiki的ID列表（可选）
      - problem_ids: 相关题目的ID列表（可选）
      示例: '[{"title":"第一周：指针基础","description":"...","wiki_ids":[1],"problem_ids":[1]}]'
    """
    _log("PATH", "创建学习路径", title)

    user_id, err = _check_user()
    if err:
        return err

    try:
        steps_list = json.loads(steps) if isinstance(steps, str) else steps
    except:
        return "步骤格式错误，请使用JSON数组格式"

    if not steps_list:
        return "路径至少需要一个步骤"

    with SessionLocal() as db:
        path = LearningPath(
            user_id=user_id,
            title=title,
            description=description,
            created_at=datetime.now().isoformat()
        )
        db.add(path)
        db.commit()
        db.refresh(path)

        # 创建步骤
        for i, step in enumerate(steps_list):
            step_title = step.get("title", f"步骤 {i+1}")
            step_desc = step.get("description", "")
            wiki_ids = json.dumps(step.get("wiki_ids", []))
            problem_ids = json.dumps(step.get("problem_ids", []))

            db_step = PathStep(
                path_id=path.id,
                order=i,
                title=step_title,
                description=step_desc,
                wiki_ids=wiki_ids,
                problem_ids=problem_ids,
                schedule_id=None
            )
            db.add(db_step)

        db.commit()

        _log("PATH", "学习路径已创建", f"ID={path.id}, steps={len(steps_list)}")

    return f"""学习路径创建成功: [{path.id}] {title}

路径包含 {len(steps_list)} 个步骤：
{chr(10).join(f"{i+1}. {s.get('title', f'步骤{i+1}')}" for i, s in enumerate(steps_list))}

要开始学习这条路径，请对我说"开始学习路径{path.id}" """


@tool
def start_learning_path(path_id: int) -> str:
    """
    开始一条学习路径

    参数:
    - path_id: 学习路径ID
    """
    _log("PATH", "开始学习路径", f"path_id={path_id}")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        # 检查路径是否存在
        path = db.query(LearningPath).filter(
            LearningPath.id == path_id,
            LearningPath.user_id == user_id
        ).first()
        if not path:
            return f"未找到ID为 {path_id} 的学习路径"

        # 检查是否已有进度
        progress = db.query(UserPathProgress).filter(
            UserPathProgress.path_id == path_id,
            UserPathProgress.user_id == user_id
        ).first()

        if progress:
            if progress.is_completed:
                return f"你已经完成了这条路径！要说 重新开始 才能再次学习"
            # 已有进度，返回当前位置
            return _build_current_step_info(db, path, progress, user_id)

        # 创建新进度
        progress = UserPathProgress(
            user_id=user_id,
            path_id=path_id,
            current_step_order=0,
            is_completed=0,
            started_at=datetime.now().isoformat()
        )
        db.add(progress)
        db.commit()

        return _build_current_step_info(db, path, progress, user_id)


def _build_current_step_info(db, path: LearningPath, progress: UserPathProgress, user_id: int) -> str:
    """构建当前步骤的详细信息"""
    # 获取当前步骤
    current_step = db.query(PathStep).filter(
        PathStep.path_id == path.id,
        PathStep.order == progress.current_step_order
    ).first()

    if not current_step:
        return "路径步骤信息出错"

    # 获取路径总步数
    total_steps = db.query(PathStep).filter(PathStep.path_id == path.id).count()

    # 获取相关Wiki和题目详情
    wiki_ids = json.loads(current_step.wiki_ids or "[]")
    problem_ids = json.loads(current_step.problem_ids or "[]")

    result_parts = [
        f"=== {path.title} ===",
        f"进度: {progress.current_step_order + 1}/{total_steps}",
        f"",
        f"【当前步骤】{current_step.title}",
        f"{current_step.description or '暂无描述'}",
    ]

    if wiki_ids:
        wikis = db.query(Wiki).filter(Wiki.id.in_(wiki_ids)).all()
        if wikis:
            result_parts.append(f"|")
            result_parts.append(f"【相关Wiki】")
            for w in wikis:
                result_parts.append(f"  - [{w.id}] {w.title}")

    if problem_ids:
        problems = db.query(CodeProblem).filter(CodeProblem.id.in_(problem_ids)).all()
        if problems:
            result_parts.append(f"|")
            result_parts.append(f"【相关题目】")
            for p in problems:
                result_parts.append(f"  - [{p.id}] {p.title} (难度: {p.difficulty})")

    result_parts.append(f"|")
    result_parts.append(f"完成当前步骤后，对我说 完成步骤 来继续")

    return "\n".join(result_parts)


@tool
def complete_current_step(path_id: int) -> str:
    """
    完成当前步骤，进入下一步

    参数:
    - path_id: 学习路径ID
    """
    _log("PATH", "完成当前步骤", f"path_id={path_id}")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        path = db.query(LearningPath).filter(
            LearningPath.id == path_id,
            LearningPath.user_id == user_id
        ).first()
        if not path:
            return f"未找到ID为 {path_id} 的学习路径"

        progress = db.query(UserPathProgress).filter(
            UserPathProgress.path_id == path_id,
            UserPathProgress.user_id == user_id
        ).first()

        if not progress:
            return "你还没有开始这条路径，请先说开始学习路径"

        if progress.is_completed:
            return "你已经完成了这条路径！"

        # 获取总步数
        total_steps = db.query(PathStep).filter(PathStep.path_id == path.id).count()

        # 完成当前步骤
        progress.current_step_order += 1

        if progress.current_step_order >= total_steps:
            # 路径完成
            progress.is_completed = 1
            progress.completed_at = datetime.now().isoformat()
            db.commit()
            return f"""🎉 恭喜！你已完成《{path.title}》全部 {total_steps} 个步骤！

这是你的学习成果。继续探索其他路径或让我帮你制定新的学习计划吧！"""
        else:
            db.commit()
            # 返回下一步信息
            return _build_current_step_info(db, path, progress, user_id)


@tool
def get_learning_path_progress(path_id: int) -> str:
    """
    查看学习路径的当前进度

    参数:
    - path_id: 学习路径ID
    """
    _log("PATH", "查看路径进度", f"path_id={path_id}")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        path = db.query(LearningPath).filter(
            LearningPath.id == path_id,
            LearningPath.user_id == user_id
        ).first()
        if not path:
            return f"未找到ID为 {path_id} 的学习路径"

        progress = db.query(UserPathProgress).filter(
            UserPathProgress.path_id == path_id,
            UserPathProgress.user_id == user_id
        ).first()

        if not progress:
            return f"你还没有开始学习《{path.title}》，请对我说开始学习路径{path_id}"

        if progress.is_completed:
            return f"🎉 你已完成《{path.title}》全部课程！"

        return _build_current_step_info(db, path, progress, user_id)


@tool
def list_learning_paths() -> str:
    """
    查看所有学习路径
    """
    _log("PATH", "查看所有路径")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        paths = db.query(LearningPath).filter(LearningPath.user_id == user_id).all()

        if not paths:
            return "目前没有任何学习路径，请我对你说帮我创建一条C++学习路径"

        result_parts = []
        for p in paths:
            steps_count = db.query(PathStep).filter(PathStep.path_id == p.id).count()
            result_parts.append(f"[{p.id}] {p.title} ({steps_count}个步骤)")

        return "\n".join(result_parts)


@tool
def get_learning_path_detail(path_id: int) -> str:
    """
    查看学习路径的详细信息（包含所有步骤）

    参数:
    - path_id: 学习路径ID
    """
    _log("PATH", "查看路径详情", f"path_id={path_id}")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        path = db.query(LearningPath).filter(
            LearningPath.id == path_id,
            LearningPath.user_id == user_id
        ).first()
        if not path:
            return f"未找到ID为 {path_id} 的学习路径"

        steps = db.query(PathStep).filter(PathStep.path_id == path.id).order_by(PathStep.order).all()

        progress = db.query(UserPathProgress).filter(
            UserPathProgress.path_id == path_id,
            UserPathProgress.user_id == user_id
        ).first()

        current_order = progress.current_step_order if progress else None
        is_completed = progress.is_completed if progress else False

        result_parts = [
            f"# {path.title}",
            f"{path.description or '暂无描述'}",
            f"",
            f"总步骤数: {len(steps)}"
        ]

        for i, step in enumerate(steps):
            status = "✅" if is_completed else ("👉" if i == current_order else "  ")
            wiki_ids = json.loads(step.wiki_ids or "[]")
            problem_ids = json.loads(step.problem_ids or "[]")

            result_parts.append(f"|")
            result_parts.append(f"{status} 步骤{i+1}: {step.title}")
            if step.description:
                result_parts.append(f"   {step.description}")
            if wiki_ids:
                result_parts.append(f"   📚 相关Wiki: {len(wiki_ids)}篇")
            if problem_ids:
                result_parts.append(f"   💻 相关题目: {len(problem_ids)}道")

        if progress and not progress.is_completed:
            result_parts.append(f"|")
            result_parts.append(f"当前进度: 步骤 {current_order + 1}")

        return "\n".join(result_parts)


@tool
def recommend_next_learning() -> str:
    """
    【智能推荐】根据用户能力画像推荐下一步学习内容
    """
    _log("PATH", "推荐学习内容")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        # 获取用户能力画像
        from app.db.models import UserAbility
        ability = db.query(UserAbility).filter(UserAbility.user_id == user_id).first()

        weak_tags = []
        if ability and ability.ability_tags:
            tags = json.loads(ability.ability_tags)
            # 找出薄弱的知识点
            for tag, level in tags.items():
                if level in ["薄弱", "一般"]:
                    weak_tags.append(tag)

        # 获取用户的学习路径进度
        active_progress = db.query(UserPathProgress).filter(
            UserPathProgress.user_id == user_id,
            UserPathProgress.is_completed == 0
        ).first()

        suggestions = []

        # 建议1: 继续当前路径
        if active_progress:
            path = db.query(LearningPath).filter(LearningPath.id == active_progress.path_id).first()
            if path:
                current_step = db.query(PathStep).filter(
                    PathStep.path_id == path.id,
                    PathStep.order == active_progress.current_step_order
                ).first()
                if current_step:
                    suggestions.append(f"继续学习《{path.title}》：当前步骤「{current_step.title}」")

        # 建议2: 针对弱项出题
        if weak_tags:
            weak_topic = weak_tags[0]
            suggestions.append(f"你的「{weak_topic}」还需要加强，要不要我出一道练习题？")

        # 建议3: 查看能力画像
        suggestions.append(f"查看你的能力画像，了解自己的长短板")

        if not suggestions:
            suggestions.append("目前没有待学习内容，想要我帮你创建一条学习路径吗？")

        return "【学习推荐】\n" + "\n".join(f"- {s}" for s in suggestions)
