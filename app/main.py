from app.agent.agent import create_agent
from app.db.database import Base, engine

def init_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def main():
    init_db()

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