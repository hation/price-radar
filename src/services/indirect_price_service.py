"""间接价服务:经慢慢买查任意电商商品的历史价/当前价 + watchlist 盯价。

解决两个问题:
1. 拼多多不直抓(anti-content 无解,M6 定案)——丢 PDD 商品链接查慢慢买间接价
2. 京东/淘宝等平台的**商品级盯价**不用等采集器:给链接+目标价,跌破飞书推送

watchlist 存 price-radar 根 watchlist.json(state 类数据,不入 git)。
推送复用 .env 的 WEBHOOK_URL(通用 Webhook 渠道,飞书即配)。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from src.services.manmanbuy_client import fetch_history_trend, parse_trend

WATCHLIST_PATH = "watchlist.json"


def lookup_item_history(item_url: str) -> Optional[dict]:
    """查单商品历史价,返回标准化结构;失败返回 None。"""
    payload = fetch_history_trend(item_url)
    if payload is None or payload.get("code") != 0:
        return None
    trend = parse_trend(payload.get("data") or {})
    if not trend:
        return None
    lowest = trend.get("lowest")
    current = trend.get("current_price")
    trend["current_vs_lowest_pct"] = (
        round((current - lowest) / lowest * 100, 1) if (current and lowest) else None
    )
    return trend


# ---------------- watchlist ----------------

def _load_watchlist() -> list[dict]:
    if os.path.exists(WATCHLIST_PATH):
        try:
            with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_watchlist(items: list[dict]) -> None:
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def watch_add(item_url: str, target_price: float, note: str = "") -> dict:
    items = _load_watchlist()
    entry = {
        "url": item_url,
        "target_price": target_price,
        "note": note,
        "added_at": datetime.now().isoformat(),
        "last_price": None,
        "last_checked": None,
    }
    items = [x for x in items if x["url"] != item_url] + [entry]
    _save_watchlist(items)
    return entry


def watch_remove(item_url: str) -> int:
    items = _load_watchlist()
    remain = [x for x in items if x["url"] != item_url]
    _save_watchlist(remain)
    return len(items) - len(remain)


def watch_list() -> list[dict]:
    return _load_watchlist()


def _notify_feishu(title: str, content: str) -> bool:
    """降价推送:.env 的 WEBHOOK_URL(与底座通知渠道同一处配置)。"""
    url = os.getenv("WEBHOOK_URL", "").strip()
    if not url:
        print("[watch] WEBHOOK_URL 未配置,推送跳过(仅控制台输出)。")
        return False
    body = json.dumps(
        {"msg_type": "text", "content": {"text": f"{title}\n{content}"}},
        ensure_ascii=False,
    )
    try:
        import requests

        resp = requests.post(
            url, data=body.encode("utf-8"),
            headers={"Content-Type": "application/json"}, timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[watch] 推送失败: {e.__class__.__name__} {e}")
        return False


def watch_check(only_url: Optional[str] = None) -> list[dict]:
    """逐条查现价,跌破目标价推送飞书。返回本轮检查结果。"""
    items = _load_watchlist()
    results = []
    for entry in items:
        if only_url and entry["url"] != only_url:
            continue
        trend = lookup_item_history(entry["url"])
        if not trend:
            results.append({"url": entry["url"], "ok": False, "reason": "查询失败"})
            continue
        current = trend.get("current_price")
        hit = current is not None and current <= entry["target_price"]
        entry["last_price"] = current
        entry["last_checked"] = datetime.now().isoformat()
        results.append(
            {
                "url": entry["url"],
                "ok": True,
                "title": trend.get("title", "")[:40],
                "current": current,
                "lowest": trend.get("lowest"),
                "target": entry["target_price"],
                "hit": hit,
            }
        )
        if hit:
            _notify_feishu(
                f"🎯 盯价命中: {trend.get('title', '')[:40]}",
                f"现价 ¥{current} ≤ 目标 ¥{entry['target_price']}"
                f"(历史最低 ¥{trend.get('lowest')})\n{entry['url']}",
            )
    _save_watchlist(items)
    return results
