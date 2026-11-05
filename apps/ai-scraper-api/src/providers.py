from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

from .config import settings
from .schemas import ModelName


@dataclass
class ProviderConfig:
    base_url: str
    model: str
    api_key: str


@dataclass
class ProviderResult:
    model: ModelName
    response: Optional[str]
    latency_ms: int
    error: Optional[str] = None


def _build_configs() -> Dict[str, ProviderConfig]:
    return {
        "chatgpt": ProviderConfig(
            base_url="https://api.openai.com/v1",
            model=settings.openai_model,
            api_key=settings.openai_api_key,
        ),
        "perplexity": ProviderConfig(
            base_url="https://api.perplexity.ai",
            model=settings.perplexity_model,
            api_key=settings.perplexity_api_key,
        ),
        "gemini": ProviderConfig(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            model=settings.gemini_model,
            api_key=settings.gemini_api_key,
        ),
        "grok": ProviderConfig(
            base_url="https://api.x.ai/v1",
            model=settings.grok_model,
            api_key=settings.grok_api_key,
        ),
    }


# Module-level constant — built once at import time
PROVIDER_CONFIGS: Dict[str, ProviderConfig] = _build_configs()

# Lifespan-managed client — set by main.py on startup
_http_client: Optional[httpx.AsyncClient] = None


def set_http_client(client: httpx.AsyncClient) -> None:
    global _http_client
    _http_client = client


def get_http_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client not initialised — call set_http_client() in app lifespan")
    return _http_client


async def _query_provider(
    client: httpx.AsyncClient,
    name: ModelName,
    cfg: ProviderConfig,
    prompt: str,
    system_prompt: Optional[str],
) -> ProviderResult:
    if not cfg.api_key:
        return ProviderResult(model=name, response=None, latency_ms=0, error="API key not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    start = time.monotonic()
    try:
        resp = await client.post(
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={"model": cfg.model, "messages": messages},
            timeout=30.0,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return ProviderResult(model=name, response=text, latency_ms=latency_ms)
    except httpx.HTTPStatusError as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return ProviderResult(model=name, response=None, latency_ms=latency_ms, error=f"HTTP {e.response.status_code}")
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return ProviderResult(model=name, response=None, latency_ms=latency_ms, error=str(e))


async def fan_out(
    models: List[ModelName],
    prompt: str,
    system_prompt: Optional[str] = None,
) -> List[ProviderResult]:
    client = get_http_client()
    tasks = [
        _query_provider(client, name, PROVIDER_CONFIGS[name], prompt, system_prompt)
        for name in models
    ]
    return await asyncio.gather(*tasks)
