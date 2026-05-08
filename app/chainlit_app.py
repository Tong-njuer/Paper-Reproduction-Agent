"""
论文复现助手 — Chainlit Frontend (v2)

A conversation-first AI agent chat UI for paper reproduction.
  - Main area: clean chat — user + assistant natural-language replies only
  - Execution panel: streaming Step, collapsible, like ChatGPT "深度思考"
  - Terminal output: code blocks inside step output
  - Sidebar: history, settings, model selection

Colour scheme: dark charcoal (#1A1A1D) + sweet pink accent (#E6397C)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import threading
import time
from typing import Any

import chainlit as cl
from chainlit.input_widget import Select, Switch, Slider

from app.core.config import get_config
from app.core.llm import get_llm
from app.agent.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

AGENT_KEYWORDS = [
    "复现", "reproduce", "复刻",
    "搜索", "查询", "找论文",
    "克隆", "clone",
    "下载仓库", "下载代码",
    "跑一下", "运行实验", "执行", "run experiment",
    "配置环境", "setup", "环境配置", "安装依赖", "配置依赖",
]

_CLASSIFY_PROMPT = """判断用户意图：
- 用户要求复现论文、搜索论文、克隆/下载代码仓库、执行实验 → 回复 AGENT
- 用户是简单问答、闲聊、询问已有论文内容 → 回复 QA
只回复 AGENT 或 QA，不要其他内容。

用户消息: {message}"""


def _classify_intent(message: str) -> str:
    lower = message.lower()
    if any(kw in lower for kw in AGENT_KEYWORDS):
        return "agent"
    try:
        llm = get_llm()
        resp = llm.generate(_CLASSIFY_PROMPT.format(message=message),
                            max_tokens=8, temperature=0.0)
        return "agent" if "AGENT" in resp.content.upper() else "qa"
    except Exception:
        return "qa"


# ---------------------------------------------------------------------------
# Context enrichment for follow-up agent tasks
# ---------------------------------------------------------------------------

def _enrich_goal(goal: str) -> str:
    """If the user's goal is vague (e.g. 'clone the repo') and we have context
    from a previous agent run, enrich the goal with that context."""
    ctx = _thread_ctx()
    last = ctx.get("last_result") or {}
    source_url = last.get("source_url", "")
    paper_content = last.get("paper_content", "")

    # If the user mentions cloning but doesn't give a URL, add the known one
    has_clone_intent = any(kw in goal.lower() for kw in ["克隆", "clone", "下载"])
    has_url = "http://" in goal or "https://" in goal or "git@" in goal

    if has_clone_intent and not has_url and source_url:
        return f"{goal}\n\n（上下文：上一次找到的源码仓库地址是 {source_url}）"

    # If the user asks about reproducing but we already have paper content,
    # add a hint that we already have the paper
    has_repro_intent = any(kw in goal.lower() for kw in ["复现", "复刻", "reproduce"])
    if has_repro_intent and paper_content:
        return (
            f"{goal}\n\n"
            f"（上下文：上一次已经搜索过此论文，源码地址: {source_url}。"
            f"请基于已有信息继续，不要重复搜索。）"
        )

    # If the user asks to setup/configure environment without specifying a repo,
    # hint with the last result's repo info
    has_setup_intent = any(kw in goal.lower() for kw in [
        "配置环境", "setup", "环境配置", "安装依赖", "配置依赖",
    ])
    if has_setup_intent and not has_url and source_url:
        repo_name = source_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        return (
            f"{goal}\n\n"
            f"（上下文：上一次找到/克隆的仓库是 {repo_name}，源码地址: {source_url}）"
        )

    return goal


# ---------------------------------------------------------------------------
# Build honest result summary
# ---------------------------------------------------------------------------

def _build_summary(result: dict | None, steps: list[dict]) -> str:
    """Build an honest summary — counts final per-step outcome.

    Key: the *last* observation per step_id is the ground truth.
    Earlier failures that were recovered via reflection don't count.
    """
    if result is None:
        return "⚠️ 执行结束，但未获取到结果。"

    # Extract plan
    plan_items = []
    for s in steps:
        if s.get("type") == "plan":
            plan_items = s.get("steps", [])
            break

    # Final outcome per step_id (last observation wins)
    step_outcomes: dict[str, bool] = {}
    for s in steps:
        if s.get("type") == "observation":
            sid = s.get("step_id", "")
            step_outcomes[sid] = s.get("status") == "success"

    total = len(step_outcomes) or len(plan_items)
    success_count = sum(1 for v in step_outcomes.values() if v)
    fail_count = total - success_count

    agent_success = result.get("success", False)
    summary = result.get("summary", "")
    source_url = result.get("source_url", "")
    paper_info = result.get("paper_info", {})

    # Only keep errors for steps that NEVER succeeded
    persistent_errors: list[str] = []
    for s in steps:
        if s.get("type") == "observation" and s.get("status") != "success":
            sid = s.get("step_id", "")
            if sid not in step_outcomes or not step_outcomes[sid]:
                persistent_errors.append(s.get("observation", "")[:200])

    if not persistent_errors:
        persistent_errors = result.get("errors", [])

    lines = []

    if agent_success:
        lines.append(f"✅ **执行成功** — {summary}")
        if total > 0:
            lines.append(f"  完成 {success_count}/{total} 个步骤")
    elif total > 0 and success_count > 0:
        lines.append(
            f"⚠️ **部分完成** — {summary}\n"
            f"  成功 {success_count}/{total} 步，{fail_count} 步未完成"
        )
    elif total > 0:
        lines.append(f"❌ **执行失败** — {summary} (0/{total} 步)")
    else:
        lines.append(f"❌ **执行失败** — {summary}")

    if source_url:
        lines.append(f"\n📦 **源码仓库**: [{source_url}]({source_url})")

    if paper_info.get("urls"):
        seen = set()
        unique_urls = []
        for u in paper_info["urls"]:
            if u not in seen and "arxiv" in u.lower():
                seen.add(u)
                unique_urls.append(u)
        if unique_urls:
            lines.append("\n📄 **论文链接**:")
            for u in unique_urls[:3]:
                lines.append(f"- [{u}]({u})")

    if persistent_errors:
        lines.append(f"\n⚠️ **未恢复的错误 ({len(persistent_errors)} 个)**:")
        for err in persistent_errors[:3]:
            lines.append(f"- {err}")

    lines.append("\n💬 你可以继续指示我下一步操作。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chat-start lifecycle
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Per-thread context isolation
# ---------------------------------------------------------------------------
# Chainlit's user_session is shared across threads within a browser tab.
# We use a module-level dict keyed by thread_id so that paper_content,
# last_result etc. are isolated between conversations.

_thread_stores: dict[str, dict] = {}

def _thread_ctx() -> dict:
    """Get or create the context dict for the current chat thread."""
    tid = cl.context.session.thread_id
    if tid not in _thread_stores:
        _thread_stores[tid] = {
            "paper_content": "",
            "last_result": None,
            "agent_running": False,
        }
    return _thread_stores[tid]


@cl.on_chat_start
async def on_chat_start():
    # Initialise fresh context for this thread
    ctx = _thread_ctx()
    ctx["paper_content"] = ""
    ctx["last_result"] = None
    ctx["agent_running"] = False

    config = get_config()
    cl.user_session.set("config", config)

    await cl.ChatSettings([
        Select(
            id="model", label="模型",
            values=["glm-4-plus", "glm-4-flash", "glm-4", "glm-3-turbo"],
            initial_value=config.llm.model,
        ),
        Slider(
            id="max_steps", label="最大步数",
            initial=config.agent.max_steps, min=3, max=20, step=1,
        ),
        Switch(id="enable_reflection", label="启用反思",
               initial=config.agent.enable_reflection),
        Switch(id="enable_memory", label="启用记忆",
               initial=config.agent.enable_memory),
    ]).send()

    await cl.Message(content=(
        "你好！我是 **论文复现助手** 🔬\n\n"
        "我可以帮你：\n"
        "- 📄 **搜索并阅读论文** — 自动搜索 ArXiv 等来源\n"
        "- 🔍 **定位源码仓库** — 找到论文对应的官方实现\n"
        "- 📥 **克隆代码** — 自动克隆到本地工作区\n"
        "- ⚙️ **配置环境** — 自动创建虚拟环境并安装依赖\n"
        "- 💬 **论文问答** — 基于论文内容解答你的问题\n\n"
        "直接告诉我你想复现的论文名称即可！"
    )).send()


@cl.on_settings_update
async def on_settings_update(settings: dict):
    config = cl.user_session.get("config")
    if config is None:
        return
    # Apply settings directly to the config object
    if "model" in settings:
        config.llm.model = settings["model"]
    if "max_steps" in settings:
        config.agent.max_steps = settings["max_steps"]
    if "enable_reflection" in settings:
        config.agent.enable_reflection = settings["enable_reflection"]
    if "enable_memory" in settings:
        config.agent.enable_memory = settings["enable_memory"]
    cl.user_session.set("config", config)


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

@cl.on_message
async def on_message(message: cl.Message):
    goal = message.content.strip()
    if not goal:
        return

    intent = _classify_intent(goal)
    if intent == "agent":
        await _handle_agent_task(goal)
    else:
        await _handle_simple_qa(goal)


# ---------------------------------------------------------------------------
# Simple QA
# ---------------------------------------------------------------------------

_QA_PROMPT = """你是一个论文问答助手。请基于论文内容回答用户的问题。

论文内容:
{paper_content}

用户问题: {question}

回答原则:
- 优先从论文内容中提取相关信息回答，可以适当展开和组织
- 对于开放性问题（如"还讲了什么"），请梳理论文内容中尚未提及的要点
- 如果论文内容有限（如仅有摘要），可以结合你的知识补充说明，但需标注哪些来自论文、哪些是你的补充
- 即使信息不完整，也尽量提供有帮助的回答，而不是简单地说"未涉及"
- 只有当你完全无法从论文内容和自身知识中找到任何相关回答时，才说明无法回答

请用中文回答，平实准确。"""


async def _handle_simple_qa(question: str):
    paper_content = _thread_ctx().get("paper_content", "")

    if not paper_content:
        await cl.Message(content=(
            "目前还没有已加载的论文内容。\n\n"
            "你可以先告诉我你想复现的论文名称（如「复现 Attention Is All You Need」），"
            "我会自动搜索并阅读论文内容，然后你就可以基于论文内容提问了。"
        )).send()
        return

    msg = cl.Message(content="")
    await msg.send()

    try:
        llm = get_llm()
        prompt = _QA_PROMPT.format(paper_content=paper_content[:8000], question=question)
        resp = llm.generate(prompt, max_tokens=1024)
        msg.content = resp.content
    except Exception as e:
        msg.content = f"问答出错: {e}"

    await msg.update()


# ---------------------------------------------------------------------------
# Agent task — streaming execution panel
# ---------------------------------------------------------------------------

async def _handle_agent_task(raw_goal: str):
    """Run the agent pipeline with real-time streaming step visibility.

    Design:
      - One assistant Message for the natural-language summary.
      - One Step ("Agent Execution") that streams progress like ChatGPT's
        "深度思考" — visible, collapsible, updating in real-time.
    """
    goal = _enrich_goal(raw_goal)

    if _thread_ctx().get("agent_running", False):
        await cl.Message(content="⚠️ 当前有任务正在执行，请稍候…").send()
        return

    _thread_ctx()["agent_running"] = True

    # ── 1. Execution step FIRST — the "深度思考" panel ──
    step = cl.Step(
        name="Agent Execution",
        type="tool",
        show_input=False,
        default_open=True,
    )
    await step.send()

    # ── 3. Thread → async bridge ──
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def push(data: dict):
        loop.call_soon_threadsafe(queue.put_nowait, data)

    def on_step(data: dict):
        push({"kind": "step", **data})

    def on_log(level: str, msg: str):
        push({"kind": "log", "level": level, "message": msg, "ts": time.time()})

    # ── 4. Run orchestrator ──
    holder: dict = {}

    def _run():
        try:
            orch = Orchestrator(on_step=on_step, on_log=on_log)
            holder["result"] = orch.run(goal).to_dict()
        except Exception as exc:
            holder["error"] = str(exc)
            push({"kind": "error", "message": str(exc)})
        finally:
            push({"kind": "_done"})

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # ── 5. Process events → stream to step ──
    step_output_lines: list[str] = []
    plan_items: list[dict] = []
    step_terminal: dict[str, list[str]] = {}  # step_id → log lines
    cur_step_id: str | None = None
    all_step_events: list[dict] = []

    def _append_line(text: str):
        step_output_lines.append(text)

    def _flush():
        """Push accumulated output to the step."""
        pass  # We stream tokens individually, not batched

    while True:
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=0.8)
        except asyncio.TimeoutError:
            if not thread.is_alive():
                break
            continue

        kind = ev.get("kind", "")

        if kind == "_done":
            break

        if kind == "error":
            holder.setdefault("error", ev.get("message", ""))
            await step.stream_token(f"\n\n[FATAL] {ev.get('message', '')}")
            break

        if kind == "log":
            ts = time.strftime("%H:%M:%S", time.localtime(ev["ts"]))
            line = f"[{ts}] {ev['message']}"
            if cur_step_id:
                step_terminal.setdefault(cur_step_id, []).append(line)

        elif kind == "step":
            all_step_events.append(ev)
            line = _format_step_event(ev, plan_items)
            if line:
                await step.stream_token(line)
            # Update step tracking + live step name
            t = ev.get("type", "")
            if t == "plan":
                plan_items.clear()
                plan_items.extend(ev.get("steps", []))
                completed = sum(1 for e in all_step_events
                                if e.get("type") == "observation" and e.get("status") == "success")
                step.name = f"Agent Execution · {completed}/{len(plan_items)} steps"
                await step.update()
            elif t == "step_start":
                cur_step_id = ev.get("step_id", "")
                desc = ev.get("description", "")
                step.name = f"Agent Execution · {desc}"
                await step.update()

    # ── 6. Finalise agent ──
    thread.join(timeout=3.0)
    result = holder.get("result")
    error = holder.get("error")

    # Append terminal output for each step that has logs
    for sid, logs in step_terminal.items():
        if logs:
            terminal_text = "\n".join(logs[-20:])
            term_block = (
                f"\n{H_BAR * 3} Terminal · Step {sid} ({len(logs)} lines) {H_BAR * 20}\n"
                f"{terminal_text}\n"
            )
            await step.stream_token(term_block)

    # Final step name
    completed = sum(1 for e in all_step_events
                    if e.get("type") == "observation" and e.get("status") == "success")
    total = len(plan_items)
    if error:
        step.name = f"Agent Execution · FAILED"
    elif completed == total and total > 0:
        step.name = f"Agent Execution · DONE ({completed}/{total})"
    else:
        step.name = f"Agent Execution · {completed}/{total} steps"
    await step.update()

    # ── 6. Send summary message BELOW the step ──
    ack_content = _build_summary(result, all_step_events)
    ack = cl.Message(content=ack_content)
    await ack.send()

    # Store for context
    if result:
        _thread_ctx()["paper_content"] = result.get("paper_content", "")
        _thread_ctx()["last_result"] = result

    _thread_ctx()["agent_running"] = False


# ---------------------------------------------------------------------------
# Format step events for streaming display
# ---------------------------------------------------------------------------

# Box-drawing characters for visual hierarchy in step output
H_BAR = "━"
SECTION = lambda title: f"\n{H_BAR * 3} {title} {H_BAR * (50 - len(title))}"

def _format_step_event(ev: dict, plan_items: list[dict]) -> str | None:
    """Convert an orchestrator step event into a structured plain-text line.

    Uses box-drawing chars, indentation, and [TAG] markers for visual
    hierarchy — readable like a structured terminal log.
    """
    t = ev.get("type", "")
    sid = ev.get("step_id", "")

    if t == "plan":
        steps = ev.get("steps", [])
        lines = [SECTION(f"Plan · {len(steps)} steps")]
        for s in steps:
            tool = f" [{s.get('tool_hint')}]" if s.get("tool_hint") else ""
            lines.append(f"  [{s['step_id']}] {s['description']}{tool}")
        lines.append(H_BAR * 55)
        return "\n".join(lines) + "\n"

    elif t == "step_start":
        desc = ev.get("description", "")
        return SECTION(f"Step {sid}: {desc}") + "\n"

    elif t == "react":
        thought = ev.get("thought", "")[:200]
        action = ev.get("action", "")
        lines = [f"  > {thought}"]
        if action:
            lines.append(f"  action: {action}")
        return "\n".join(lines) + "\n"

    elif t == "observation":
        obs = ev.get("observation", "")[:300]
        tag = "[OK]" if ev.get("status") == "success" else "[FAIL]"
        return f"\n  {tag}  {obs}\n"

    elif t == "reflection":
        analysis = ev.get("analysis", {})
        explanation = analysis.get("explanation", "")[:200]
        error_type = analysis.get("error_type", "")
        if explanation:
            return f"\n  [REFLECT] {error_type}: {explanation}\n"
        return None

    elif t == "replan":
        new_count = len(ev.get("steps", []))
        return f"  [REPLAN] {new_count} new steps\n"

    return None
