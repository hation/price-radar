from datetime import datetime, timedelta

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.services.notification_dedup_service import (
    resolve_item_key,
    should_skip_duplicate_notification,
)


def _use_temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "results.sqlite3"))
    bootstrap_sqlite_storage()


def test_resolve_item_key_prefers_item_id_over_link():
    assert resolve_item_key({"商品ID": "123", "商品链接": "https://x/y?id=123"}) == "item:123"
    assert resolve_item_key({"商品链接": "https://x/y?a=1&b=2"}) == "link:https://x/y?a=1"
    assert resolve_item_key({}) is None


def test_first_notification_is_not_skipped_and_gets_recorded(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    item = {"商品ID": "1"}

    assert should_skip_duplicate_notification(item, window_hours=24) is False


def test_duplicate_within_window_is_skipped(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    item = {"商品ID": "1"}
    now = datetime(2026, 3, 1, 12, 0, 0)

    assert should_skip_duplicate_notification(item, window_hours=24, now=now) is False
    assert (
        should_skip_duplicate_notification(
            item, window_hours=24, now=now + timedelta(hours=1)
        )
        is True
    )


def test_notification_after_window_expires_is_not_skipped(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    item = {"商品ID": "1"}
    now = datetime(2026, 3, 1, 12, 0, 0)

    assert should_skip_duplicate_notification(item, window_hours=1, now=now) is False
    assert (
        should_skip_duplicate_notification(
            item, window_hours=1, now=now + timedelta(hours=2)
        )
        is False
    )


def test_window_hours_zero_disables_dedup(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    item = {"商品ID": "1"}

    assert should_skip_duplicate_notification(item, window_hours=0) is False
    assert should_skip_duplicate_notification(item, window_hours=0) is False


def test_item_without_id_or_link_is_never_deduped(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    assert should_skip_duplicate_notification({}, window_hours=24) is False
    assert should_skip_duplicate_notification({}, window_hours=24) is False
