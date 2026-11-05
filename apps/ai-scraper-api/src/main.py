from __future__ import annotations

import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from . import brand, meter
from .auth import require_admin, require_api_key
from .config import settings
from .providers import fan_out, set_http_client
from .schemas import (
    AVAILABLE_MODELS,
    CreateKeyRequest,
    CreateKeyResponse,
    ModelResult,
    ScrapeRequest,
    ScrapeResponse,
    UsageResponse,
)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    await meter.init_db()
    async with httpx.AsyncClient() as client:
        set_http_client(client)
        yield


app = FastAPI(
    title="AI Scraper API",
    description="Query ChatGPT, Perplexity, Gemini, and Grok in one call. Get structured brand intelligence.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "models": AVAILABLE_MODELS}


# ---------------------------------------------------------------------------
# Core scrape endpoint
# ---------------------------------------------------------------------------

@app.post("/v1/scrape", response_model=ScrapeResponse, tags=["scrape"])
async def scrape(
    req: ScrapeRequest,
    api_key: str = Depends(require_api_key),
) -> ScrapeResponse:
    query_count = len(req.models)

    allowed, quota_remaining = await meter.check_and_increment(api_key, query_count, list(req.models))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly quota exceeded. Remaining: {quota_remaining}",
        )

    raw_results = await fan_out(req.models, req.prompt, req.system_prompt)

    results: List[ModelResult] = []
    for r in raw_results:
        if r.error or r.response is None:
            log.warning("provider_error model=%s error=%s", r.model, r.error)
            results.append(ModelResult(model=r.model, status="error", error=r.error, latency_ms=r.latency_ms))
            continue

        if req.brand:
            intel = brand.analyze(r.response, req.brand, req.aliases)
            results.append(ModelResult(
                model=r.model,
                status="success",
                response=r.response,
                latency_ms=r.latency_ms,
                brand_mentioned=intel.mentioned,
                rank=intel.rank,
                mention_count=intel.mention_count,
                sentiment=intel.sentiment,
                citations=intel.citations,
            ))
        else:
            results.append(ModelResult(
                model=r.model,
                status="success",
                response=r.response,
                latency_ms=r.latency_ms,
            ))

    return ScrapeResponse(
        query_id=str(uuid.uuid4()),
        prompt=req.prompt,
        brand=req.brand,
        results=results,
        queries_used=query_count,
        quota_remaining=quota_remaining,
    )


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

@app.get("/v1/usage", response_model=UsageResponse, tags=["account"])
async def get_usage(api_key: str = Depends(require_api_key)) -> UsageResponse:
    usage = await meter.get_usage(api_key)
    if usage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return UsageResponse(**usage)


# ---------------------------------------------------------------------------
# Key management (admin)
# ---------------------------------------------------------------------------

@app.post("/v1/keys", response_model=CreateKeyResponse, tags=["admin"], dependencies=[Depends(require_admin)])
async def create_key(req: CreateKeyRequest) -> CreateKeyResponse:
    key = "sk-" + secrets.token_urlsafe(32)
    await meter.create_key(key, req.name, req.monthly_limit)
    return CreateKeyResponse(api_key=key, name=req.name, monthly_limit=req.monthly_limit)


@app.delete("/v1/keys", tags=["admin"], dependencies=[Depends(require_admin)])
async def delete_key(key: str = Body(..., embed=True)) -> dict:
    """Delete a key by value. Key is passed in the request body, not the URL."""
    deleted = await meter.delete_key(key)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return {"deleted": True}
