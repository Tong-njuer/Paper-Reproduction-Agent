from app.agent.agent import create_agent
from app.db.database import Base, engine
from app.core.context import set_current_user_id
from app.core.auth import register_user, login_user

def init_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def ensure_default_user():
    """确保存在一个默认用户（用于CLI模式）"""
    success, _, user_id = login_user("default_user", "default123")
    if not success:
        # 用户不存在则创建
        success, _ = register_user("default_user", "default123")
        if success:
            _, _, user_id = login_user("default_user", "default123")
    return user_id

def main():
    init_db()

    # CLI模式使用默认用户
    user_id = ensure_default_user()
    set_current_user_id(user_id)
    print(f"[INFO] 已以默认用户登录 (user_id={user_id})")

    agent = create_agent()

    print("🤖 编程教练Agent启动！输入 exit 退出\n")

    while True:
        user_input = input("你: ")

        if user_input.lower() == "exit":
            break

        response = agent(user_input)

        print("\nAgent:", response, "\n")

if __name__ == "__main__":
    main()
