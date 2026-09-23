"""多平台 Web 采集公共层:浏览器启动 / 登录态解析 / 接口样本落盘 / 通用 JSON 探底 / 统一落库。

平台适配器(jd.py / taobao.py)只写平台差异:搜索 URL、接口识别、字段映射。
统一商品中文键与闲鱼 parsers.py 对齐,下游(快照/结果/通知)零改动。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, List, Optional

from src.infrastructure.persistence.storage_names import build_result_filename
from src.services.price_history_service import record_market_snapshots
from src.services.result_storage_service import save_result_record

# 铁律1:headless 必被风控拦,有头+屏外窗口+禁 occlusion(旧监控器实战参数)
LAUNCH_ARGS = [
    "--window-position=-32000,-32000",
    "--disable-features=CalculateNativeWinOcclusion",
]

# CDP 专用 Chrome 数据目录(与日常 Chrome 隔离,避免指纹互染;可用环境变量覆盖)
CDP_PROFILE_DIR = os.getenv("CDP_CHROME_PROFILE") or os.path.abspath(
    os.path.join("state", "cdp-chrome-profile")
)
# Windows PowerShell 启动命令提示(登录态持久化在此 profile,关窗不掉)
CDP_START_HINT = (
    "Start-Process chrome -ArgumentList '--remote-debugging-port=9222',"
    f"'--user-data-dir={CDP_PROFILE_DIR}'"
)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


async def launch_headful_browser(playwright):
    return await playwright.chromium.launch(
        headless=False, channel="chrome", args=LAUNCH_ARGS
    )


async def new_desktop_context(browser, storage_state: Optional[str] = None):
    kwargs = {
        "user_agent": DESKTOP_UA,
        "viewport": {"width": 1440, "height": 900},
        "locale": "zh-CN",
    }
    if storage_state:
        kwargs["storage_state"] = storage_state
    return await browser.new_context(**kwargs)


def resolve_login_state_file(task_config: dict, platform: str) -> Optional[str]:
    """登录态解析顺序:任务 fixed 指定 > state/<platform>/ 首个 json > 根目录 <platform>_state.json。

    与闲鱼的 state/acc1.json 完全隔离(立项铁律4)。
    """
    fixed = str(task_config.get("account_state_file") or "").strip()
    if fixed and os.path.exists(fixed):
        return fixed
    state_dir = os.getenv("ACCOUNT_STATE_DIR", "state")
    for candidate in (os.path.join(state_dir, platform), state_dir):
        if os.path.isdir(candidate):
            for name in sorted(os.listdir(candidate)):
                if name.endswith(".json") and platform in os.path.join(candidate, name):
                    return os.path.join(candidate, name)
    # state/ 根目录兜底:state/jd_state.json 命名约定
    root_state = os.path.join(state_dir, f"{platform}_state.json")
    if os.path.exists(root_state):
        return root_state
    return None


def dump_api_sample(platform: str, keyword: str, url: str, payload: Any) -> str:
    """接口原始响应落盘 logs/platform_samples/,供精确解析函数定型。"""
    sample_dir = os.path.join("logs", "platform_samples")
    os.makedirs(sample_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_kw = "".join(c for c in keyword if c.isalnum())[:20] or "kw"
    path = os.path.join(sample_dir, f"{platform}_{safe_kw}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"url": url, "captured_at": ts, "payload": payload},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[{platform}] 接口样本已落盘: {path}")
    return path


# ---------------- 通用 JSON 探底(精确解析定型前的过渡方案) ----------------

_TITLE_KEYS = ("title", "warename", "wname", "skuname", "itemtitle", "itemname")
_ID_KEYS = ("skuid", "sku_id", "wareid", "itemid", "item_id")
_LINK_KEYS = ("itemurl", "clickurl", "url", "link")


def _looks_like_item(d: dict) -> bool:
    text = json.dumps(d, ensure_ascii=False)[:600].lower()
    return any(t in text for t in _TITLE_KEYS) and "price" in text


def deep_find_item_lists(node: Any, depth: int = 0) -> List[List[dict]]:
    """递归寻找"元素普遍含标题+价格特征"的列表节点。命中返回最浅层(最外层列表)。"""
    if depth > 8 or isinstance(node, str):
        return []
    if isinstance(node, list) and len(node) >= 3 and all(isinstance(x, dict) for x in node[:5]):
        if sum(1 for x in node[:5] if _looks_like_item(x)) >= 3:
            return [node]
    found: List[List[dict]] = []
    if isinstance(node, dict):
        for v in node.values():
            found.extend(deep_find_item_lists(v, depth + 1))
    elif isinstance(node, list):
        for v in node:
            found.extend(deep_find_item_lists(v, depth + 1))
    return found


def _flatten(obj: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in obj.items():
        key = f"{prefix}.{k}".lower()
        if isinstance(v, dict):
            flat.update(_flatten(v, key))
        elif isinstance(v, list):
            flat[key] = json.dumps(v, ensure_ascii=False)
        else:
            flat[key] = v
    return flat


def _is_number(v) -> bool:
    if isinstance(v, (int, float)):
        return True
    return isinstance(v, str) and bool(re.fullmatch(r"\d+(\.\d+)?", v.strip()))


def map_generic_items(raw_items: List[dict], platform: str) -> List[dict]:
    """启发式字段映射到统一中文键。平台真实样本到手后应替换为精确解析函数。"""
    out: List[dict] = []
    for it in raw_items:
        flat = _flatten(it)
        title = next((flat[k] for k in flat for t in _TITLE_KEYS if k.endswith(t) and flat[k]), "")
        price = next(
            (flat[k] for k in flat if "price" in k and _is_number(flat[k]) and float(flat[k]) > 0),
            None,
        )
        item_id = next((str(flat[k]) for k in flat for t in _ID_KEYS if k.endswith(t) and flat[k]), "")
        link = next(
            (str(flat[k]) for k in flat for t in _LINK_KEYS if k.endswith(t) and str(flat[k]).startswith("http")),
            "",
        )
        if not (title and price is not None):
            continue
        out.append(
            {
                "商品标题": str(title)[:200],
                "当前售价": f"¥{float(price):.2f}",
                "商品原价": "暂无",
                "“想要”人数": "NaN",
                "商品标签": [],
                "发货地区": "",
                "卖家昵称": "",
                "商品链接": link,
                "发布时间": "未知时间",
                "商品ID": item_id or link,
            }
        )
    print(f"[{platform}] 通用探底映射出 {len(out)} 条商品(待样本精确解析校准)。")
    return out


async def persist_platform_items(
    platform: str,
    task_config: dict,
    items: List[dict],
    run_id: str,
) -> int:
    """统一落库:价格快照(比价核心)+ result_items(WebUI 展示)。返回落库商品数。"""
    if not items:
        return 0
    keyword = task_config.get("keyword", "")
    task_name = task_config.get("task_name", "Untitled Task")
    snapshot_time = datetime.now().isoformat()

    record_market_snapshots(
        keyword=keyword,
        task_name=task_name,
        items=items,
        run_id=run_id,
        snapshot_time=snapshot_time,
        platform=platform,
    )

    saved = 0
    for item in items:
        record = {
            "搜索关键字": keyword,
            "任务名称": task_name,
            "爬取时间": snapshot_time,
            "商品信息": item,
            "卖家信息": {},
            "platform": platform,
            "ai_analysis": {
                "is_recommended": False,
                "analysis_source": f"{platform}_capture",
            },
        }
        try:
            if await save_result_record(record, keyword):
                saved += 1
        except Exception as e:
            print(f"[{platform}] 结果落库异常(商品仍入快照): {e.__class__.__name__} {e}")
    print(f"[{platform}] 快照+结果落库完成: {len(items)} 条快照 / {saved} 条结果。")
    return len(items)
