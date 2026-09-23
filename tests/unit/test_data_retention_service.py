from datetime import datetime, timedelta

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.services.data_retention_service import (
    cleanup_price_snapshots,
    cleanup_result_items,
)


def _use_temp_db(tmp_path, monkeypatch):
    # 必须单独用 APP_DATABASE_FILE 隔离，否则会污染仓库根目录下的真实 data/app.sqlite3。
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "results.sqlite3"))
    bootstrap_sqlite_storage()


def _insert_price_snapshot(conn, *, item_id: str, snapshot_time: str):
    conn.execute(
        """
        INSERT INTO price_snapshots (
            keyword_slug, keyword, task_name, snapshot_time, snapshot_day,
            run_id, item_id, title, price, price_display, tags_json, region,
            seller, publish_time, link
        ) VALUES ('sony', 'sony', 'task', ?, ?, 'run-1', ?, 'title', 100, '¥100', '[]', '', '', '', '')
        """,
        (snapshot_time, snapshot_time[:10], item_id),
    )


def _insert_result_item(conn, *, item_id: str, crawl_time: str):
    conn.execute(
        """
        INSERT INTO result_items (
            result_filename, keyword, task_name, crawl_time, publish_time, price,
            price_display, item_id, title, link, link_unique_key, seller_nickname,
            is_recommended, analysis_source, keyword_hit_count, raw_json
        ) VALUES ('sony.jsonl', 'sony', 'task', ?, '', 100, '¥100', ?, 'title', ?, ?, '', 0, 'ai', 0, '{}')
        """,
        (crawl_time, item_id, f"https://item/{item_id}", item_id),
    )


def test_cleanup_price_snapshots_removes_only_expired_rows(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    now = datetime(2026, 3, 1)
    old_time = (now - timedelta(days=40)).isoformat()
    recent_time = (now - timedelta(days=5)).isoformat()

    with sqlite_connection() as conn:
        _insert_price_snapshot(conn, item_id="old", snapshot_time=old_time)
        _insert_price_snapshot(conn, item_id="recent", snapshot_time=recent_time)
        conn.commit()

    deleted = cleanup_price_snapshots(keep_days=30, now=now)
    assert deleted == 1

    with sqlite_connection() as conn:
        remaining = {row["item_id"] for row in conn.execute("SELECT item_id FROM price_snapshots").fetchall()}
    assert remaining == {"recent"}


def test_cleanup_price_snapshots_disabled_when_keep_days_below_one(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    now = datetime(2026, 3, 1)
    old_time = (now - timedelta(days=400)).isoformat()

    with sqlite_connection() as conn:
        _insert_price_snapshot(conn, item_id="old", snapshot_time=old_time)
        conn.commit()

    assert cleanup_price_snapshots(keep_days=0, now=now) == 0

    with sqlite_connection() as conn:
        remaining = conn.execute("SELECT COUNT(*) AS c FROM price_snapshots").fetchone()["c"]
    assert remaining == 1


def test_cleanup_result_items_removes_only_expired_rows(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    now = datetime(2026, 3, 1)
    old_time = (now - timedelta(days=120)).isoformat()
    recent_time = (now - timedelta(days=10)).isoformat()

    with sqlite_connection() as conn:
        _insert_result_item(conn, item_id="old", crawl_time=old_time)
        _insert_result_item(conn, item_id="recent", crawl_time=recent_time)
        conn.commit()

    deleted = cleanup_result_items(keep_days=90, now=now)
    assert deleted == 1

    with sqlite_connection() as conn:
        remaining = {row["item_id"] for row in conn.execute("SELECT item_id FROM result_items").fetchall()}
    assert remaining == {"recent"}
