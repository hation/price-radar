"""
跨任务通知去重。

通知去重此前只按 (result_filename, link_unique_key) 做，即按"任务 + 链接"去重——
同一件商品被两个不同任务命中时会分别存储、分别通知两次。这里用一张不区分任务的
全局表，在推送前查一次"这件商品最近是否已经被(任意任务)通知过"。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection


def resolve_item_key(item_data: dict) -> Optional[str]:
    item_id = str((item_data or {}).get("商品ID") or "").strip()
    if item_id:
        return f"item:{item_id}"
    link = str((item_data or {}).get("商品链接") or "").strip()
    if link:
        return f"link:{link.split('&', 1)[0]}"
    return None


def should_skip_duplicate_notification(
    item_data: dict,
    *,
    window_hours: int,
    now: Optional[datetime] = None,
) -> bool:
    """若该商品在保留窗口内已经被通知过，返回 True（调用方应跳过本次通知）。

    未跳过时会顺带把这次的通知时间记下来，作为后续判断的依据；
    window_hours <= 0 表示不做跨任务去重。
    """
    if window_hours <= 0:
        return False

    item_key = resolve_item_key(item_data)
    if not item_key:
        return False

    current = now or datetime.now()
    cutoff = (current - timedelta(hours=window_hours)).isoformat()
    current_iso = current.isoformat()

    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        row = conn.execute(
            "SELECT notified_at FROM notified_items WHERE item_key = ?",
            (item_key,),
        ).fetchone()
        if row is not None and str(row["notified_at"]) >= cutoff:
            return True

        conn.execute(
            """
            INSERT INTO notified_items (item_key, notified_at) VALUES (?, ?)
            ON CONFLICT(item_key) DO UPDATE SET notified_at = excluded.notified_at
            """,
            (item_key, current_iso),
        )
        conn.commit()
    return False
