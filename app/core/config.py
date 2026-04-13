# ============================================================
# 配置模块
# ============================================================
# 管理 Agent 的所有配置设置。
# 支持环境变量和配置文件。
#
# Console Output: 初始化时显示配置信息
# ============================================================

import os
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# 从 .env 文件加载环境变量
load_dotenv()


class LLMConfig(BaseModel):
    """
    LLM（大语言模型）配置。

    Attributes:
        provider: LLM 提供商名称（如 'zhipu'）
        model: 模型标识符（如 'glm-5.1'）
        api_key: API 密钥
        max_tokens: 响应最大 token 数
        temperature: 采样温度（0.0-1.0）
    """
    provider: str = Field(default="zhipu", description="LLM provider (zhipu/glm)")
    model: str = Field(
        default="glm-5.1",
        description="Model identifier (glm-5.1, glm-4 etc.)"
    )
    api_key: Optional[str] = Field(default=None, description="API key")
    max_tokens: int = Field(default=4096, description="Max tokens in response")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0, description="Sampling temperature")


class AgentConfig(BaseModel):
    """
    Agent 行为配置。

    Attributes:
        max_steps: 强制终止前的最大步数
        max_retries: 失败操作的最大重试次数
        replan_threshold: 触发重新规划的连续失败次数
        enable_reflexion: 是否启用自我反思
        enable_memory: 是否启用记忆系统
    """
    max_steps: int = Field(default=50, description="Max steps before termination")
    max_retries: int = Field(default=3, description="Max retry attempts")
    replan_threshold: int = Field(default=3, description="Failures before replanning")
    enable_reflexion: bool = Field(default=True, description="Enable self-reflection")
    enable_memory: bool = Field(default=True, description="Enable memory system")


class MemoryConfig(BaseModel):
    """
    记忆系统配置。

    Attributes:
        memory_dir: 持久化记忆存储目录
        short_term_max: 短期记忆最大条目数
        long_term_enabled: 是否持久化长期记忆
    """
    memory_dir: str = Field(default="./data/memory", description="Memory storage directory")
    short_term_max: int = Field(default=10, description="Max short-term memory items")
    long_term_enabled: bool = Field(default=True, description="Enable long-term memory")


class LoggingConfig(BaseModel):
    """
    日志配置。

    Attributes:
        level: 日志级别（DEBUG, INFO, WARNING, ERROR）
        log_dir: 日志文件目录
        console_output: 是否输出到控制台
    """
    level: str = Field(default="INFO", description="Log level")
    log_dir: str = Field(default="./data/logs", description="Log directory")
    console_output: bool = Field(default=True, description="Print to console")


class Config(BaseModel):
    """
    根配置对象。

    包含 Agent 的所有配置部分。
    从环境变量加载，优先使用环境变量值。
    """
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_env(cls) -> "Config":
        """
        从环境变量创建配置对象。

        Environment variables take precedence over defaults.
        Variable naming convention: SECTION_VARIABLE (e.g., AGENT_MAX_STEPS)

        Returns:
            Config: Configuration instance
        """
        # 从环境变量加载 API 密钥
        api_key = os.getenv("ZHIPU_API_KEY")

        return cls(
            llm=LLMConfig(
                provider=os.getenv("LLM_PROVIDER", "zhipu"),
                model=os.getenv("LLM_MODEL", "glm-5.1"),
                api_key=api_key,
                max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            ),
            agent=AgentConfig(
                max_steps=int(os.getenv("AGENT_MAX_STEPS", "50")),
                max_retries=int(os.getenv("AGENT_MAX_RETRIES", "3")),
                replan_threshold=int(os.getenv("AGENT_REPLAN_THRESHOLD", "3")),
                enable_reflexion=os.getenv("AGENT_ENABLE_REFLEXION", "true").lower() == "true",
                enable_memory=os.getenv("AGENT_ENABLE_MEMORY", "true").lower() == "true",
            ),
            memory=MemoryConfig(
                memory_dir=os.getenv("MEMORY_DIR", "./data/memory"),
                short_term_max=int(os.getenv("MEMORY_SHORT_TERM_MAX", "10")),
                long_term_enabled=os.getenv("MEMORY_LONG_TERM_ENABLED", "true").lower() == "true",
            ),
            logging=LoggingConfig(
                level=os.getenv("LOG_LEVEL", "INFO"),
                log_dir=os.getenv("LOG_DIR", "./data/logs"),
                console_output=os.getenv("LOG_CONSOLE", "true").lower() == "true",
            ),
        )

    def print_config(self) -> None:
        """
        Print current configuration to console.
        Useful for debugging and verification.
        """
        print("\n" + "=" * 60)
        print("[CONFIG] Agent Configuration")
        print("=" * 60)

        print("\n[LLM] LLM Configuration:")
        print(f"   Provider:    {self.llm.provider}")
        print(f"   Model:       {self.llm.model}")
        print(f"   Max Tokens:  {self.llm.max_tokens}")
        print(f"   Temperature: {self.llm.temperature}")
        print(f"   API Key:     {'[OK] Set' if self.llm.api_key else '[--] Not Set'}")

        print("\n[AGENT] Agent Configuration:")
        print(f"   Max Steps:         {self.agent.max_steps}")
        print(f"   Max Retries:       {self.agent.max_retries}")
        print(f"   Replan Threshold:  {self.agent.replan_threshold}")
        print(f"   Reflexion:         {'[ON] Enabled' if self.agent.enable_reflexion else '[OFF] Disabled'}")
        print(f"   Memory:            {'[ON] Enabled' if self.agent.enable_memory else '[OFF] Disabled'}")

        print("\n[MEMORY] Memory Configuration:")
        print(f"   Memory Dir:        {self.memory.memory_dir}")
        print(f"   Short-term Max:    {self.memory.short_term_max}")
        print(f"   Long-term:         {'[ON] Enabled' if self.memory.long_term_enabled else '[OFF] Disabled'}")

        print("\n[LOG] Logging Configuration:")
        print(f"   Level:          {self.logging.level}")
        print(f"   Log Dir:        {self.logging.log_dir}")
        print(f"   Console Output: {'[ON] Enabled' if self.logging.console_output else '[OFF] Disabled'}")

        print("\n" + "=" * 60 + "\n")


# ============================================================
# Global Config Instance
# ============================================================
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the global configuration instance.

    Loads from environment on first call, returns cached instance after.

    Returns:
        Config: The global configuration object
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reload_config() -> Config:
    """
    Force reload configuration from environment.

    Returns:
        Config: The reloaded configuration object
    """
    global _config
    _config = Config.from_env()
    return _config
