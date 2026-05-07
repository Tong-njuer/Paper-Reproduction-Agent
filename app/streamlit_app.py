import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from app.core.config import get_config
from app.core.llm import get_llm
from app.core.logging import setup_logging
from app.agent.orchestrator import Orchestrator
from app.tools import list_available_tools

setup_logging()

st.set_page_config(
    page_title="论文复现助手",
    page_icon="🔬",
    layout="wide",
)


# ── shared state (survives st.rerun via cache_resource) ──────────
@st.cache_resource
def _store():
    """Thread-safe shared store that survives Streamlit re-runs."""
    return {
        "steps": [], "logs": [], "result": None,
        "paper_content": "", "_done": False,
        "clone_status": None,  # None | "running" | "done" | "error"
        "clone_result": None,
        "clone_logs": [],
    }


# ── session state init ───────────────────────────────────────────
DEFAULTS = {
    "run_state": None,          # None | "running" | "done"
    "chat_messages": [],        # list of {role, content}
    "goal_snapshot": "",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def _run_in_thread(goal: str):
    """Background thread — writes to shared _store, NOT st.session_state."""
    store = _store()

    def on_step(data: dict):
        store["steps"].append(data)

    def on_log(level: str, message: str):
        store["logs"].append({
            "level": level, "message": message, "time": time.time(),
        })

    orchestrator = Orchestrator(on_step=on_step, on_log=on_log)
    try:
        result = orchestrator.run(goal)
        d = result.to_dict()
        store["result"] = d
        store["paper_content"] = d.get("paper_content", "")
    except Exception as e:
        store["logs"].append({
            "level": "error", "message": str(e), "time": time.time(),
        })
        store["result"] = {
            "success": False, "summary": f"执行异常: {e}",
            "source_url": "", "paper_content": "",
            "paper_info": {}, "errors": [str(e)],
        }
    finally:
        store["_done"] = True


def _run_clone_in_thread(repo_url: str, branch: str = ""):
    """Background thread for cloning repo — writes to shared _store."""
    from app.tools.clone_tool import CloneRepoTool

    store = _store()
    store["clone_status"] = "running"
    store["clone_logs"] = []
    store["clone_result"] = None

    def clone_log(msg: str):
        store["clone_logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    clone_log(f"开始克隆: {repo_url}" + (f" (分支: {branch})" if branch else " (自动探测分支)"))
    tool = CloneRepoTool()
    result = tool.execute(repo_url=repo_url, branch=branch)

    if result.success:
        store["clone_status"] = "done"
        store["clone_result"] = {
            "success": True, "output": result.output,
            "local_path": result.metadata.get("local_path", ""),
            "repo_name": result.metadata.get("repo_name", ""),
        }
    else:
        store["clone_status"] = "error"
        store["clone_result"] = {"success": False, "error": result.error}
    clone_log("完成" if result.success else f"失败: {result.error}")


# ── render helpers — take data as explicit args ───────────────────

def render_terminal(logs: list):
    lines = []
    for log in logs[-50:]:
        ts = time.strftime("%H:%M:%S", time.localtime(log["time"]))
        lines.append(f"{ts} | {log['level'].upper():7s} | {log['message']}")
    st.code("\n".join(lines) if lines else "等待输出...", language="text")


def render_steps(steps: list):
    for data in steps:
        t = data["type"]
        sid = data.get("step_id", "")

        if t == "plan":
            with st.expander(
                f"📋 规划: {len(data.get('steps', []))} 个步骤", expanded=True,
            ):
                for s in data.get("steps", []):
                    st.markdown(f"**步骤{s['step_id']}**: {s['description']}")
                    if s.get("tool_hint"):
                        st.caption(f"  工具: {s['tool_hint']}")

        elif t == "step_start":
            st.markdown(f"▶️ **步骤{sid}**: {data.get('description', '')}")

        elif t == "react":
            st.markdown(f"💭 **思考**: {data.get('thought', '')[:200]}")
            st.caption(
                f"🎯 行动: `{data.get('action')}` | 参数: `{data.get('action_args')}`"
            )

        elif t == "observation":
            obs = data.get("observation", "")[:300]
            if data.get("status") == "success":
                st.success(f"✅ 步骤{sid}完成: {obs}")
            else:
                st.error(f"❌ 步骤{sid}失败: {obs}")

        elif t == "reflection":
            analysis = data.get("analysis", {})
            fixes = data.get("fix_suggestions", [])
            with st.expander(
                f"🤔 反思: {analysis.get('explanation', '')[:100]}", expanded=True,
            ):
                st.markdown(f"**错误类型**: {analysis.get('error_type', 'unknown')}")
                st.markdown(f"**严重程度**: {analysis.get('severity', 'medium')}")
                for j, fix in enumerate(fixes, 1):
                    st.markdown(
                        f"**修复方案{j}**: {fix.get('description', '')} "
                        f"(置信度: {fix.get('confidence', 0):.0%})"
                    )
                if data.get("should_replan"):
                    st.warning("⚠️ 建议重新规划")

        elif t == "replan":
            st.info(f"🔄 重新规划: {len(data.get('steps', []))} 个新步骤")


def render_result(r: dict):
    if not r:
        return
    st.divider()
    st.subheader("执行结果")
    if r["success"]:
        st.success(f"✅ {r['summary']}")
    else:
        st.error(f"❌ {r['summary']}")
    if r.get("source_url"):
        st.info(f"**源码地址**: [{r['source_url']}]({r['source_url']})")
    if r.get("paper_info", {}).get("urls"):
        st.markdown("**论文链接**:")
        for url in r["paper_info"]["urls"][:5]:
            st.markdown(f"- [{url}]({url})")
    if r.get("errors"):
        with st.expander(f"⚠️ 错误详情 ({len(r['errors'])} 个)", expanded=False):
            for err in r["errors"]:
                st.caption(f"- {err[:200]}")


def render_clone_section(source_url: str, store: dict):
    """Show clone prompt and handle clone flow if source_url found."""
    if not source_url:
        return

    st.divider()
    st.subheader("📥 源码仓库")

    clone_status = store.get("clone_status")

    if clone_status is None:
        # Haven't started — show prompt
        st.success(f"已找到源码仓库: {source_url}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📥 克隆仓库到工作区", use_container_width=True, type="primary"):
                t = threading.Thread(
                    target=_run_clone_in_thread,
                    args=(source_url, ""),  # empty branch → auto-detect
                    daemon=True,
                )
                t.start()
                st.rerun()
        with c2:
            # Let user scroll down to chat, or we could use an anchor
            st.caption("💬 你也可以在下方对论文内容提问")

    elif clone_status == "running":
        st.info(f"⏳ 正在克隆: {source_url}")
        logs = store.get("clone_logs", [])
        st.code("\n".join(logs[-20:]) if logs else "准备中...", language="text")
        time.sleep(1)
        st.rerun()

    elif clone_status == "done":
        cr = store.get("clone_result", {})
        st.success(f"✅ 克隆成功!")
        st.code(cr.get("output", ""), language="text")
        path = cr.get("local_path", "")
        if path:
            st.info(f"📂 本地路径: `{path}`")

    elif clone_status == "error":
        cr = store.get("clone_result", {})
        st.error(f"❌ 克隆失败: {cr.get('error', '未知错误')}")


def render_chat(paper_content: str):
    st.divider()
    st.subheader("💬 论文问答")
    if not paper_content:
        st.caption("未获取到论文内容，无法问答")
        return

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_q = st.chat_input("关于这篇论文，你想问什么？")
    if not user_q:
        return

    st.session_state.chat_messages.append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)

    with st.chat_message("assistant"):
        with st.spinner("思考中..."):
            answer = _ask_llm_about_paper(user_q, paper_content)
        st.markdown(answer)
    st.session_state.chat_messages.append({"role": "assistant", "content": answer})


def _ask_llm_about_paper(question: str, paper_content: str) -> str:
    llm = get_llm()
    prompt = f"""你是一个论文问答助手。根据以下论文内容回答用户的问题。
如果论文内容中没有相关信息，请如实说"论文内容中未涉及此问题"，不要编造。

论文内容:
{paper_content[:8000]}

用户问题: {question}

请用中文回答，简洁准确。"""
    try:
        resp = llm.generate(prompt, max_tokens=1024)
        return resp.content
    except Exception as e:
        return f"问答出错: {e}"


# ── main ────────────────────────────────────────────────────────

def main():
    st.title("🔬 论文复现助手")
    st.markdown("输入论文名称，Agent 自动搜索、阅读、定位源码地址")

    store = _store()
    run_state = st.session_state.run_state

    # ── sidebar ──
    with st.sidebar:
        st.header("配置")
        try:
            config = get_config()
        except RuntimeError as e:
            st.error(f"配置错误: {e}")
            st.stop()

        st.info(f"**模型**: {config.llm.model}")
        st.info(f"**最大步数**: {config.agent.max_steps}")
        st.info(f"**反思**: {'启用' if config.agent.enable_reflection else '关闭'}")
        st.info(f"**记忆**: {'启用' if config.agent.enable_memory else '关闭'}")

        st.divider()
        st.subheader("可用工具")
        for name, desc in list_available_tools().items():
            st.caption(f"**{name}**: {desc}")

        st.divider()
        st.subheader("未来工具（待实现）")
        for t in ["analyze_tool", "sandbox_tool", "test_tool", "doc_tool"]:
            st.caption(f"{t}")

        if st.button("🧹 清空对话", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()

    # ── input row ──
    c1, c2 = st.columns([3, 1])
    with c1:
        goal = st.text_input(
            "输入复现目标",
            placeholder="例如：复现 Attention Is All You Need",
            key="goal_input",
            label_visibility="collapsed",
        )
    with c2:
        is_running = run_state == "running"
        run_clicked = st.button(
            "开始复现", type="primary", use_container_width=True, disabled=is_running,
        )

    if run_clicked and not goal:
        st.warning("请输入复现目标")

    if run_clicked and goal:
        # Reset shared store and session state
        store["steps"] = []
        store["logs"] = []
        store["result"] = None
        store["paper_content"] = ""
        store["_done"] = False
        store["clone_status"] = None
        store["clone_result"] = None
        store["clone_logs"] = []
        st.session_state.run_state = "running"
        st.session_state.goal_snapshot = goal
        st.session_state.chat_messages = []

        t = threading.Thread(target=_run_in_thread, args=(goal,), daemon=True)
        t.start()
        st.rerun()

    # ── running: poll shared store, render directly ──
    if run_state == "running":
        # Thread finished?
        if store["_done"]:
            st.session_state.result = store["result"]
            st.session_state.paper_content = store["paper_content"]
            st.session_state.run_state = "done"
            st.rerun()

        st.markdown(f"### ⚡ 执行中: {st.session_state.goal_snapshot}")

        steps = store["steps"]
        completed = sum(
            1 for s in steps
            if s["type"] == "observation" and s.get("status") == "success"
        )
        plan_steps = []
        for s in steps:
            if s["type"] == "plan":
                plan_steps = s.get("steps", [])
                break
        total = len(plan_steps) or 4
        st.progress(min(completed / max(total, 1), 1.0),
                     text=f"进度: {completed}/{total} 步")

        tab1, tab2 = st.tabs(["执行步骤", "终端输出"])
        with tab1:
            render_steps(steps)
        with tab2:
            render_terminal(store["logs"])

        time.sleep(1.5)
        st.rerun()

    # ── done: final result + clone + chat ──
    if run_state == "done":
        st.markdown(f"### 目标: {st.session_state.goal_snapshot}")

        tab1, tab2, tab3 = st.tabs(["执行步骤", "终端输出", "执行结果"])
        with tab1:
            render_steps(store["steps"])
        with tab2:
            render_terminal(store["logs"])
        with tab3:
            render_result(store["result"])

        # Clone section — shown when source_url is found
        source_url = (store.get("result") or {}).get("source_url", "")
        render_clone_section(source_url, store)

        render_chat(st.session_state.paper_content)


if __name__ == "__main__":
    main()
