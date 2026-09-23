"""
AI 调用成本控制：跨任务结果缓存 + 可选的跨进程全局并发上限。

每个爬虫任务都是独立子进程，AI_ANALYSIS_CONCURRENCY 只能限制单个任务内部的并发，
多个任务同时运行时会各自独立地把并发拉满，叠加放大 API 花费/限流压力。这里补两样：
1. 按"商品内容 + 该任务的 prompt"算一个哈希，命中缓存直接复用结果，避免同一件商品
   被不同任务重复分析（缓存键包含 prompt，不同任务的判断标准不同不会互相污染）。
2. 一个可选的、基于 SQLite 的跨进程信号量，限制同一时刻全局有多少个 AI 请求在跑。
   默认关闭（GLOBAL_AI_CONCURRENCY_LIMIT=0），需要用户自己按 API 配额设置。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection

DEFAULT_STALE_INFLIGHT_SECONDS = 600
DEFAULT_POLL_INTERVAL_SECONDS = 1.0


def build_ai_cache_key(record: dict, prompt_text: str) -> str:
    item = (record or {}).get("商品信息", {}) or {}
    payload = {
        "item_id": item.get("商品ID"),
        "link": item.get("商品链接"),
        "price": item.get("当前售价"),
        "title": item.get("商品标题"),
        "tags": item.get("商品标签"),
        "prompt": prompt_text or "",
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_cached_ai_result(cache_key: str, *, ttl_hours: int, now: Optional[datetime] = None) -> Optional[dict]:
    if ttl_hours <= 0:
        return None

    current = now or datetime.now()
    cutoff = (current - timedelta(hours=ttl_hours)).isoformat()

    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        row = conn.execute(
            "SELECT result_json, created_at FROM ai_analysis_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if row is None or str(row["created_at"]) < cutoff:
        return None
    try:
        return json.loads(row["result_json"])
    except json.JSONDecodeError:
        return None


def store_ai_result_cache(cache_key: str, result: dict, *, now: Optional[datetime] = None) -> None:
    current = now or datetime.now()
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        conn.execute(
            """
            INSERT INTO ai_analysis_cache (cache_key, result_json, created_at) VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                result_json = excluded.result_json,
                created_at = excluded.created_at
            """,
            (cache_key, json.dumps(result, ensure_ascii=False), current.isoformat()),
        )
        conn.commit()


class GlobalAIConcurrencyGate:
    """基于 SQLite 的跨进程信号量。limit <= 0 时完全不生效（不加锁、不轮询）。

    进程崩溃导致的"未释放"记录不会永久占位：任何一次 acquire 都会先清理超过
    stale_after_seconds 还没释放的陈旧记录，超时时间需要大于单次 AI 调用可能
    耗费的最长时间（含内部重试）。
    """

    def __init__(
        self,
        *,
        limit: int,
        stale_after_seconds: int = DEFAULT_STALE_INFLIGHT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._limit = max(0, limit)
        self._stale_after_seconds = max(1, stale_after_seconds)
        self._poll_interval_seconds = max(0.05, poll_interval_seconds)
        self._call_id: Optional[str] = None

    async def __aenter__(self) -> "GlobalAIConcurrencyGate":
        if self._limit <= 0:
            return self
        call_id = uuid.uuid4().hex
        while not await asyncio.to_thread(self._try_acquire_sync, call_id):
            await asyncio.sleep(self._poll_interval_seconds)
        self._call_id = call_id
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._call_id is not None:
            await asyncio.to_thread(self._release_sync, self._call_id)
            self._call_id = None

    def _try_acquire_sync(self, call_id: str) -> bool:
        bootstrap_sqlite_storage()
        now = datetime.now()
        stale_cutoff = (now - timedelta(seconds=self._stale_after_seconds)).isoformat()
        with sqlite_connection() as conn:
            conn.execute("DELETE FROM ai_inflight_calls WHERE started_at < ?", (stale_cutoff,))
            active = conn.execute("SELECT COUNT(*) AS c FROM ai_inflight_calls").fetchone()["c"]
            if active >= self._limit:
                conn.commit()
                return False
            conn.execute(
                "INSERT OR IGNORE INTO ai_inflight_calls (call_id, started_at) VALUES (?, ?)",
                (call_id, now.isoformat()),
            )
            conn.commit()
        return True

    def _release_sync(self, call_id: str) -> None:
        bootstrap_sqlite_storage()
        with sqlite_connection() as conn:
            conn.execute("DELETE FROM ai_inflight_calls WHERE call_id = ?", (call_id,))
            conn.commit()
