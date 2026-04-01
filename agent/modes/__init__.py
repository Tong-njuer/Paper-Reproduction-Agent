# ============================================================
# modes/ 模块 - 多模式支持
# ============================================================
"""
训练模式模块，支持不同类型的训练场景：

1. AlgorithmMode - 算法训练
   出题 → 写代码 → 自动测试 → debug → 优化

2. DesignMode - 设计训练
   OOP结构分析与改进、设计模式应用

3. ProjectMode - 项目引导
   从0到1逐步完成项目

4. RefactorMode - 代码重构
   代码质量提升、坏味道识别

5. LearningPathMode - 学习路径
   长期能力提升规划
"""

from agent.modes.base import (
    TrainingMode,
    ModeStrategy,
    ModeRegistry,
)

__all__ = [
    "TrainingMode",
    "ModeStrategy",
    "ModeRegistry",
]
