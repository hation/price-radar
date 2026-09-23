import asyncio
from datetime import datetime, timedelta

import pytest

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.services.ai_cost_control_service import (
    GlobalAIConcurrencyGate,
    build_ai_cache_key,
    load_cached_ai_result,
    store_ai_result_cache,
)


def _use_temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "results.sqlite3"))
    bootstrap_sqlite_storage()


def _record(price="¥100"):
    return {
        "商品信息": {
            "商品ID": "1",
            "商品链接": "https://x/y",
            "当前售价": price,
            "商品标题": "title",
            "商品标签": ["a"],
        }
    }


def test_cache_key_is_stable_for_identical_input():
    assert build_ai_cache_key(_record(), "prompt-a") == build_ai_cache_key(_record(), "prompt-a")


def test_cache_key_changes_when_price_changes():
    assert build_ai_cache_key(_record("¥100"), "prompt-a") != build_ai_cache_key(_record("¥90"), "prompt-a")


def test_cache_key_changes_when_prompt_changes():
    assert build_ai_cache_key(_record(), "prompt-a") != build_ai_cache_key(_record(), "prompt-b")


def test_store_and_load_cache_round_trip(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    key = build_ai_cache_key(_record(), "prompt-a")
    result = {"is_recommended": True, "reason": "cheap"}

    assert load_cached_ai_result(key, ttl_hours=24) is None

    store_ai_result_cache(key, result)

    assert load_cached_ai_result(key, ttl_hours=24) == result


def test_cache_expires_after_ttl(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    key = build_ai_cache_key(_record(), "prompt-a")
    now = datetime(2026, 3, 1, 12, 0, 0)

    store_ai_result_cache(key, {"is_recommended": True}, now=now)

    assert load_cached_ai_result(key, ttl_hours=1, now=now + timedelta(minutes=30)) is not None
    assert load_cached_ai_result(key, ttl_hours=1, now=now + timedelta(hours=2)) is None


def test_cache_disabled_when_ttl_hours_zero(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    key = build_ai_cache_key(_record(), "prompt-a")
    store_ai_result_cache(key, {"is_recommended": True})

    assert load_cached_ai_result(key, ttl_hours=0) is None


@pytest.mark.asyncio
async def test_concurrency_gate_disabled_when_limit_zero_never_touches_db(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    gate = GlobalAIConcurrencyGate(limit=0)

    async with gate:
        pass

    assert gate._call_id is None


@pytest.mark.asyncio
async def test_concurrency_gate_serializes_when_limit_is_one(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    gate = GlobalAIConcurrencyGate(limit=1, poll_interval_seconds=0.01)
    order: list[str] = []
    first_acquired = asyncio.Event()

    async def first():
        async with gate:
            order.append("first-start")
            first_acquired.set()
            await asyncio.sleep(0.1)
            order.append("first-end")

    async def second():
        await first_acquired.wait()
        async with gate:
            order.append("second-start")

    await asyncio.gather(first(), second())

    assert order == ["first-start", "first-end", "second-start"]


@pytest.mark.asyncio
async def test_concurrency_gate_ignores_stale_inflight_rows(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    gate = GlobalAIConcurrencyGate(limit=1, stale_after_seconds=1, poll_interval_seconds=0.01)

    # 模拟一个崩溃的进程留下的过期占位记录
    from src.infrastructure.persistence.sqlite_connection import sqlite_connection

    with sqlite_connection() as conn:
        conn.execute(
            "INSERT INTO ai_inflight_calls (call_id, started_at) VALUES (?, ?)",
            ("leaked", (datetime.now() - timedelta(seconds=5)).isoformat()),
        )
        conn.commit()

    async with gate:
        pass

    assert gate._call_id is None
