from langchain.tools import tool
from app.db.database import SessionLocal
from app.db.models import Schedule
from app.core.context import get_current_user_id


def _check_user():
    """检查用户是否登录"""
    user_id = get_current_user_id()
    if not user_id:
        return None, "用户未登录"
    return user_id, None


@tool
def create_schedule(title: str, start_date: str, end_date: str) -> str:
    """
    创建一个学习日程
    参数:
    - title: 日程名称
    - start_date: 开始日期 (YYYY-MM-DD)
    - end_date: 结束日期 (YYYY-MM-DD)
    """
    print("\n[DEBUG] create_schedule CALLED")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        schedule = Schedule(
            user_id=user_id,
            title=title,
            start_date=start_date,
            end_date=end_date
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)

        print(f"[DEBUG] Inserted ID: {schedule.id}")

        all_data = db.query(Schedule).filter(Schedule.user_id == user_id).all()
        print(f"[DEBUG] All schedules after insert: {[(s.id, s.title) for s in all_data]}")

        return f"日程创建成功: {title} ({start_date} 到 {end_date})"


@tool
def get_all_schedules() -> str:
    """
    查询所有学习日程
    """
    print("\n[DEBUG] get_all_schedules CALLED")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        schedules = db.query(Schedule).filter(Schedule.user_id == user_id).all()

        print(f"[DEBUG] Query result count: {len(schedules)}")
        print(f"[DEBUG] Data: {[(s.id, s.title) for s in schedules]}")

        if not schedules:
            return "目前没有任何日程"


        result =  "\n".join(
            f"[{s.id}] {s.title} ({s.start_date} 到 {s.end_date})"
            for s in schedules
        )
        print(f"[DEBUG] Returning: {result}")


        return result


@tool
def update_schedule(schedule_id: int, title: str | None = None, start_date: str | None = None, end_date: str | None = None) -> str:
    """
    更新一个学习日程的标题或日期
    参数:
    - schedule_id: 日程ID（必填）
    - title: 新日程名称（可选）
    - start_date: 新开始日期（可选，YYYY-MM-DD）
    - end_date: 新结束日期（可选，YYYY-MM-DD）
    """
    user_id, err = _check_user()
    if err:
        return err

    db = SessionLocal()
    schedule = db.query(Schedule).filter(
        Schedule.id == schedule_id,
        Schedule.user_id == user_id
    ).first()
    if not schedule:
        db.close()
        return f"未找到ID为 {schedule_id} 的日程"

    if title is not None:
        schedule.title = title
    if start_date is not None:
        schedule.start_date = start_date
    if end_date is not None:
        schedule.end_date = end_date

    db.commit()
    _title = schedule.title
    _start = schedule.start_date
    _end = schedule.end_date
    db.close()
    return f"日程更新成功: [{schedule_id}] {_title} ({_start} 到 {_end})"


@tool
def delete_schedule(schedule_id: int) -> str:
    """
    删除一个学习日程
    参数:
    - schedule_id: 日程ID（必填）
    """
    user_id, err = _check_user()
    if err:
        return err

    db = SessionLocal()
    schedule = db.query(Schedule).filter(
        Schedule.id == schedule_id,
        Schedule.user_id == user_id
    ).first()
    if not schedule:
        db.close()
        return f"未找到ID为 {schedule_id} 的日程"

    _title = schedule.title
    db.delete(schedule)
    db.commit()
    db.close()
    return f"日程删除成功: [{schedule_id}] {_title}"
