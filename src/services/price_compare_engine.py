"""跨平台比价引擎。

输入关键词,从 price_snapshots 拉各平台最新一轮快照,输出同款候选对比+差价率。
同款认定第一版 = 标题 token 归一化后 Jaccard 相似度(GLM 辅助判定留接口,后置)。

数据流:采集适配器(淘宝/京东/1688)写本库 price_snapshots(platform 维度);
闲鱼数据 = 只读对接旧监控器(xianyu-monitor)的 app.sqlite3——它已稳定生产
(AI 打分+推送),不重造采集(架构决策 2026-09-19),配件/型号过滤对齐本引擎。
"""
from __future__ import annotations

import os
import re
import sqlite3 as _sqlite3
from dataclasses import dataclass, field
from typing import Optional

from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.services.price_history_service import normalize_keyword_slug

# 旧监控器(闲鱼数据源)只读库
# 闲鱼外部行情库(可选):指向一个现成的闲鱼监控器 SQLite,比价即多一路二手行情。
# 未配置/文件不存在时自动跳过闲鱼行情,不影响其他平台。
XIANYU_EXTERNAL_DB = os.getenv("XIANYU_EXTERNAL_DB", "")

# 比价时忽略的噪声词(成色/营销话术,防同款误伤)
_STOP_TOKENS = {
    "二手", "全新", "未激活", "激活", "正品", "国行", "港版", "美版", "日版",
    "包邮", "顺丰", "自用", "闲置", "转让", "出售", "支持", "验货", "宝",
    "官方", "旗舰店", "正品保障", "现货", "当天发", "送礼", "盒装", "裸机",
}


@dataclass
class PlatformSummary:
    """单平台在关键词下的最新一轮行情摘要。"""

    platform: str
    item_count: int = 0
    lowest_price: Optional[float] = None
    lowest_title: str = ""
    lowest_link: str = ""
    median_price: Optional[float] = None
    latest_run: str = ""
    items: list = field(default_factory=list)


# 配件特征词:命中即视为非整机(比价只比主机)
_ACCESSORY_WORDS = (
    "适用于", "适配", "手机壳", "保护壳", "保护套", "贴膜", "钢化膜", "挂绳",
    "支架", "充电器", "数据线", "壳膜", "镜头膜", "皮套", "翻页笔", "外屏",
    "总成", "维修", "回收", "模型",
)


def _is_accessory(title: str) -> bool:
    text = str(title or "")
    return any(w in text for w in _ACCESSORY_WORDS)


def _title_tokens(title: str) -> set[str]:
    """标题分词:小写化+按非字母数字汉字边界切+去噪声词+去单字符。"""
    text = re.sub(r"\s+", " ", str(title or "").lower())
    tokens = set(t for t in re.split(r"[^0-9a-z一-鿿]+", text) if len(t) >= 2)
    # 汉字整体也算一个 token(型号如 fold5 靠字母数字;纯中文品名靠整体)
    core = re.sub(r"[^0-9a-z一-鿿]", "", text)
    if len(core) >= 2:
        tokens.add(core)
    return tokens - _STOP_TOKENS


def _similarity(a: str, b: str) -> float:
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _load_latest_run_items_xianyu_external(keyword: str) -> list[dict]:
    """闲鱼数据:只读外部监控器库(可选),按型号 token 模糊匹配最近一轮 run。"""
    tokens = sorted(_keyword_model_tokens(keyword))
    if not tokens or not XIANYU_EXTERNAL_DB or not os.path.exists(XIANYU_EXTERNAL_DB):
        if tokens and XIANYU_EXTERNAL_DB:
            print(f"[compare] 闲鱼外部库不存在({XIANYU_EXTERNAL_DB}),闲鱼行情跳过。")
        return []
    try:
        conn = _sqlite3.connect(f"file:{XIANYU_EXTERNAL_DB}?mode=ro", uri=True)
        conn.row_factory = _sqlite3.Row
        cond = " OR ".join("keyword_slug LIKE ?" for _ in tokens)
        params = [f"%{t}%" for t in tokens]
        row = conn.execute(
            f"""
            SELECT run_id, MAX(snapshot_time) AS latest
            FROM price_snapshots
            WHERE {cond}
            GROUP BY run_id ORDER BY latest DESC LIMIT 1
            """,
            params,
        ).fetchone()
        if row is None:
            conn.close()
            return []
        rows = conn.execute(
            """
            SELECT item_id, title, price, link, seller, snapshot_time
            FROM price_snapshots
            WHERE run_id = ?
            ORDER BY price ASC
            """,
            (row["run_id"],),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[compare] 闲鱼外部源读取失败: {e.__class__.__name__} {e}")
        return []


def _load_latest_run_items(keyword: str, platform: str) -> list[dict]:
    """取该关键词+平台最新一轮 run 的全部快照行。闲鱼=外部旧监控器库,其余=本库。"""
    if platform == "goofish":
        return _load_latest_run_items_xianyu_external(keyword)
    slug = normalize_keyword_slug(keyword)
    with sqlite_connection() as conn:
        row = conn.execute(
            """
            SELECT run_id, MAX(snapshot_time) AS latest
            FROM price_snapshots
            WHERE keyword_slug = ? AND platform = ?
            GROUP BY run_id ORDER BY latest DESC LIMIT 1
            """,
            (slug, platform),
        ).fetchone()
        if row is None:
            return []
        rows = conn.execute(
            """
            SELECT item_id, title, price, link, seller, snapshot_time
            FROM price_snapshots
            WHERE keyword_slug = ? AND platform = ? AND run_id = ?
            ORDER BY price ASC
            """,
            (slug, platform, row["run_id"]),
        ).fetchall()
    return [dict(r) for r in rows]


def _keyword_model_tokens(keyword: str) -> set[str]:
    """关键词里的型号 token(字母数字,如 fold5):标题必须全含才算同型号。"""
    text = re.sub(r"\s+", " ", str(keyword or "").lower())
    return set(t for t in re.split(r"[^0-9a-z]+", text) if len(t) >= 2)


def summarize_platform(keyword: str, platform: str) -> PlatformSummary:
    items = _load_latest_run_items(keyword, platform)
    # 配件过滤:手机壳/贴膜等非整机不参与比价
    items = [it for it in items if not _is_accessory(it.get("title", ""))]
    # 型号精确过滤:标题须含关键词全部型号 token(Fold ≠ Fold5,防上代机型混入)
    model_tokens = _keyword_model_tokens(keyword)
    if model_tokens:
        items = [
            it for it in items
            if all(t in it.get("title", "").lower().replace(" ", "") for t in model_tokens)
        ]
    summary = PlatformSummary(platform=platform, items=items[:50])
    if not items:
        return summary
    prices = sorted(float(it["price"]) for it in items)
    summary.item_count = len(items)
    summary.lowest_price = prices[0]
    summary.median_price = prices[len(prices) // 2]
    summary.latest_run = items[0].get("snapshot_time", "")
    lowest = items[0]
    summary.lowest_title = lowest.get("title", "")
    summary.lowest_link = lowest.get("link", "")
    return summary


def compare_keyword(keyword: str, platforms: Optional[list[str]] = None) -> dict:
    """跨平台比价主入口:各平台最新行情 + 跨平台最低价差价率 + 同款候选。"""
    from src.platforms import PLATFORM_DISPLAY_NAMES

    platforms = platforms or list(PLATFORM_DISPLAY_NAMES.keys())
    summaries = {p: summarize_platform(keyword, p) for p in platforms}
    active = {p: s for p, s in summaries.items() if s.item_count > 0}

    result: dict = {
        "keyword": keyword,
        "platforms": {
            p: {
                "display": PLATFORM_DISPLAY_NAMES.get(p, p),
                "item_count": s.item_count,
                "lowest": s.lowest_price,
                "median": s.median_price,
                "latest_run": s.latest_run,
                "lowest_title": s.lowest_title,
                "lowest_link": s.lowest_link,
            }
            for p, s in summaries.items()
        },
        "cross_platform": None,
        "same_item_candidates": [],
    }

    if len(active) >= 2:
        cheapest_platform = min(active, key=lambda p: active[p].lowest_price)
        dearest_platform = max(active, key=lambda p: active[p].lowest_price)
        lo = active[cheapest_platform].lowest_price
        hi = active[dearest_platform].lowest_price
        result["cross_platform"] = {
            "cheapest": {"platform": cheapest_platform, "price": lo},
            "most_expensive": {"platform": dearest_platform, "price": hi},
            "gap": round(hi - lo, 2),
            "gap_pct": round((hi - lo) / hi * 100, 1) if hi else 0.0,
        }

        # 同款候选:以最便宜平台的最低价商品为锚,找其他平台标题相似且价格相近的商品
        anchor = active[cheapest_platform]
        if anchor.lowest_title:
            for p, s in active.items():
                if p == cheapest_platform:
                    continue
                for it in s.items:
                    sim = _similarity(anchor.lowest_title, it.get("title", ""))
                    if sim >= 0.35:
                        result["same_item_candidates"].append(
                            {
                                "platform": p,
                                "title": it.get("title", "")[:80],
                                "price": it.get("price"),
                                "link": it.get("link", ""),
                                "similarity": round(sim, 2),
                            }
                        )
            result["same_item_candidates"].sort(key=lambda x: (-x["similarity"], x["price"]))
            result["same_item_candidates"] = result["same_item_candidates"][:10]

    return result


def format_compare_report(result: dict) -> str:
    """比价结果转可读报告(飞书/控制台通用)。"""
    lines = [f"# 全网比价: {result['keyword']}", ""]
    for p, s in result["platforms"].items():
        if s["item_count"] == 0:
            lines.append(f"- [{s['display']}] 暂无数据")
        else:
            lines.append(
                f"- [{s['display']}] 最低 ¥{s['lowest']:.0f} / 中位 ¥{s['median']:.0f}"
                f"({s['item_count']} 件) {s['lowest_title'][:30]}"
            )
    cp = result.get("cross_platform")
    if cp:
        lines.append("")
        lines.append(
            f"**跨平台价差**: {cp['cheapest']['platform']} ¥{cp['cheapest']['price']:.0f}"
            f" → {cp['most_expensive']['platform']} ¥{cp['most_expensive']['price']:.0f}"
            f"(差 ¥{cp['gap']:.0f} / {cp['gap_pct']}%)"
        )
    if result["same_item_candidates"]:
        lines.append("")
        lines.append("**同款候选**(标题相似度≥0.35,待 GLM 精判):")
        for c in result["same_item_candidates"][:5]:
            lines.append(f"- [{c['platform']}] ¥{float(c['price']):.0f} (sim={c['similarity']}) {c['title'][:40]}")
    return "\n".join(lines)
