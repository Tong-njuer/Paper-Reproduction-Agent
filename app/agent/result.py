"""
AgentResult — 编排器执行结果的数据类。

保存完整的执行记录，包括目标、步骤详情、错误列表、论文信息等。
"""

from typing import Dict, List


class AgentResult:
    """Agent 执行结果，由 Orchestrator.run() 返回。"""

    def __init__(self):
        self.success: bool = False
        self.goal: str = ""
        self.summary: str = ""
        self.source_url: str = ""
        self.paper_content: str = ""
        self.paper_info: Dict = {}
        self.steps: List[Dict] = []
        self.errors: List[str] = []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "goal": self.goal,
            "summary": self.summary,
            "source_url": self.source_url,
            "paper_content": self.paper_content,
            "paper_info": self.paper_info,
            "steps": self.steps,
            "errors": self.errors,
        }
