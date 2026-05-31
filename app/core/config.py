import os
from typing import Optional

from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class LLMConfig(BaseModel):
    provider: str = Field(default="zhipu")
    model: str = Field(default="glm-4-plus")
    api_key: Optional[str] = None
    base_url: str = Field(default="https://open.bigmodel.cn/api/paas/v4/chat/completions")
    max_tokens: int = Field(default=4096, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)


class AgentConfig(BaseModel):
    max_steps: int = Field(default=10, ge=1)
    max_retries: int = Field(default=3, ge=1)
    replan_threshold: int = Field(default=3, ge=1)
    enable_reflection: bool = True
    enable_memory: bool = True
    workspace_dir: str = Field(default="./workspace")
    python_executable: str = Field(default="")


class LogConfig(BaseModel):
    level: str = Field(default="INFO")
    dir: str = Field(default="./logs")
    retention: str = Field(default="7 days")


class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    log: LogConfig = Field(default_factory=LogConfig)

    @classmethod
    def from_env(cls) -> "Config":
        provider = os.getenv("LLM_PROVIDER", "zhipu").lower()

        # Resolve API key: provider-specific → generic → error
        if provider == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
        elif provider == "zhipu":
            api_key = os.getenv("ZHIPU_API_KEY") or os.getenv("LLM_API_KEY")
        else:
            api_key = os.getenv("LLM_API_KEY")
            
        if not api_key:
            raise RuntimeError(
                f"No API key found for provider '{provider}'. "
                f"Set {provider.upper()}_API_KEY or LLM_API_KEY in .env file."
            )

        # Default model & base_url per provider
        provider_defaults = {
            "deepseek": {
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1/chat/completions",
            },
            "zhipu": {
                "model": "glm-4-plus",
                "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            },
        }
        defaults = provider_defaults.get(provider, provider_defaults["zhipu"])

        return cls(
            llm=LLMConfig(
                provider=provider,
                model=os.getenv("LLM_MODEL", defaults["model"]),
                api_key=api_key,
                base_url=os.getenv("LLM_BASE_URL", defaults["base_url"]),
                max_tokens=int(os.getenv("LLM_MAX_TOKENS", "65536")),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            ),
            agent=AgentConfig(
                max_steps=int(os.getenv("AGENT_MAX_STEPS", "10")),
                max_retries=int(os.getenv("AGENT_MAX_RETRIES", "3")),
                replan_threshold=int(os.getenv("AGENT_REPLAN_THRESHOLD", "3")),
                enable_reflection=os.getenv("AGENT_ENABLE_REFLECTION", "true").lower()
                == "true",
                enable_memory=os.getenv("AGENT_ENABLE_MEMORY", "true").lower()
                == "true",
                workspace_dir=os.getenv("WORKSPACE_DIR", "./workspace"),
                python_executable=os.getenv("PYTHON_EXECUTABLE", ""),
            ),
            log=LogConfig(
                level=os.getenv("LOG_LEVEL", "INFO"),
                dir=os.getenv("LOG_DIR", "./logs"),
                retention=os.getenv("LOG_RETENTION", "7 days"),
            ),
        )


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reload_config() -> Config:
    global _config
    _config = Config.from_env()
    return _config
