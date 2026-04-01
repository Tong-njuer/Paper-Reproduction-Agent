# ============================================================
# TrainingMode - 训练模式基类
# ============================================================
"""
训练模式基类。

设计思路：
- 每种训练场景对应一个具体的模式类
- 模式定义了该场景特有的系统提示词、工具选择、评估标准
- 模式可切换，Agent自动适应不同的训练需求
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tools.base import Tool


@dataclass
class ModeConfig:
    """
    模式配置

    包含模式的配置参数。
    """
    # 模式标识
    mode_name: str                     # 模式名称
    display_name: str                  # 显示名称
    description: str                   # 模式描述

    # 提示词
    system_prompt: str                 # 系统提示词
    user_prompt_template: str          # 用户提示模板

    # 工具配置
    required_tools: list[str] = field(default_factory=list)  # 必须的工具
    optional_tools: list[str] = field(default_factory=list)   # 可选的工具

    # 执行配置
    max_iterations: int = 10           # 最大迭代次数
    timeout_seconds: int = 300         # 超时时间

    # 评估配置
    evaluation_criteria: dict[str, Any] = field(default_factory=dict)

    # 元数据
    tags: list[str] = field(default_factory=list)  # 标签，用于搜索
    version: str = "1.0"              # 版本号


class ModeStrategy(ABC):
    """
    模式策略抽象基类

    定义特定模式的策略逻辑。
    每个模式可以实现自己的：
    - 计划策略
    - 执行策略
    - 评估策略
    - 反思策略
    """

    @property
    @abstractmethod
    def config(self) -> ModeConfig:
        """获取模式配置"""
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        获取系统提示词

        用于初始化LLM的system角色。
        不同模式有不同的指导原则。
        """
        pass

    @abstractmethod
    def select_tools(self) -> list[type[Tool]]:
        """
        选择该模式需要的工具

        Returns:
            list[Tool]: 工具类列表
        """
        pass

    @abstractmethod
    def create_mode_components(
        self,
    ) -> "ModeComponents":
        """
        创建模式专用的组件

        返回该模式特有的组件配置。

        Returns:
            ModeComponents: 组件配置
        """
        pass

    def pre_execute_hook(
        self, task: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        执行前钩子

        在Agent执行前做一些准备。
        默认实现返回原上下文。
        """
        return context

    def post_execute_hook(
        self, result: Any, context: dict[str, Any]
    ) -> Any:
        """
        执行后钩子

        在Agent执行后做一些后处理。
        默认实现返回原结果。
        """
        return result


@dataclass
class ModeComponents:
    """
    模式组件配置

    包含一个模式所需的各类组件。
    """
    # Planner配置
    planner_type: str                  # Planner类型
    planner_config: dict[str, Any] = field(default_factory=dict)

    # Evaluator配置
    evaluator_type: str               # Evaluator类型
    evaluator_config: dict[str, Any] = field(default_factory=dict)

    # Reflector配置
    reflector_type: str = "default"   # Reflector类型
    reflector_config: dict[str, Any] = field(default_factory=dict)

    # 额外的模式特定配置
    extra_config: dict[str, Any] = field(default_factory=dict)


class TrainingMode(ModeStrategy):
    """
    训练模式基类

    所有具体模式的基类。
    提供通用的模式和配置管理。
    """

    def __init__(self):
        """初始化训练模式"""
        self._config = self._create_config()
        self._setup_components()

    @property
    def config(self) -> ModeConfig:
        """获取模式配置"""
        return self._config

    @abstractmethod
    def _create_config(self) -> ModeConfig:
        """
        创建模式配置

        子类实现，返回具体的配置。
        """
        pass

    def _setup_components(self) -> None:
        """设置组件"""
        self._components = self.create_mode_components()

    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        pass

    @abstractmethod
    def select_tools(self) -> list[type[Tool]]:
        """选择工具"""
        pass

    @abstractmethod
    def create_mode_components(self) -> ModeComponents:
        """创建模式组件"""
        pass


# ============================================================
# 模式注册表
# ============================================================

class ModeRegistry:
    """
    模式注册表

    管理所有可用的训练模式。
    支持按名称获取模式。
    """

    def __init__(self):
        """初始化注册表"""
        self._modes: dict[str, TrainingMode] = {}

    def register(self, mode: TrainingMode) -> None:
        """
        注册模式

        Args:
            mode: 训练模式实例
        """
        self._modes[mode.config.mode_name] = mode

    def get(self, name: str) -> TrainingMode | None:
        """
        获取模式

        Args:
            name: 模式名称

        Returns:
            TrainingMode: 模式实例
        """
        return self._modes.get(name)

    def list_modes(self) -> list[str]:
        """列出所有模式"""
        return list(self._modes.keys())

    def get_mode_info(self, name: str) -> ModeConfig | None:
        """
        获取模式信息

        Args:
            name: 模式名称

        Returns:
            ModeConfig: 模式配置
        """
        mode = self.get(name)
        return mode.config if mode else None
