"""ConfigTool — display current agent configuration.

Shows LLM settings, agent parameters, workspace path, pip mirror,
and other runtime configuration so the user understands the current
operating environment.
"""

import os

from app.core.config import get_config
from app.tools import BaseTool, ToolResult


class ConfigTool(BaseTool):
    name = "config_tool"
    description = (
        "查看当前 Agent 系统的全部配置: LLM、Agent参数、工作区路径、"
        "pip镜像等。无需参数。"
    )

    def execute(self, **kwargs) -> ToolResult:
        config = get_config()

        lines = ["## 当前系统配置", ""]

        # LLM
        llm = config.llm
        lines.append("### LLM")
        lines.append(f"  provider:    {llm.provider}")
        lines.append(f"  model:       {llm.model}")
        lines.append(f"  max_tokens:  {llm.max_tokens}")
        lines.append(f"  temperature: {llm.temperature}")
        if llm.base_url:
            lines.append(f"  base_url:    {llm.base_url}")
        lines.append("")

        # Agent
        agent = config.agent
        lines.append("### Agent")
        lines.append(f"  max_steps:        {agent.max_steps}")
        lines.append(f"  max_retries:      {agent.max_retries}")
        lines.append(f"  replan_threshold: {agent.replan_threshold}")
        lines.append(f"  enable_reflection: {agent.enable_reflection}")
        lines.append(f"  enable_memory:    {agent.enable_memory}")
        lines.append(f"  workspace_dir:    {agent.workspace_dir}")
        lines.append("")

        # Logging
        log_cfg = config.log
        lines.append("### 日志")
        lines.append(f"  level:     {log_cfg.level}")
        lines.append(f"  dir:       {log_cfg.dir}")
        lines.append(f"  retention: {log_cfg.retention}")
        lines.append("")

        # Environment
        lines.append("### 环境变量")
        pip_index = os.environ.get("PIP_INDEX_URL",
                                   "https://pypi.tuna.tsinghua.edu.cn/simple")
        github_token = os.environ.get("GITHUB_TOKEN", "")
        python_exe = os.environ.get("PYTHON_EXECUTABLE", "(系统默认)")

        lines.append(f"  PIP_INDEX_URL:    {pip_index}")
        lines.append(f"  GITHUB_TOKEN:     {'已设置' if github_token else '未设置'}")
        lines.append(f"  PYTHON_EXECUTABLE: {python_exe}")
        lines.append(f"  ZHIPU_API_KEY:    {'已设置' if os.environ.get('ZHIPU_API_KEY') else '未设置'}")

        return self._ok(output="\n".join(lines))
