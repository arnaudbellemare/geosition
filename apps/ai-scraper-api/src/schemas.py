from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ModelName = Literal["chatgpt", "perplexity", "gemini", "grok"]

AVAILABLE_MODELS: List[ModelName] = ["chatgpt", "perplexity", "gemini", "grok"]


class ScrapeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    models: List[ModelName] = Field(default=AVAILABLE_MODELS)
    brand: Optional[str] = Field(None, description="Brand name to track in responses")
    aliases: List[str] = Field(default_factory=list, description="Additional brand aliases")
    system_prompt: Optional[str] = Field(None, max_length=500)


class ModelResult(BaseModel):
    model: ModelName
    status: Literal["success", "error"]
    response: Optional[str] = None
    error: Optional[str] = None
    latency_ms: int = 0
    brand_mentioned: Optional[bool] = None
    rank: Optional[int] = Field(None, description="Position in a numbered list, if detected")
    mention_count: Optional[int] = None
    sentiment: Optional[Literal["positive", "negative", "neutral"]] = None
    citations: List[str] = Field(default_factory=list)


class ScrapeResponse(BaseModel):
    query_id: str
    prompt: str
    brand: Optional[str]
    results: List[ModelResult]
    queries_used: int
    quota_remaining: int


class UsageResponse(BaseModel):
    key_name: str
    queries_used: int
    monthly_limit: int
    quota_remaining: int
    reset_month: str


class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    monthly_limit: int = Field(default=1000, ge=1, le=1_000_000)


class CreateKeyResponse(BaseModel):
    api_key: str
    name: str
    monthly_limit: int
