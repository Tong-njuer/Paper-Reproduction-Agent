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
from typing import Any, Dict, List

import chainlit as cl
from chainlit.input_widget import Select, Switch, Slider

from app.core.config import get_config
from app.core.llm import get_llm
from app.agent.orchestrator import Orchestrator
from app.chainlit_helpers import (
    H_BAR,
    SECTION,
    STATUS_ICONS,
    PHASE_MAP,
    PROVIDER_MODELS,
    NO_AGENT_TOOL_NAMES,
    build_agent_summary,
    format_step_event_lines,
)

# ---------------------------------------------------------------------------
# Intent classification — delegates to app.agent.intent_classifier
# ---------------------------------------------------------------------------

from app.agent.intent_classifier import IntentType, get_classifier


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

    # If the user asks about reproducing and we already know the source URL,
    # provide it as context (but don't tell the planner to skip steps).
    has_repro_intent = any(kw in goal.lower() for kw in ["复现", "复刻", "reproduce"])
    if has_repro_intent and source_url and not has_url:
        return (
            f"{goal}\n\n"
            f"（提示：之前找到的源码地址是 {source_url}，可直接用于克隆。）"
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
    # Last successful observation per step_id → output text
    step_outputs: dict[int, str] = {}
    for s in steps:
        if s.get("type") == "observation":
            sid = s.get("step_id", "")
            step_outcomes[sid] = s.get("status") == "success"
            if s.get("status") == "success":
                obs = s.get("observation", "")
                # Strip leading status prefixes like "[SUCCESS]" "[OK]"
                if obs:
                    step_outputs[sid] = obs

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

    # All step tool_hints from the plan (so we know what type of plan this is)
    plan_tools = {s.get("tool_hint", "") for s in plan_items}
    is_aux_plan = bool(plan_tools & NO_AGENT_TOOL_NAMES) or (
        len(plan_items) == 1 and total <= 1 and not source_url
    )

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

    # --- Show tool outputs in the main message area ---
    # For auxiliary tools (config, workspace, reports, etc.), the tool
    # output IS the answer the user wants.  Include it directly.
    # For reproduction tasks, only include execution-step outputs.
    if step_outputs:
        if is_aux_plan:
            # Aux query — show all tool outputs as the main reply
            for sid in sorted(step_outputs.keys()):
                output = step_outputs[sid].strip()
                if output:
                    lines.append(f"\n{output}")
        else:
            # Reproduction task — include execute_session_tool or run outputs
            for sid in sorted(step_outputs.keys()):
                output = step_outputs[sid].strip()
                if output and len(output) > 50:
                    # Check if this step maps to an execute/run tool
                    step_desc = ""
                    for p in plan_items:
                        if p.get("step_id") == sid:
                            step_desc = p.get("description", "")
                            break
                    exec_keywords = ["执行", "运行", "execute", "run", "复现"]
                    if any(kw in step_desc.lower() for kw in exec_keywords) or \
                       any(kw in step_desc.lower() for kw in ["配置", "环境", "setup"]):
                        # Show the first 2000 chars of execution output
                        lines.append(f"\n### 执行结果\n{output[:2000]}")

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
_MAX_THREAD_STORES = 50

# Session persistence for page-refresh recovery
from app.tools.session_store import get_session_store
_session_store = get_session_store()

def _thread_ctx() -> dict:
    """Get or create the context dict for the current chat thread.
    NOTE: Does NOT auto-save to disk — use _save_session() explicitly.
    """
    try:
        tid = cl.context.session.thread_id
    except (AttributeError, RuntimeError):
        return {"paper_content": "", "last_result": None, "agent_running": False, "_temp": True}

    if tid not in _thread_stores:
        if len(_thread_stores) >= _MAX_THREAD_STORES:
            oldest = next(iter(_thread_stores))
            del _thread_stores[oldest]
        _thread_stores[tid] = {
            "paper_content": "",
            "last_result": None,
            "agent_running": False,
            "_user_messages": [],
        }
    return _thread_stores[tid]


def _save_session():
    """Explicitly save current session to disk.
    Skips blank sessions — only saves when there's meaningful data.
    """
    try:
        tid = cl.context.session.thread_id
        ctx = _thread_stores.get(tid)
        if ctx is None or ctx.get("_temp"):
            return
        has_data = (
            ctx.get("last_result") or ctx.get("paper_content")
            or ctx.get("_user_messages") or ctx.get("_last_qa")
        )
        if not has_data:
            return
        _session_store.save(tid, ctx)
    except Exception:
        pass


def _restore_session(ctx: dict) -> bool:
    """Restore previous session context and message history.
    Returns True if any data was restored.
    """
    try:
        tid = cl.context.session.thread_id
        saved = _session_store.load(tid)
        if not saved:
            saved = _session_store.load_latest()
        if not saved:
            return False
        ctx["paper_content"] = saved.get("paper_content", "")
        ctx["last_result"] = saved.get("last_result")
        ctx["_user_messages"] = saved.get("user_messages", [])
        ctx["_messages"] = saved.get("messages", [])
        has_data = bool(ctx.get("_messages"))
        return has_data
    except Exception:
        pass
    return False


@cl.on_chat_start
async def on_chat_start():
    ctx = _thread_ctx()
    # Try to restore previous session
    restored = _restore_session(ctx)

    config = get_config()
    cl.user_session.set("config", config)

    provider = config.llm.provider
    model_values = PROVIDER_MODELS.get(provider, PROVIDER_MODELS["zhipu"])
    # Ensure current model is in the list
    current_model = config.llm.model
    if current_model not in model_values:
        model_values = [current_model] + model_values

    await cl.ChatSettings([
        Select(
            id="provider", label="LLM 提供商",
            values=["deepseek", "zhipu"],
            initial_value=provider,
        ),
        Select(
            id="model", label="模型",
            values=model_values,
            initial_value=current_model,
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
    # Save the restored context immediately so it's not lost on next refresh
    _save_session()

    # Replay historical messages if session was restored
    if restored:
        await _replay_messages(ctx)


async def _replay_messages(ctx: dict):
    """Replay saved messages into the Chainlit UI so the full conversation is visible."""
    messages = ctx.get("_messages", [])
    if not messages:
        return
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            await cl.Message(content=content, author="你").send()
        elif role == "assistant":
            await cl.Message(content=content[:2000], author="助手").send()
    # Divider to separate history from the current session
    divider = "━" * 40 + "\n\n*以上为历史消息，继续当前对话*"
    await cl.Message(content=divider, author="系统").send()


def _save_message(role: str, content: str):
    """Append a message to the context's message list and persist to disk."""
    ctx = _thread_ctx()
    ctx.setdefault("_messages", []).append({
        "role": role,
        "content": content[:2000],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    })
    _save_session()


@cl.on_chat_end
async def on_chat_end():
    """Clean up thread context when the chat session ends (page refresh / close)."""
    try:
        tid = cl.context.session.thread_id
        _thread_stores.pop(tid, None)
    except (AttributeError, RuntimeError):
        pass


@cl.on_settings_update
async def on_settings_update(settings: dict):
    config = cl.user_session.get("config")
    if config is None:
        return

    # Provider change → update base_url and api_key too
    if "provider" in settings:
        new_provider = settings["provider"]
        config.llm.provider = new_provider
        _DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
        _ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        if new_provider == "deepseek":
            import os
            config.llm.base_url = _DEEPSEEK_URL
            config.llm.api_key = os.getenv("DEEPSEEK_API_KEY", "") or config.llm.api_key
        else:
            config.llm.base_url = _ZHIPU_URL
            config.llm.api_key = os.getenv("ZHIPU_API_KEY", "") or config.llm.api_key
        # Reset LLM singleton so next call picks up new config
        import app.core.llm as llm_mod
        llm_mod._llm = None

    if "model" in settings:
        config.llm.model = settings["model"]
        import app.core.llm as llm_mod
        llm_mod._llm = None

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

    # ── Classify intent using the proper IntentClassifier with context ──
    ctx = _thread_ctx()
    last_result = ctx.get("last_result") or {}
    paper_content = ctx.get("paper_content", "")

    # Build context string for the classifier
    context_parts = []
    if last_result:
        status = "成功" if last_result.get("success") else "失败"
        context_parts.append(
            f"上一次执行: 目标={last_result.get('goal', '')}, "
            f"结果={status}, "
            f"源码={last_result.get('source_url', '无')}"
        )
        if last_result.get("errors"):
            context_parts.append(f"错误数: {len(last_result.get('errors', []))}")
    if paper_content:
        context_parts.append(f"已有论文内容: {len(paper_content)} 字符")
    context_str = " | ".join(context_parts) if context_parts else ""

    classifier = get_classifier()
    intent, requires_agent = classifier.classify(goal, context_str)

    # ── Save user message & persist ──
    ctx.setdefault("_user_messages", []).append(goal[:200])
    _save_message("user", goal)
    _save_session()

    # ── Route based on intent ──
    if requires_agent:
        await _handle_agent_task(goal)
    else:
        await _handle_simple_qa(goal)


# ---------------------------------------------------------------------------
# Simple QA
# ---------------------------------------------------------------------------

_QA_PROMPT = """你是一个论文复现助手。根据提供的论文内容和复现执行记录，回答用户的问题。

回答原则:
- 如果问题涉及复现过程（步骤、错误、结果），优先从**复现执行记录**中提取信息
- 如果问题涉及论文内容（方法、实验、结论），优先从**论文内容**中提取信息
- 可以结合你的知识补充说明，但需标注哪些来自记录、哪些是你的补充
- 对于"讲解一下你是如何复现的"这类问题，按照执行步骤逐步说明过程
- 对于"遇到了什么错误"，列出错误及修复方式
- 对于"复现成功的标志是什么"，说明安装验证通过、核心导入成功等
- 如果信息不完整，也尽量提供有帮助的回答
- 只有当你完全无法从提供的信息中找到相关回答时，才说明无法回答

请用中文回答，平实准确。"""


async def _handle_simple_qa(question: str):
    ctx = _thread_ctx()
    paper_content = ctx.get("paper_content", "")
    last_result = ctx.get("last_result") or {}

    # Build rich context from the last agent run (if any)
    reproduction_summary = ""
    if last_result:
        goal = last_result.get("goal", "")
        source_url = last_result.get("source_url", "")
        errors = last_result.get("errors", [])
        success = last_result.get("success", False)
        steps = last_result.get("steps", [])
        # Extract execution observations
        exec_notes = []
        for s in steps:
            if s.get("status") == "success" and s.get("observation"):
                obs = s["observation"][:300]
                exec_notes.append(f"  Step {s['step_id']} ({s.get('action', '?')}): {obs}")
        reproduction_summary = "\n".join([
            f"## 上次复现执行记录",
            f"目标: {goal}",
            f"结果: {'成功' if success else '失败'}",
            f"源码: {source_url}" if source_url else "",
            f"错误: {len(errors)} 个" if errors else "",
            "",
            "### 执行步骤详情",
            *exec_notes,
        ])

    # ── 无论文内容且无复现记录时，当作通用 LLM 问答 ──
    if not paper_content and not reproduction_summary:
        thinking = cl.Message(content="🤔 思考中…")
        await thinking.send()
        try:
            llm = get_llm()
            # Build conversation history context
            history_lines = []
            for msg in ctx.get("_messages", [])[-8:]:  # last 8 turns
                role = "用户" if msg["role"] == "user" else "助手"
                history_lines.append(f"{role}: {msg['content'][:300]}")
            history_text = "\n".join(history_lines)
            if history_text:
                prompt = f"你是一个友好的 AI 助手。以下是我们的对话历史：\n\n{history_text}\n\n用户: {question}\n\n助手:"
            else:
                prompt = f"你是一个友好的 AI 助手。请回答用户的问题。\n\n用户: {question}\n\n助手:"
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(
                None, lambda: llm.generate(prompt, max_tokens=1024)
            )
            await thinking.remove()
            await cl.Message(content=resp.content).send()
            _save_message("assistant", resp.content)
        except Exception as e:
            await thinking.remove()
            await cl.Message(content=f"抱歉，回答出错: {e}").send()
        return

    # ── 有论文/复现上下文时 ──
    thinking = cl.Message(content="🤔 正在结合上下文分析…")
    await thinking.send()

    try:
        llm = get_llm()
        # Build prompt with conversation history for context
        history_lines = []
        for msg in ctx.get("_messages", [])[-6:]:  # last 6 turns
            role = "用户" if msg["role"] == "user" else "助手"
            history_lines.append(f"{role}: {msg['content'][:300]}")
        history_text = "\n".join(history_lines)

        prompt_parts = [_QA_PROMPT]
        if history_text:
            prompt_parts.append(f"\n## 对话历史\n{history_text}")
        if reproduction_summary:
            prompt_parts.append(f"\n{reproduction_summary}")
        if paper_content:
            prompt_parts.append(f"\n## 论文内容\n{paper_content[:6000]}")
        prompt_parts.append(f"\n## 用户问题\n{question}")
        prompt = "\n".join(prompt_parts)

        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None, lambda: llm.generate(prompt, max_tokens=2048)
        )
        await thinking.remove()
        await cl.Message(content=resp.content).send()
        _save_message("assistant", resp.content)
    except Exception as e:
        await thinking.remove()
        await cl.Message(content=f"问答出错: {e}").send()


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

    # ── 1. Persistent status indicator (updates in real-time) ──
    status_msg = cl.Message(content="🤖 准备开始…")
    await status_msg.send()

    def update_status(phase: str, detail: str = ""):
        icon = STATUS_ICONS.get(phase, "🤖")
        text = f"{icon} {detail}" if detail else f"{icon} {phase}…"
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(_update_msg(status_msg, text))
        )

    async def _update_msg(msg: cl.Message, text: str):
        msg.content = text
        await msg.update()

    update_status("thinking", "分析意图…")

    # ── 2. Execution step — the "深度思考" panel ──
    step = cl.Step(
        name="Agent Execution",
        type="tool",
        show_input=False,
        default_open=True,
    )
    await step.send()
    # Remove status message once step panel is up
    await status_msg.remove()

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

    # Build conversation history context for the orchestrator
    ctx_conversation = _thread_ctx()
    conv_lines = []
    for msg in ctx_conversation.get("_messages", [])[-10:]:
        role = "用户" if msg["role"] == "user" else "助手"
        conv_lines.append(f"{role}: {msg['content'][:300]}")
    conversation_context = "## 对话历史\n" + "\n".join(conv_lines) if conv_lines else ""

    def _run():
        try:
            orch = Orchestrator(on_step=on_step, on_log=on_log)
            holder["result"] = orch.run(goal, conversation_context=conversation_context).to_dict()
        except Exception as exc:
            holder["error"] = str(exc)
            push({"kind": "error", "message": str(exc)})
        finally:
            push({"kind": "_done"})

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # ── 5. Process events → stream to step with flush ──
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
            # Format step events into lines and stream each line individually
            lines = _format_step_event_lines(ev, plan_items)
            for line in lines:
                if line:
                    await step.stream_token(line + "\n")
                    await step.update()  # Flush to UI immediately
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
                # Map tool_hint to status icon for the live indicator
                tool_hint = ev.get("tool_hint", "")
                phase = PHASE_MAP.get(tool_hint, "")
                if phase:
                    update_status(phase, desc[:60])
                step.name = f"Agent Execution · {desc}"
                await step.update()
            elif t == "sub_step":
                rnd = ev.get("round_num", 0)
                max_rnd = ev.get("max_rounds", 0)
                phase = ev.get("phase", "")
                if phase == "run":
                    step.name = f"Agent Execution · Round {rnd}/{max_rnd}"
                    await step.update()
                elif phase == "reflect":
                    step.name = f"Agent Execution · Reflecting..."
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
    _save_message("assistant", ack_content)

    # Send full report as a separate message if available
    if result and result.get("summary"):
        full_report = result["summary"]
        # Only send as separate message if it's substantially longer
        # than the brief ack (which already includes the summary inline)
        if len(full_report) > 300:
            report_msg = cl.Message(content=f"### 📋 完整复现报告\n\n{full_report}")
            await report_msg.send()
            _save_message("assistant", f"### 📋 完整复现报告\n\n{full_report[:1500]}")

    # Store for context and persist for page-refresh recovery
    if result:
        _thread_ctx()["paper_content"] = result.get("paper_content", "")
        _thread_ctx()["last_result"] = result
        _save_session()

    _thread_ctx()["agent_running"] = False
    _save_session()


# ---------------------------------------------------------------------------
# Format step events for streaming display
# ---------------------------------------------------------------------------

# Box-drawing characters for visual hierarchy in step output
# H_BAR and SECTION are imported from app.chainlit_helpers

def _format_step_event_lines(ev: dict, plan_items: list[dict]) -> list[str]:
    """Convert an orchestrator step event into one or more lines.

    Each line is streamed individually so the UI updates line by line
    rather than showing the entire event at once.
    """
    t = ev.get("type", "")
    sid = ev.get("step_id", "")
    result: list[str] = []

    if t == "plan":
        steps = ev.get("steps", [])
        result.append(SECTION(f"Plan · {len(steps)} steps"))
        for s in steps:
            tool = f" [{s.get('tool_hint')}]" if s.get("tool_hint") else ""
            result.append(f"  [{s['step_id']}] {s['description']}{tool}")
        result.append(H_BAR * 55)
        return result

    elif t == "step_start":
        desc = ev.get("description", "")
        return [SECTION(f"Step {sid}: {desc}")]

    elif t == "react":
        thought = ev.get("thought", "")[:200]
        action = ev.get("action", "")
        result.append(f"  > {thought}")
        if action:
            result.append(f"  action: {action}")
        return result

    elif t == "observation":
        obs = ev.get("observation", "")[:300]
        tag = "[OK]" if ev.get("status") == "success" else "[FAIL]"
        return [f"  {tag}  {obs}"]

    elif t == "reflection":
        analysis = ev.get("analysis", {})
        explanation = analysis.get("explanation", "")[:200]
        error_type = analysis.get("error_type", "")
        if explanation:
            return [f"  [REFLECT] {error_type}: {explanation}"]
        return []

    elif t == "replan":
        new_count = len(ev.get("steps", []))
        return [f"  [REPLAN] {new_count} new steps"]

    elif t == "sub_step":
        phase = ev.get("phase", "")
        rnd = ev.get("round_num", 0)
        max_rnd = ev.get("max_rounds", 0)
        if phase == "run":
            reason = ev.get("detail", "")[:120]
            cmd = ev.get("command", "")[:150]
            result.append(f"    ── Round {rnd}/{max_rnd} ──")
            if reason:
                result.append(f"    {reason}")
            result.append(f"    $ {cmd}")
            return result
        elif phase == "result":
            status = ev.get("status", "")
            detail = ev.get("detail", "")
            tag = "[OK]" if status == "success" else "[FAIL]"
            return [f"    {tag}  {detail}"]
        elif phase == "done":
            detail = ev.get("detail", "")[:200]
            status = ev.get("status", "")
            tag = "[DONE]" if status == "success" else "[FAIL]"
            return [f"    {tag}  {detail}"]
        elif phase == "error":
            detail = ev.get("detail", "")[:200]
            return [f"    [FATAL] {detail}"]
        elif phase == "reflect":
            detail = ev.get("detail", "")[:200]
            return [f"    [REFLECT] {detail}"]

    return []
