import asyncio
from unittest.mock import AsyncMock, patch

import src.ai_handler as ai_handler
from src.scraper import _get_title_screening_enabled


def test_get_title_screening_enabled_task_overrides_env(monkeypatch):
    monkeypatch.setenv("AI_TITLE_SCREENING_ENABLED", "true")

    # 任务级 true 优先
    assert _get_title_screening_enabled({"ai_title_screening": True}) is True
    # 任务级 false 覆盖环境变量（显式关闭）
    assert _get_title_screening_enabled({"ai_title_screening": False}) is False
    # 任务级缺失时回退到环境变量
    assert _get_title_screening_enabled({}) is True
    monkeypatch.setenv("AI_TITLE_SCREENING_ENABLED", "false")
    assert _get_title_screening_enabled({}) is False
    # 字符串形式的任务级开关
    assert _get_title_screening_enabled({"ai_title_screening": "yes"}) is True


def test_get_title_screening_enabled_string_env(monkeypatch):
    # 未设置任务级开关与环境变量时，默认开启
    monkeypatch.delenv("AI_TITLE_SCREENING_ENABLED", raising=False)
    assert _get_title_screening_enabled({}) is True
    # 环境变量显式关闭时，全局回退为关闭
    monkeypatch.setenv("AI_TITLE_SCREENING_ENABLED", "false")
    assert _get_title_screening_enabled({}) is False


async def _run_screen(title, keyword, requirements, response_content):
    fake_response = object()
    with patch.object(ai_handler, "client", object()), patch.object(
        ai_handler,
        "create_ai_response_async",
        AsyncMock(return_value=fake_response),
    ), patch.object(
        ai_handler, "extract_ai_response_content", return_value=response_content
    ):
        return await ai_handler.screen_product_title(title, keyword, requirements)


def test_screen_product_title_not_matching():
    async def run():
        match, reason = await _run_screen(
            "iPhone 15 99新",
            "a7m4",
            "想要一台索尼微单相机",
            '{"match": false, "reason": "品类完全无关"}',
        )
        assert match is False
        assert "无关" in reason

    asyncio.run(run())


def test_screen_product_title_matching():
    async def run():
        match, _ = await _run_screen(
            "索尼 A7M4 微单相机",
            "a7m4",
            "想要一台索尼微单相机",
            '{"match": true, "reason": "符合要求"}',
        )
        assert match is True

    asyncio.run(run())


def test_screen_product_title_falls_back_to_keep_on_error():
    async def run():
        with patch.object(ai_handler, "client", object()), patch.object(
            ai_handler,
            "create_ai_response_async",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            match, reason = await ai_handler.screen_product_title(
                "iPhone 15", "a7m4", "索尼微单"
            )
        # 出错时按「不跳过」处理，避免漏掉潜在目标
        assert match is True
        assert reason == ""

    asyncio.run(run())


def test_screen_product_title_no_client_no_requirements():
    async def run():
        with patch.object(ai_handler, "client", None):
            assert await ai_handler.screen_product_title("x", "k", "req") == (True, "")
        assert await ai_handler.screen_product_title("", "k", "req") == (True, "")
        assert await ai_handler.screen_product_title("x", "k", "") == (True, "")

    asyncio.run(run())
