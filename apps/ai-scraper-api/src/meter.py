from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import AsyncGenerator, List, Optional, Tuple

import aiosqlite

from .config import settings


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


def _db_path() -> str:
    p = Path(settings.db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


@asynccontextmanager
async def _conn() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(_db_path()) as con:
        con.row_factory = aiosqlite.Row
        await con.execute("PRAGMA journal_mode=WAL")
        yield con


async def init_db() -> None:
    async with _conn() as con:
        await con.executescript("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key           TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                monthly_limit INTEGER NOT NULL DEFAULT 1000,
                queries_used  INTEGER NOT NULL DEFAULT 0,
                reset_month   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key   TEXT NOT NULL,
                ts        TEXT NOT NULL DEFAULT (datetime('now')),
                models    TEXT NOT NULL,
                queries   INTEGER NOT NULL
            );
        """)
        await con.commit()


async def create_key(key: str, name: str, monthly_limit: int) -> None:
    async with _conn() as con:
        await con.execute(
            "INSERT INTO api_keys (key, name, monthly_limit, reset_month) VALUES (?, ?, ?, ?)",
            (key, name, monthly_limit, _current_month()),
        )
        await con.commit()


async def get_key(key: str) -> Optional[aiosqlite.Row]:
    async with _conn() as con:
        async with con.execute("SELECT * FROM api_keys WHERE key = ?", (key,)) as cur:
            return await cur.fetchone()


async def delete_key(key: str) -> bool:
    async with _conn() as con:
        async with con.execute("DELETE FROM api_keys WHERE key = ?", (key,)) as cur:
            await con.commit()
            return cur.rowcount > 0


async def _maybe_reset(con: aiosqlite.Connection, key: str, row: aiosqlite.Row) -> aiosqlite.Row:
    if row["reset_month"] != _current_month():
        await con.execute(
            "UPDATE api_keys SET queries_used = 0, reset_month = ? WHERE key = ?",
            (_current_month(), key),
        )
        async with con.execute("SELECT * FROM api_keys WHERE key = ?", (key,)) as cur:
            return await cur.fetchone()
    return row


async def check_and_increment(key: str, query_count: int, models: List[str]) -> Tuple[bool, int]:
    """Returns (allowed, quota_remaining). BEGIN IMMEDIATE prevents concurrent over-quota races."""
    async with _conn() as con:
        await con.execute("BEGIN IMMEDIATE")
        try:
            async with con.execute("SELECT * FROM api_keys WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
            if row is None:
                await con.execute("ROLLBACK")
                return False, 0
            row = await _maybe_reset(con, key, row)
            used = row["queries_used"]
            limit = row["monthly_limit"]
            if used + query_count > limit:
                await con.execute("ROLLBACK")
                return False, max(0, limit - used)
            await con.execute(
                "UPDATE api_keys SET queries_used = queries_used + ? WHERE key = ?",
                (query_count, key),
            )
            await con.execute(
                "INSERT INTO usage_log (api_key, models, queries) VALUES (?, ?, ?)",
                (key, json.dumps(models), query_count),
            )
            await con.execute("COMMIT")
            return True, limit - used - query_count
        except Exception:
            await con.execute("ROLLBACK")
            raise


async def get_usage(key: str) -> Optional[dict]:
    async with _conn() as con:
        async with con.execute("SELECT * FROM api_keys WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return {
            "key_name": row["name"],
            "queries_used": row["queries_used"],
            "monthly_limit": row["monthly_limit"],
            "quota_remaining": max(0, row["monthly_limit"] - row["queries_used"]),
            "reset_month": row["reset_month"],
        }
