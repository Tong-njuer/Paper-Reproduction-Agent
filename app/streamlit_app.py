# ============================================================
# Streamlit Web Application
# ============================================================
# Optional web-based visualization and control interface.
#
# Features:
#   - Goal input
#   - Execution visualization
#   - State monitoring
#   - Memory inspection
#
# Run with:
#   streamlit run app/streamlit_app.py
#   or via docker-compose with profile: ui
# ============================================================

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.agent import create_agent
from app.core.config import get_config
from app.tools import list_available_tools


def main():
    """Streamlit app main function."""

    st.set_page_config(
        page_title="Autonomous Agent Core",
        page_icon="[AGENT]",
        layout="wide",
    )

    st.title("[AGENT] Autonomous Agent Core")
    st.markdown("**Paper Reproduction Agent** - Web Interface")

    # Sidebar configuration
    st.sidebar.header("[EXEC] Configuration")

    config = get_config()

    st.sidebar.markdown(f"**LLM Model:** {config.llm.model}")
    st.sidebar.markdown(f"**Max Steps:** {config.agent.max_steps}")
    st.sidebar.markdown(f"**Replan Threshold:** {config.agent.replan_threshold}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Available Tools:**")
    tools = list_available_tools()
    for name, desc in tools.items():
        st.sidebar.markdown(f"- `{name}`: {desc}")

    # Main content
    col1, col2 = st.columns([2, 1])

    with col1:
        st.header("[GOAL] Goal Input")

        goal = st.text_area(
            "Enter the goal for the agent:",
            value="复现论文：Minimal learning machine for multi-label learning",
            height=100,
        )

        if st.button("[RUN] Start Agent", type="primary"):
            if goal:
                with st.spinner("Agent is running..."):
                    try:
                        agent = create_agent()
                        context = agent.run(goal)

                        st.success(f"Agent completed with status: {context.status}")
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.warning("Please enter a goal")

    with col2:
        st.header("[STAT] Status")

        if "agent" in st.session_state:
            status = st.session_state.agent.get_status()
            st.json(status)
        else:
            st.info("Agent not started yet")

    # Execution history
    st.header("[NOTE] Execution History")

    if "history" in st.session_state and st.session_state.history:
        for i, step in enumerate(st.session_state.history[-10:], 1):
            with st.expander(f"Step {i}: {step.get('action', 'unknown')}"):
                st.markdown(f"**Thought:** {step.get('thought', 'N/A')}")
                st.markdown(f"**Action:** {step.get('action')}")
                st.markdown(f"**Args:** {step.get('action_args', {})}")
                st.markdown(f"**Observation:** {step.get('observation', 'N/A')}")


if __name__ == "__main__":
    main()
