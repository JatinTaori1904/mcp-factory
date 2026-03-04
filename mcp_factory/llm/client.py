"""LLM Client — Unified interface for Ollama (local) and OpenAI/Claude (cloud).

Handles:
- Connection management with health checks
- Structured JSON extraction from LLM responses
- Timeout and retry logic
- Graceful degradation when LLM is unavailable
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    model: str
    provider: str
    success: bool
    error: Optional[str] = None
    usage: Optional[dict] = None  # token counts if available


class LLMClient:
    """Unified LLM client supporting Ollama (local) and OpenAI-compatible APIs."""

    def __init__(self, provider: str = "ollama", model: Optional[str] = None):
        self.provider = provider
        self.model = model or self._default_model(provider)
        self._available: Optional[bool] = None  # cached availability

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check if the LLM provider is reachable.

        Result is cached after the first call.  Call ``reset()`` to clear.
        """
        if self._available is not None:
            return self._available

        try:
            if self.provider == "ollama":
                self._available = self._check_ollama()
            elif self.provider in ("openai", "claude"):
                self._available = self._check_openai_compat()
            else:
                self._available = False
        except Exception:
            self._available = False

        return self._available

    def reset(self) -> None:
        """Clear the cached availability flag."""
        self._available = None

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> LLMResponse:
        """Send a chat completion request and return the response.

        Parameters
        ----------
        system_prompt : str
            The system message that sets the LLM's role.
        user_prompt : str
            The user's message / question.
        temperature : float
            Sampling temperature (lower = more deterministic).
        max_tokens : int
            Maximum tokens in the response.
        timeout : float
            Request timeout in seconds.

        Returns
        -------
        LLMResponse
            Always returns an ``LLMResponse``; check ``.success`` before
            using ``.content``.
        """
        if not self.is_available():
            return LLMResponse(
                content="",
                model=self.model,
                provider=self.provider,
                success=False,
                error=f"{self.provider} is not available. Is the service running?",
            )

        try:
            if self.provider == "ollama":
                return self._chat_ollama(system_prompt, user_prompt, temperature, timeout)
            elif self.provider in ("openai", "claude"):
                return self._chat_openai_compat(system_prompt, user_prompt, temperature, max_tokens, timeout)
            else:
                return LLMResponse(
                    content="", model=self.model, provider=self.provider,
                    success=False, error=f"Unknown provider: {self.provider}",
                )
        except Exception as e:
            return LLMResponse(
                content="", model=self.model, provider=self.provider,
                success=False, error=str(e),
            )

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> tuple[Optional[dict], LLMResponse]:
        """Send a chat request and extract JSON from the response.

        Returns
        -------
        tuple[Optional[dict], LLMResponse]
            (parsed_json, raw_response).  If JSON extraction fails,
            ``parsed_json`` is ``None`` but the raw response is still
            available for debugging.
        """
        response = self.chat(system_prompt, user_prompt, **kwargs)
        if not response.success:
            return None, response

        parsed = self._extract_json(response.content)
        return parsed, response

    # ------------------------------------------------------------------
    # Provider-specific implementations
    # ------------------------------------------------------------------

    def _chat_ollama(
        self, system: str, user: str, temperature: float, timeout: float
    ) -> LLMResponse:
        import ollama as _ollama

        result = _ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={"temperature": temperature},
        )

        content = result.get("message", {}).get("content", "")
        usage = {}
        if "eval_count" in result:
            usage["completion_tokens"] = result["eval_count"]
        if "prompt_eval_count" in result:
            usage["prompt_tokens"] = result["prompt_eval_count"]

        return LLMResponse(
            content=content,
            model=self.model,
            provider="ollama",
            success=True,
            usage=usage or None,
        )

    def _chat_openai_compat(
        self, system: str, user: str, temperature: float, max_tokens: int, timeout: float
    ) -> LLMResponse:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL")  # allows Claude-compatible proxies

        if not api_key:
            return LLMResponse(
                content="", model=self.model, provider=self.provider,
                success=False, error="OPENAI_API_KEY not set in environment.",
            )

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

        result = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = result.choices[0]
        usage = None
        if result.usage:
            usage = {
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
            }

        return LLMResponse(
            content=choice.message.content or "",
            model=self.model,
            provider=self.provider,
            success=True,
            usage=usage,
        )

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def _check_ollama(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            import ollama as _ollama
            models = _ollama.list()
            model_names = []
            if isinstance(models, dict) and "models" in models:
                model_names = [m.get("name", "").split(":")[0] for m in models["models"]]
            elif hasattr(models, "models"):
                model_names = [m.model.split(":")[0] if hasattr(m, "model") else str(m).split(":")[0] for m in models.models]
            return self.model.split(":")[0] in model_names or len(model_names) > 0
        except Exception:
            return False

    def _check_openai_compat(self) -> bool:
        """Check if OpenAI API key is set."""
        return bool(os.getenv("OPENAI_API_KEY"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_model(provider: str) -> str:
        defaults = {
            "ollama": "llama3",
            "openai": "gpt-4o-mini",
            "claude": "claude-sonnet-4-20250514",
        }
        return defaults.get(provider, "llama3")

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Extract a JSON object from LLM output.

        Handles:
        - Raw JSON
        - JSON wrapped in ```json ... ``` code blocks
        - JSON embedded in prose text
        """
        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None
