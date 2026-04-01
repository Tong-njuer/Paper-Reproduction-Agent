# ============================================================
# ReasoningRegistry - 推理机制注册器
# ============================================================
"""
推理机制注册器。

用于：
1. 注册和管理多种推理引擎
2. 按名称获取推理引擎
3. 支持动态切换推理策略
"""

from typing import Any

from agent.reasoning.base import ReasoningEngine


class ReasoningRegistry:
    """
    推理引擎注册器

    实现简单的注册表模式，支持：
    - 注册新的推理引擎
    - 按名称获取推理引擎
    - 列出所有可用引擎
    - 默认引擎设置
    """

    def __init__(self):
        """初始化注册器"""
        self._engines: dict[str, ReasoningEngine] = {}
        self._default_engine: str | None = None

    def register(
        self,
        name: str,
        engine: ReasoningEngine,
        set_as_default: bool = False,
    ) -> None:
        """
        注册推理引擎

        Args:
            name: 引擎名称
            engine: 引擎实例
            set_as_default: 是否设为默认引擎
        """
        if not isinstance(engine, ReasoningEngine):
            raise TypeError(
                f"Engine must be instance of ReasoningEngine, "
                f"got {type(engine).__name__}"
            )

        self._engines[name] = engine

        if set_as_default or self._default_engine is None:
            self._default_engine = name

    def unregister(self, name: str) -> bool:
        """
        注销推理引擎

        Args:
            name: 引擎名称

        Returns:
            bool: 是否成功注销
        """
        if name in self._engines:
            del self._engines[name]

            # 如果是默认引擎，重设默认
            if self._default_engine == name:
                self._default_engine = (
                    next(iter(self._engines)) if self._engines else None
                )

            return True

        return False

    def get(self, name: str) -> ReasoningEngine | None:
        """
        获取推理引擎

        Args:
            name: 引擎名称

        Returns:
            ReasoningEngine: 引擎实例，如果不存在返回None
        """
        return self._engines.get(name)

    def get_default(self) -> ReasoningEngine | None:
        """
        获取默认推理引擎

        Returns:
            ReasoningEngine: 默认引擎实例
        """
        if self._default_engine is None:
            return None
        return self._engines.get(self._default_engine)

    def list_engines(self) -> list[str]:
        """
        列出所有注册的引擎名称

        Returns:
            list[str]: 引擎名称列表
        """
        return list(self._engines.keys())

    def set_default(self, name: str) -> bool:
        """
        设置默认引擎

        Args:
            name: 引擎名称

        Returns:
            bool: 是否设置成功
        """
        if name in self._engines:
            self._default_engine = name
            return True
        return False

    def create_engine(self, name: str, **kwargs) -> ReasoningEngine | None:
        """
        工厂方法：创建并注册引擎

        支持通过名称快捷创建常用引擎。

        Args:
            name: 引擎名称
            **kwargs: 引擎构造参数

        Returns:
            ReasoningEngine: 创建的引擎实例
        """
        # 预定义的引擎创建函数
        creators = {
            "react": self._create_react,
            "reflexion": self._create_reflexion,
        }

        creator = creators.get(name.lower())
        if creator:
            engine = creator(**kwargs)
            self.register(name, engine, set_as_default=True)
            return engine

        return None

    def _create_react(self, **kwargs) -> "ReActEngine":
        """创建 ReAct 引擎"""
        from agent.reasoning.react import ReActEngine
        return ReActEngine(llm_client=kwargs.get("llm_client"))

    def _create_reflexion(self, **kwargs) -> "ReflexionEngine":
        """创建 Reflexion 引擎"""
        from agent.reasoning.reflexion import ReflexionEngine
        return ReflexionEngine(llm_client=kwargs.get("llm_client"))

    def __contains__(self, name: str) -> bool:
        """支持 'in' 操作符"""
        return name in self._engines

    def __len__(self) -> int:
        """支持 len() 操作符"""
        return len(self._engines)
