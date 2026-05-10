# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A conversational AI agent for paper reproduction — users describe a paper or repo, and the agent autonomously searches, clones, sets up environments, and executes experiments. The system implements the **Planner → ReAct → Reflection → Memory** agent architecture with a Chainlit chat frontend.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Chainlit frontend (development)
chainlit run app/chainlit_app.py --host 0.0.0.0 --port 8000

# Docker build and run
docker-compose up --build

# Environment setup
cp .env.example .env   # then edit ZHIPU_API_KEY
```

There is no test suite or linting configuration in this project.

## Architecture

### Agent loop (the core orchestration)

`app/agent/orchestrator.py` — `Orchestrator.run(goal)` runs the main loop:

1. **Planner** (`planner.py`) — decomposes the goal into `PlanStep` objects, each with a `tool_hint` binding it to a specific tool. Supports LLM-driven planning and keyword-based fallback plans (predefined step sequences like `FULL_REPRODUCTION_PLAN`).
2. **ReAct** (`react.py`) — for each step, determines tool arguments via LLM. The tool itself is **locked** by the planner (`force_tool`); the LLM only fills in args.
3. **Execution** — the tool runs, producing an observation.
4. **Verification** — `_verify_step_completion()` checks that the step actually achieved its goal (e.g., clone verification checks `.git` exists on disk), not just that the tool returned success.
5. **On failure**: first tries **ErrorHandlerTool** (fast deterministic fix), then **Reflection** (LLM analysis with L1/L2/L3 levels), then **Replan** if consecutive failures exceed threshold.
6. **Memory** (`memory.py`) — short-term (last N steps) and long-term (error→fix patterns persisted to `data/memory/long_term_memory.json`).

### Args enrichment (anti-hallucination)

`Orchestrator._enrich_args()` is a critical layer that overrides LLM-generated args with deterministic values from prior step outputs. For example, if `source_tool` found `github.com/google-research/simclr` but the LLM invents `github.com/ningyuanshao/SimCLR` for the clone step, the orchestrator replaces it with the stored URL. This applies to `clone_tool` URLs, `run_tool` commands, `fetch_tool` URLs, and `execute_session_tool` repo paths.

### Tool registry

`app/tools/__init__.py` — `_build_registry()` registers all tools at import time into `TOOL_REGISTRY`. Current tools:

| Tool | Status | Purpose |
|------|--------|---------|
| `execute_session_tool` | **Active** | Conversational LLM-driven loop: creates venv, installs deps, runs commands, diagnoses errors — replaces the old rigid pipeline |
| `search_tool` | Active | Multi-source paper search (arXiv, Semantic Scholar, web) |
| `fetch_tool` | Active | Fetch and extract paper/web content |
| `source_tool` | Active | Find official repo URLs from paper references |
| `clone_tool` | Active | Git clone repos into `workspace/` with multi-branch fallback and GITHUB_TOKEN auth |
| `error_handler_tool` | Active | Deterministic error fixes (install missing module, recreate venv, find entry files) |
| `report_tool` | Active | Generate final summary report (called directly by orchestrator, bypasses ReAct) |
| `setup_tool` | **Deprecated** | Old venv + pip install tool — use `execute_session_tool` instead |
| `execute_tool` | **Deprecated** | Old single-command runner |
| `read_repo_tool` | **Deprecated** | Old repo analysis tool |
| `plan_run_tool` | **Deprecated** | Old command-planning tool |
| `run_tool` | **Deprecated** | Old execution tool |

The planner prompt explicitly tells the LLM not to use the deprecated tools. The `execute_session_tool` is preferred because it gives the LLM a multi-turn conversation loop where it can see command output, diagnose errors, and retry — mirroring how a human developer works.

### State machine

`app/agent/state.py` — `StateManager` tracks the agent lifecycle through `IDLE → PLANNING → EXECUTING → REFLECTING → REPLANNING → COMPLETED/FAILED`. Enforces valid transitions and terminates at max steps or terminal states.

### Frontend

`app/chainlit_app.py` — Chainlit app with:
- **Intent classification**: keyword-based + LLM fallback to decide between simple QA and agent execution
- **Thread-safe context isolation**: module-level dict keyed by thread ID (since `cl.user_session` is shared across threads in a tab)
- **Streaming execution panel**: the agent runs in a background thread, pushes events through an `asyncio.Queue`, and the Chainlit step streams tokens in real-time (like ChatGPT's "深度思考" panel)
- **Context enrichment**: follow-up messages are enriched with prior results (e.g., "clone the repo" auto-appends the last found repo URL)

### LLM interface

`app/core/llm.py` — wraps Zhipu AI's OpenAI-compatible chat completions API. `generate_structured()` has a multi-strategy JSON parser: direct parse → markdown code fence extraction → brace matching. Configured via `ZHIPU_API_KEY` and `LLM_MODEL` env vars (defaults to `glm-4-plus`).

### Configuration

`app/core/config.py` — Pydantic models (`LLMConfig`, `AgentConfig`, `LogConfig`) loaded from env vars via `Config.from_env()`. Singleton accessed via `get_config()`.

## Key design patterns

- **Tools inform planning, not the reverse**: the planner prompt includes the full tool registry so it understands available capabilities.
- **Steps are verified, not just executed**: tool success ≠ step success. The orchestrator has per-tool verification logic.
- **Deterministic context passing beats LLM memory**: `_step_context` dict carries data between steps (repo URLs, commands, paths) rather than trusting the LLM to recall them from conversation history.
- **Error recovery is tiered**: fast deterministic fix first (ErrorHandlerTool), then LLM analysis (Reflection), then structural change (Replan).
- **Cross-tool fix allowlist**: `_allow_cross_tool_fix()` defines valid tool-switch transitions during retry (e.g., `execute_tool` import error → retry with `setup_tool`).
