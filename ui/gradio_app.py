# ============================================================
# Gradio UI - 前端界面
# ============================================================
"""
Gradio前端界面。

提供交互式的Web界面展示Agent执行过程。
"""

import gradio as gr
from typing import Any

from dto.request import AgentRequest
from dto.trace import StepStatus


class GradioUI:
    """
    Gradio UI类

    使用Gradio构建前端界面。
    """

    def __init__(self, agent_service: Any = None):
        """
        初始化UI

        Args:
            agent_service: Agent服务实例
        """
        self.agent_service = agent_service

    def build_interface(self) -> gr.Blocks:
        """
        构建Gradio界面

        Returns:
            gr.Blocks: Gradio应用
        """
        with gr.Blocks(title="编程教练 Agent") as demo:
            gr.Markdown("# 编程教练 Agent")
            gr.Markdown("一个多模式的编程学习助手")

            # 模式选择
            with gr.Row():
                mode = gr.Dropdown(
                    choices=[
                        "algorithm",
                        "design",
                        "project",
                        "refactor",
                        "learning_path",
                    ],
                    value="algorithm",
                    label="训练模式",
                    info="选择你想要的学习模式",
                )

            # 任务输入
            task_input = gr.Textbox(
                label="任务描述",
                placeholder="输入你的编程任务或问题...",
                lines=5,
            )

            # 执行按钮
            run_btn = gr.Button("开始训练", variant="primary")

            # 输出区域
            with gr.Tab("输出结果"):
                output = gr.Textbox(label="结果", lines=10)

            with gr.Tab("执行过程"):
                # Timeline展示
                timeline = gr.JSON(label="执行Timeline")

            with gr.Tab("历史记录"):
                history = gr.Dataframe(
                    headers=["ID", "模式", "任务", "状态", "时间"],
                    label="历史记录",
                )

            # 事件绑定
            run_btn.click(
                fn=self._run_agent,
                inputs=[mode, task_input],
                outputs=[output, timeline],
            )

        return demo

    async def _run_agent(
        self,
        mode: str,
        task: str,
    ) -> tuple[str, dict[str, Any]]:
        """
        运行Agent

        Args:
            mode: 模式
            task: 任务

        Returns:
            (输出, Timeline)
        """
        if not self.agent_service:
            return "Agent服务未初始化", {}

        request = AgentRequest(
            task=task,
            mode=mode,
        )

        response = await self.agent_service.run_agent(request)

        # 构建Timeline数据
        timeline = {}
        if response.trace:
            timeline = {
                "trace_id": response.trace.trace_id,
                "total_steps": len(response.trace.steps),
                "steps": [
                    {
                        "step": i + 1,
                        "thought": s.thought[:50] + "..." if len(s.thought) > 50 else s.thought,
                        "action": s.action or "-",
                        "status": s.status.value,
                    }
                    for i, s in enumerate(response.trace.steps)
                ],
            }

        output_text = response.output
        if response.error:
            output_text = f"错误: {response.error}"

        return output_text, timeline


def create_app() -> gr.Blocks:
    """
    创建Gradio应用

    Returns:
        gr.Blocks: Gradio应用
    """
    ui = GradioUI()
    return ui.build_interface()


# 主入口
if __name__ == "__main__":
    app = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860)
