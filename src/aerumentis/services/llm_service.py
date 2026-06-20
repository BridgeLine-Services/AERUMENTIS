"""
Aerumentis — LLM Service
Unified LLM interface supporting OpenAI, OpenRouter, and Azure.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from aerumentis.core.config import LLMProvider, get_settings
from aerumentis.core.logging import get_logger

logger = get_logger("aerumentis.llm")
settings = get_settings()


class LLMError(Exception):
    pass


class LLMService:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._api_key = settings.active_llm_api_key
        self._base_url = settings.active_llm_base_url
        self._model = settings.chat_model
        self._fallback_model = settings.chat_model_fallback
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens
        self._timeout = settings.llm_request_timeout

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
            if settings.llm_provider == LLMProvider.OPENROUTER:
                headers["HTTP-Referer"] = "https://aerumentis.com"
            self._client = httpx.AsyncClient(
                base_url=self._base_url, headers=headers,
                timeout=httpx.Timeout(self._timeout, connect=10.0),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True,
    )
    async def chat(
        self, messages: list[dict[str, str]], model: str | None = None,
        temperature: float | None = None, max_tokens: int | None = None, stream: bool = False,
    ) -> dict | AsyncIterator[dict]:
        target_model = model or self._model
        payload = {
            "model": target_model, "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens or self._max_tokens, "stream": stream,
        }
        try:
            if stream:
                return self._stream_chat(payload, target_model)
            return await self._chat(payload, target_model)
        except Exception as e:
            if target_model != self._fallback_model:
                logger.warning("llm_fallback", primary=target_model, fallback=self._fallback_model, error=str(e))
                payload["model"] = self._fallback_model
                if stream:
                    return self._stream_chat(payload, self._fallback_model)
                return await self._chat(payload, self._fallback_model)
            raise LLMError(f"LLM request failed: {e}") from e

    async def _chat(self, payload: dict, model: str) -> dict:
        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        return {
            "content": choice["message"]["content"], "role": choice["message"]["role"],
            "model": data.get("model", model), "usage": data.get("usage", {}),
            "finish_reason": choice.get("finish_reason"),
        }

    async def _stream_chat(self, payload: dict, model: str) -> AsyncIterator[dict]:
        async with self.client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {})
                if "content" in delta and delta["content"]:
                    yield {"content": delta["content"], "model": chunk.get("model", model)}

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


_llm_service: LLMService | None = None

def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
