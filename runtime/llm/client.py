from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LLMClientError(RuntimeError):
    """Base error for LLM client failures."""


class LLMTimeoutError(LLMClientError):
    """Raised when the LLM request times out."""


class LLMResponseError(LLMClientError):
    """Raised when the LLM response cannot be parsed or is invalid."""


@dataclass(frozen=True)
class LLMClient:
    """Minimal OpenAI-compatible chat completions client.

    Configured via environment variables:

    - ``MODEL_BASE_URL`` — API base URL (shared by planner and coder)
    - ``MODEL_API_KEY`` — API key (shared)
    - ``PLANNER_MODEL`` — model for task planning (lightweight/fast)
    - ``CODING_MODEL`` — model for code generation (code-optimized)
    """

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls, *, model_env_key: str = "CODING_MODEL") -> LLMClient:
        """Create client from environment variables.

        Args:
            model_env_key: Environment variable name for the model.
                           "PLANNER_MODEL" for planning, "CODING_MODEL" for code generation.

        ⭐ Loads .env from the project root (agent_hub/) using absolute path,
        ensuring it works regardless of CWD.
        """
        # 自动加载 .env — 使用项目根目录的绝对路径确保可靠性
        try:
            from dotenv import load_dotenv
            _project_root = Path(__file__).resolve().parents[3]  # runtime/llm/client.py -> agent_hub/
            _env_path = _project_root / ".env"
            if _env_path.exists():
                load_dotenv(_env_path, override=False)
        except (ImportError, Exception):
            pass

        base_url = os.environ.get("MODEL_BASE_URL", "")
        api_key = os.environ.get("MODEL_API_KEY", "")
        model = os.environ.get(model_env_key, "")
        if not base_url or not api_key or not model:
            raise LLMClientError(
                f"MODEL_BASE_URL, MODEL_API_KEY, and {model_env_key} "
                "must all be set in the environment"
            )
        return cls(base_url=base_url, api_key=api_key, model=model)

    def _endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request and return the parsed JSON body.

        Raises :class:`LLMTimeoutError` on timeout and :class:`LLMResponseError`
        on HTTP or parsing failures.
        """
        import time
        start_time = time.time()
        
        logger.info(
            f"[LLM Call] Starting model call - Model: {self.model}, "
            f"Temperature: {temperature}, Max tokens: {max_tokens}, "
            f"Message count: {len(messages)}"
        )
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            body["response_format"] = response_format
        
        # 禁用深度思考（如果模型支持）
        # 对于 v4-Lash 这类模型，我们明确禁用 thinking
        body["thinking"] = {"type": "disabled"}
        logger.info(f"[LLM Call] Request body (thinking disabled): {json.dumps(body, ensure_ascii=False)[:500]}")

        try:
            response = httpx.post(
                self._endpoint(),
                json=body,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            logger.error(f"[LLM Call] Timeout after {self.timeout_seconds}s")
            raise LLMTimeoutError(f"LLM request timed out after {self.timeout_seconds}s") from exc
        except httpx.RequestError as exc:
            logger.error(f"[LLM Call] Request failed: {exc}")
            raise LLMResponseError(f"LLM request failed: {exc}") from exc

        if response.status_code >= 400:
            snippet = response.text[:500]
            logger.error(f"[LLM Call] API returned error {response.status_code}: {snippet}")
            raise LLMResponseError(
                f"LLM API returned {response.status_code}: {snippet}"
            )

        try:
            response_json = response.json()
            elapsed_time = time.time() - start_time
            
            # 提取响应信息
            usage = response_json.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            
            logger.info(
                f"[LLM Call] Completed - Elapsed: {elapsed_time:.2f}s, "
                f"Model: {self.model}, "
                f"Tokens - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}"
            )
            
            return response_json
        except json.JSONDecodeError as exc:
            snippet = response.text[:300]
            logger.error(f"[LLM Call] Failed to parse JSON response: {snippet}")
            raise LLMResponseError(f"Failed to parse LLM response as JSON: {snippet}") from exc

    def extract_content(self, response_body: dict[str, Any]) -> str:
        """Extract the assistant message content from a chat completion response."""
        try:
            return response_body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                f"Unexpected LLM response shape: {json.dumps(response_body, ensure_ascii=False)[:500]}"
            ) from exc
