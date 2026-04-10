"""
Streamlit Web 界面 - 编程教练Agent
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from app.agent.agent import create_agent
from app.core.auth import register_user, login_user
from app.core.context import set_current_user_id, clear_current_user
from app.db.database import Base, engine
from app.db import models  # 确保 models 被导入以注册表


def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)


def init_session():
    """初始化会话状态"""
    if "agent" not in st.session_state:
        st.session_state.agent = create_agent()
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None


def logout():
    """登出"""
    clear_current_user()
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.username = None
    st.session_state.messages = []


def show_login_page():
    """显示登录/注册页面"""
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.title("🤖 编程教练Agent")
        st.markdown("---")

        tab1, tab2 = st.tabs(["登录", "注册"])

        with tab1:
            username = st.text_input("用户名", key="login_username")
            password = st.text_input("密码", type="password", key="login_password")

            if st.button("登录", type="primary"):
                if username and password:
                    success, msg, user_id = login_user(username, password)
                    if success:
                        set_current_user_id(user_id)
                        st.session_state.logged_in = True
                        st.session_state.user_id = user_id
                        st.session_state.username = username
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.error("请输入用户名和密码")

        with tab2:
            new_username = st.text_input("用户名", key="register_username")
            new_password = st.text_input("密码", type="password", key="register_password")
            confirm_password = st.text_input("确认密码", type="password", key="register_confirm")

            if st.button("注册", type="primary"):
                if not new_username or not new_password:
                    st.error("用户名和密码不能为空")
                elif len(new_password) < 6:
                    st.error("密码长度至少6位")
                elif new_password != confirm_password:
                    st.error("两次密码不一致")
                else:
                    success, msg = register_user(new_username, new_password)
                    if success:
                        st.success(msg)
                        st.info("请切换到登录标签登录")
                    else:
                        st.error(msg)


def show_main_app():
    """显示主应用界面"""
    # 设置用户上下文
    if st.session_state.user_id:
        set_current_user_id(st.session_state.user_id)

    st.set_page_config(
        page_title="编程教练Agent",
        page_icon="🤖",
        layout="wide"
    )

    # 顶部栏
    col1, col2 = st.columns([6, 1])
    with col1:
        st.title(f"🤖 编程教练Agent - {st.session_state.username}")
    with col2:
        if st.button("登出"):
            logout()
            st.rerun()

    st.markdown("---")

    # 侧边栏
    with st.sidebar:
        st.header("功能说明")
        st.markdown("""
        ### 对话
        直接在下方输入你的问题，Agent会自动回复。

        ### 出题
        说"出一道关于XX的题目"，Agent会创建题目并告诉你文件位置。

        ### 作答
        1. 在工作区目录下找到题目文件
        2. 编辑文件，编写代码
        3. 回来说"提交第X题答案"
        """)

        st.markdown("---")
        st.markdown("### 工作区")
        st.code(f"workspace/user_{st.session_state.user_id}/problem_X.md", language="bash")

    # 对话历史
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 用户输入
    if prompt := st.chat_input("输入你的问题..."):
        # 显示用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 调用Agent
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                response = st.session_state.agent(prompt, verbose=False)
                st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})


def main():
    init_db()  # 确保数据库表是最新的
    init_session()

    if not st.session_state.logged_in:
        show_login_page()
    else:
        show_main_app()


if __name__ == "__main__":
    main()
