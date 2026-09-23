"""
历史数据保留期清理服务。

price_snapshots / result_items 两张表此前没有任何清理机制，长期运行的实例会
无限增长。这里沿用 task_log_cleanup_service 的"启动时按保留期清理"模式：
keep_days < 1 表示关闭清理、永久保留。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection

logger = get_logger(__name__)


def _cutoff_iso(keep_days: int, now: datetime | None = None) -> str:
    return ((now or datetime.now()) - timedelta(days=keep_days)).isoformat()


def cleanup_price_snapshots(*, keep_days: int, now: datetime | None = None) -> int:
    """删除超过保留期的价格快照。keep_days < 1 表示不清理。"""
    if keep_days < 1:
        return 0

    cutoff = _cutoff_iso(keep_days, now)
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM price_snapshots WHERE snapshot_time < ?",
            (cutoff,),
        )
        conn.commit()

    deleted = int(cursor.rowcount or 0)
    if deleted:
        logger.info(f"价格快照清理完成：已删除 {deleted} 条超过 {keep_days} 天的历史快照。")
    return deleted


def cleanup_result_items(*, keep_days: int, now: datetime | None = None) -> int:
    """删除超过保留期的历史商品结果记录。keep_days < 1 表示不清理。"""
    if keep_days < 1:
        return 0

    cutoff = _cutoff_iso(keep_days, now)
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM result_items WHERE crawl_time < ?",
            (cutoff,),
        )
        conn.commit()

    deleted = int(cursor.rowcount or 0)
    if deleted:
        logger.info(f"历史商品记录清理完成：已删除 {deleted} 条超过 {keep_days} 天的历史记录。")
    return deleted
