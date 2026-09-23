import asyncio
import os

import pytest

import src.scraper as scraper


@pytest.mark.asyncio
async def test_risk_control_pauses_on_first_failure_without_waiting_for_threshold(
    tmp_path, monkeypatch
):
    guard_path = tmp_path / "guard.json"
    guard = scraper.FailureGuard(
        path=str(guard_path),
        threshold=3,
        pause_seconds=24 * 60 * 60,
        tz_name="Asia/Shanghai",
    )
    monkeypatch.setattr(scraper, "FAILURE_GUARD", guard)

    sent = []

    async def fake_send(product_data, reason):
        sent.append((product_data, reason))
        return {}

    monkeypatch.setattr(scraper, "send_ntfy_notification", fake_send)

    await scraper._notify_task_failure(
        {"task_name": "task-a", "keyword": "kw"},
        "baxia-dialog",
        cookie_path=None,
        immediate_pause=True,
    )

    decision = guard.should_skip_start("task-a")
    assert decision.skip is True
    assert decision.consecutive_failures == 1
    assert sent, "risk-control failure with immediate_pause should notify right away"


@pytest.mark.asyncio
async def test_generic_failure_does_not_pause_before_threshold(tmp_path, monkeypatch):
    guard_path = tmp_path / "guard.json"
    guard = scraper.FailureGuard(
        path=str(guard_path),
        threshold=3,
        pause_seconds=24 * 60 * 60,
        tz_name="Asia/Shanghai",
    )
    monkeypatch.setattr(scraper, "FAILURE_GUARD", guard)

    sent = []

    async def fake_send(product_data, reason):
        sent.append((product_data, reason))
        return {}

    monkeypatch.setattr(scraper, "send_ntfy_notification", fake_send)

    await scraper._notify_task_failure(
        {"task_name": "task-a", "keyword": "kw"},
        "TimeoutError: network hiccup",
        cookie_path=None,
        immediate_pause=False,
    )

    decision = guard.should_skip_start("task-a")
    assert decision.skip is False
    assert not sent, "a single generic failure below threshold should not notify yet"


def test_cookie_change_detection_uses_content_hash_not_mtime(tmp_path):
    from src.failure_guard import _cookie_changed, _get_content_hash

    cookie_path = tmp_path / "state.json"
    cookie_path.write_text('{"a": 1}', encoding="utf-8")
    original_hash = _get_content_hash(str(cookie_path))

    # 内容真正改变，但强制把 mtime 设成和原来完全一样：旧的 mtime 判断法会漏判，
    # 新的内容哈希判断法必须能识别出变化。
    stat = os.stat(cookie_path)
    cookie_path.write_text('{"a": 2}', encoding="utf-8")
    os.utime(cookie_path, (stat.st_atime, stat.st_mtime))

    assert _cookie_changed(str(cookie_path), original_hash) is True

    # 内容完全相同（哪怕文件被原子替换、mtime 变了）不应被视为"已更新"。
    same_content_hash = _get_content_hash(str(cookie_path))
    cookie_path.write_text('{"a": 2}', encoding="utf-8")
    assert _cookie_changed(str(cookie_path), same_content_hash) is False
