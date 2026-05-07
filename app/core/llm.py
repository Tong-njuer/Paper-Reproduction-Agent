import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel

from app.core.config import get_config
from app.core.logging import get_logger


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str


class LLMInterface:
    def __init__(self, api_key: Optional[str] = None):
        config = get_config().llm
        self.api_key = api_key or config.api_key
        if not self.api_key:
            raise RuntimeError("No API key configured. Set ZHIPU_API_KEY in .env")
        self.model = config.model
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature
        self.base_url = config.base_url
        self._log = get_logger("llm")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        self._log.info(f"Request: model={self.model} temp={temp} max_tokens={tokens} prompt_len={len(prompt)}")

        start = datetime.now()
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temp,
                "max_tokens": tokens,
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            elapsed = (datetime.now() - start).total_seconds()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            finish = data.get("choices", [{}])[0].get("finish_reason", "stop")

            self._log.info(
                f"Response: elapsed={elapsed:.2f}s "
                f"tokens={usage.get('completion_tokens', 0)} "
                f"finish={finish}"
            )

            return LLMResponse(
                content=content,
                model=data.get("model", self.model),
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                },
                finish_reason=finish,
            )

        except requests.exceptions.RequestException as e:
            self._log.error(f"API request failed: {e}")
            raise RuntimeError(f"LLM API request failed: {e}")
        except (KeyError, json.JSONDecodeError) as e:
            self._log.error(f"Response parse error: {e}")
            raise RuntimeError(f"Failed to parse LLM response: {e}")

    def generate_structured(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        response = self.generate(prompt, system_prompt)
        content = response.content

        # Strategy 1: direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Strategy 2: extract from ```json block
        result = self._extract_json_block(content, "json")
        if result is not None:
            return result

        # Strategy 3: extract from any ``` block
        result = self._extract_json_block(content)
        if result is not None:
            return result

        # Strategy 4: brace matching
        result = self._extract_by_braces(content)
        if result is not None:
            return result

        self._log.error(f"Failed to parse structured response: {content[:300]}")
        raise RuntimeError(f"Failed to parse JSON from LLM response: {content[:200]}")

    @staticmethod
    def _extract_json_block(content: str, tag: str = "") -> Optional[Dict[str, Any]]:
        fence = f"```{tag}" if tag else "```"
        start = content.find(fence)
        if start == -1:
            return None
        start += len(fence)
        nl = content.find("\n", start)
        if nl != -1:
            start = nl + 1
        end = content.find("```", start)
        if end == -1:
            end = len(content)
        try:
            return json.loads(content[start:end].strip())
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_by_braces(content: str) -> Optional[Dict[str, Any]]:
        start = content.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(content[start : i + 1])
                    except json.JSONDecodeError:
                        return None
        return None


_llm: Optional[LLMInterface] = None


def get_llm() -> LLMInterface:
    global _llm
    if _llm is None:
        _llm = LLMInterface()
    return _llm
