"""Async httpx wrapper around the Ollama HTTP API with streaming metric capture.

Captures the three benchmark metrics the prototype cares about:

* ``time_to_first_token_ms`` — wall time from request send to first streamed token.
* ``tokens_per_second`` — from Ollama's ``eval_count`` / ``eval_duration`` in the
  final ``done`` message (authoritative; falls back to wall-clock if absent).
* ``total_latency_ms`` — wall time for the whole request.

No model name is hardcoded — the caller passes ``model``. Any Ollama-compatible
model works (gemma3:2b, phi4-mini:3.8b, mistral, qwen2.5:7b, ...).
"""

from __future__ import annotations

import json
import time

import httpx

from backend.config import Settings, get_settings
from backend.models import ChatMetrics


class OllamaClient:
    def __init__(self, settings: Settings | None = None, timeout: float = 300.0):
        self.settings = settings or get_settings()
        self.base_url = self.settings.ollama_base_url.rstrip("/")
        self.timeout = timeout

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        num_ctx: int = 4096,
        temperature: float = 0.1,
        num_predict: int = 200,
    ) -> tuple[str, ChatMetrics]:
        """Stream a chat completion and return (text, metrics)."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.settings.ollama_keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "num_ctx": num_ctx,
            },
        }

        text_parts: list[str] = []
        ttft_ms = 0.0
        eval_count = 0
        eval_duration_ns = 0
        start = time.perf_counter()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        if not text_parts:
                            ttft_ms = (time.perf_counter() - start) * 1000
                        text_parts.append(piece)
                    if chunk.get("done"):
                        eval_count = chunk.get("eval_count", 0) or 0
                        eval_duration_ns = chunk.get("eval_duration", 0) or 0

        total_latency_ms = (time.perf_counter() - start) * 1000
        if eval_count and eval_duration_ns:
            tokens_per_second = eval_count / (eval_duration_ns / 1e9)
        elif total_latency_ms > 0:
            # Fallback: rough wall-clock estimate (~4 chars/token).
            est_tokens = sum(len(p) for p in text_parts) / 4
            tokens_per_second = est_tokens / (total_latency_ms / 1000)
        else:
            tokens_per_second = 0.0

        metrics = ChatMetrics(
            time_to_first_token_ms=ttft_ms,
            tokens_per_second=tokens_per_second,
            total_latency_ms=total_latency_ms,
            eval_count=eval_count,
        )
        return "".join(text_parts), metrics

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        """Return an embedding vector for ``text`` via Ollama."""
        model = model or self.settings.ollama_embed_model
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json().get("embedding", [])

    async def list_models(self) -> list[str]:
        """Return the names of models currently pulled in Ollama."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]

    async def version(self) -> str:
        """Return the running Ollama version string (best effort)."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/api/version")
                resp.raise_for_status()
                return resp.json().get("version", "unknown")
        except Exception:
            return "unknown"

    async def health(self, model: str | None = None) -> bool:
        """True if Ollama is reachable and (if given) ``model`` is pulled."""
        try:
            available = await self.list_models()
        except Exception:
            return False
        if model is None:
            return True
        # Match with or without an explicit ":latest" tag.
        names = {n.split(":")[0] for n in available} | set(available)
        return model in available or model.split(":")[0] in names
