# ============================================================
# LLM Interface Module
# ============================================================
# Provides unified interface for Large Language Model interactions.
# Currently supports Zhipu AI GLM-5.1 API.
#
# Console Output:
#   - API connection status
#   - Request/response summaries
#   - Error messages
# ============================================================

import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

# Third-party imports
import requests
from pydantic import BaseModel

# Local imports
from app.core.config import get_config


class LLMResponse(BaseModel):
    """
    Standardized LLM response object.

    Attributes:
        content: The text content of the response
        model: Model used for generation
        usage: Token usage statistics
        finish_reason: Why generation stopped
        raw_response: Original API response
    """
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str
    raw_response: Any


class LLMInterface:
    """
    LLM interaction interface.

    Provides a clean abstraction over the underlying LLM API
    with standardized request/response handling.

    Attributes:
        config: LLM configuration
        api_key: API key for authentication
        model: Model identifier
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
    """

    # GLM API endpoint (Zhipu AI)
    GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize LLM Interface.

        Args:
            api_key: API key for authentication. If None, reads from config/env.
        """
        self.config = get_config().llm
        self.api_key = api_key or self.config.api_key

        # Check if API key is available
        if self.api_key:
            print(f"[OK] LLM Interface initialized with GLM API (model: {self.config.model})")
        else:
            print("[!]  LLM Interface initialized WITHOUT API key - running in demo mode")

        self.model = self.config.model
        self.max_tokens = self.config.max_tokens
        self.temperature = self.config.temperature

    def is_available(self) -> bool:
        """
        Check if LLM is available (API key configured).

        Returns:
            bool: True if API key is set
        """
        return self.api_key is not None

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt for context
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Returns:
            LLMResponse: Standardized response object

        Raises:
            RuntimeError: If API key not configured or API call fails
        """
        if not self.api_key:
            # Demo mode - return placeholder response
            return LLMResponse(
                content=f"[DEMO MODE] Received prompt: {prompt[:100]}...",
                model=self.model,
                usage={"prompt_tokens": 0, "completion_tokens": 0},
                finish_reason="demo_mode",
                raw_response=None,
            )

        # Use defaults if not specified
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens

        # Build messages list (GLM format)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Print request summary
        print(f"\n[OUT] LLM Request:")
        print(f"   Model:       {self.model}")
        print(f"   Temp:        {temp}")
        print(f"   Max Tokens:  {tokens}")
        print(f"   Prompt Len:  {len(prompt)} chars")

        start_time = datetime.now()

        try:
            # Call GLM API
            response = self._call_glm_api(messages, temp, tokens)

            elapsed = (datetime.now() - start_time).total_seconds()

            # Extract response content
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Extract usage information
            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            # Extract finish reason
            finish_reason = response.get("choices", [{}])[0].get("finish_reason", "stop")

            # Build response object
            llm_response = LLMResponse(
                content=content,
                model=response.get("model", self.model),
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                finish_reason=finish_reason,
                raw_response=response,
            )

            # Print response summary
            print(f"\n[IN] LLM Response:")
            print(f"   Elapsed:           {elapsed:.2f}s")
            print(f"   Completion Tokens: {completion_tokens}")
            print(f"   Finish:            {finish_reason}")
            print(f"   Content Preview:   {content[:200]}...")

            return llm_response

        except requests.exceptions.RequestException as e:
            print(f"\n[X] LLM API Request Error: {e}")
            raise RuntimeError(f"LLM API request failed: {e}")

        except (KeyError, json.JSONDecodeError) as e:
            print(f"\n[X] LLM API Response Parse Error: {e}")
            raise RuntimeError(f"Failed to parse GLM API response: {e}")

        except Exception as e:
            print(f"\n[X] LLM Unexpected Error: {e}")
            raise

    def _call_glm_api(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """
        Call the GLM API.

        Args:
            messages: List of message dicts with role and content
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Dict: API response as dict
        """
        # GLM API request format
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        print(f"   API URL:    {self.GLM_API_URL}")
        print(f"   Auth:       Bearer {self.api_key[:10]}...")

        # Make the API call
        response = requests.post(
            self.GLM_API_URL,
            headers=headers,
            json=payload,
            timeout=120,  # 2 minute timeout
        )

        # Check HTTP errors
        response.raise_for_status()

        return response.json()

    def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response.

        Assumes the model returns valid JSON and parses it.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            Dict: Parsed JSON response

        Raises:
            RuntimeError: If JSON parsing fails
        """
        response = self.generate(prompt, system_prompt)

        try:
            # Try to parse as JSON
            return json.loads(response.content)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            content = response.content
            # Look for JSON block
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                if end > start:
                    return json.loads(content[start:end].strip())
            elif "```" in content:
                # Handle code blocks without json tag
                start = content.find("```") + 3
                end = content.find("```", start)
                if end > start:
                    return json.loads(content[start:end].strip())
            elif "{" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                if end > start:
                    return json.loads(content[start:end])

            raise RuntimeError(f"Failed to parse structured response: {content[:200]}")


# ============================================================
# Global LLM Interface Instance
# ============================================================
_llm_interface: Optional[LLMInterface] = None


def get_llm() -> LLMInterface:
    """
    Get the global LLM interface instance.

    Returns:
        LLMInterface: The global instance
    """
    global _llm_interface
    if _llm_interface is None:
        _llm_interface = LLMInterface()
    return _llm_interface
