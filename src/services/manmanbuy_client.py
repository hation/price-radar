"""慢慢买历史价格客户端(页面查询版,2026-09-19 实测定型)。

路线演进:
- v1 requests 直调 api.ashx + 复刻签名 → 实测"无效的票据",签名机制非公开,死路;
- v2 (本版) playwright 页面查询:打开 HistoryLowest.aspx → 键盘输入商品链接 →
  点查询 → 解析结果区 DOM。签名由慢慢买自己的 JS 完成,永不过时。

实测要点(全部踩坑实证):
- 京东商品查询必须"京东授权"(用慢慢买App扫码,授权标记落在登录会话账号上);
  淘宝/天猫免授权但覆盖率差(Fold5 品类 4/4 暂未收录)。
- 登录态:微信扫码一次,cookies 持久(state/manmanbuy_browser.json);
  专用 CDP Chrome(9222)里已注入并完成授权,优先接管。
- 结果区文本结构:
    历史价格走势图 / <商品名> / <站点名> <N>个月历史最低：xx(yyyy-mm-dd) <N>天均价：xx
    ... 到手价列表行:<日期> | <标题> | 到手价：￥<价>
  "暂未收录" = 该商品无数据。

返回结构(兼容旧签名): {"code":0|1|2|3, "msg":str, "data":{siteName, spName,
currentPrice, haveTrend, datePrice, ...}},datePrice 为 JSON 字符串
[[ts,price,"备注"],...],由 parse_trend 统一解析。
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from typing import Optional, Union

CDP_ENDPOINT = os.getenv("MANMANBUY_CDP_ENDPOINT", "http://127.0.0.1:9222")
QUERY_URL = "https://tool.manmanbuy.com/HistoryLowest.aspx"
STATE_FILE = os.path.join("state", "manmanbuy_browser.json")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# 结果区正则(实测 DOM innerText 定型)
_RE_LOWEST = re.compile(r"历史最低：\s*([\d.]+)\s*\(([\d-]+)\)")
_RE_AVG = re.compile(r"(\d+)天均价：\s*([\d.]+)")
_RE_DEAL = re.compile(r"(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*\|\s*到手价：￥\s*([\d,]+\.?\d*)")


async def _type_like_human(page, item_url: str) -> None:
    """拟人输入商品链接并点击查询(直接 set value 不触发框架校验)。"""
    await page.click("#historykey")
    for ch in item_url:
        await page.keyboard.type(ch, delay=random.randint(5, 25))
    await page.wait_for_timeout(random.randint(300, 700))
    await page.click("#searchHistory")


async def _fetch_via_cdp(item_url: str, timeout_s: int = 60) -> Optional[dict]:
    """专用 CDP Chrome 查询(持久授权态,首选)。"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_ENDPOINT, timeout=6000)
        try:
            ctx = browser.contexts[0]
            page = await ctx.new_page()
            try:
                return await _query_on_page(page, item_url, timeout_s)
            finally:
                await page.close()
        finally:
            await browser.close()  # 仅断连


async def _fetch_via_temp(item_url: str, timeout_s: int = 60) -> Optional[dict]:
    """临时浏览器 + state cookies 查询(CDP 不可用时的后备)。"""
    from playwright.async_api import async_playwright

    if not os.path.exists(STATE_FILE):
        print("[manmanbuy] 无登录态文件,且 CDP 不可用 → 放弃")
        return None
    with open(STATE_FILE, encoding="utf-8") as f:
        cookies = json.load(f).get("cookies", [])
    to_add = []
    for c in cookies:
        nc = {k: c[k] for k in ("name", "value", "domain", "path") if k in c}
        for k in ("expires", "httpOnly", "secure", "sameSite"):
            if k in c and c[k] is not None:
                nc[k] = c[k]
        if "domain" not in nc:
            nc["url"] = "https://www.manmanbuy.com/"
        to_add.append(nc)

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        try:
            ctx = await browser.new_context(
                user_agent=_UA, locale="zh-CN", viewport={"width": 1024, "height": 768})
            await ctx.add_cookies(to_add)
            page = await ctx.new_page()
            return await _query_on_page(page, item_url, timeout_s)
        finally:
            await browser.close()


async def _query_on_page(page, item_url: str, timeout_s: int) -> Optional[dict]:
    """在已就绪的页面上完成查询+解析。"""
    try:
        await page.goto(QUERY_URL, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        print(f"[manmanbuy] 打开查询页失败: {e.__class__.__name__}")
        return None
    await page.wait_for_timeout(2200)

    body = await page.inner_text("body")
    if "请登录" in body[:200]:
        print("[manmanbuy] 登录态失效(页面要求登录)")
        return {"code": 2, "msg": "login_required", "data": {}}

    await _type_like_human(page, item_url)

    # 等结果:走势图渲染 / 暂未收录 / 授权弹层
    verdict = ""
    for _ in range(timeout_s):
        await page.wait_for_timeout(1000)
        try:
            txt = await page.inner_text("body")
        except Exception:
            continue
        if "历史价格走势图" in txt:
            verdict = "ok"
            break
        if "暂未收录" in txt:
            verdict = "no_data"
            break
        if "京东授权" in txt:
            verdict = "need_auth"
            break
    else:
        verdict = "timeout"

    if verdict == "need_auth":
        print("[manmanbuy] 京东商品需授权(慢慢买App扫码),当前会话未授权")
        return {"code": 3, "msg": "jd_auth_required", "data": {}}
    if verdict == "no_data":
        return {"code": 1, "msg": "not_indexed", "data": {"haveTrend": 0}}
    if verdict != "ok":
        return {"code": 1, "msg": verdict, "data": {}}

    await page.wait_for_timeout(2000)  # 等列表渲染完
    txt = await page.inner_text("body")
    return {"code": 0, "msg": "成功", "data": _parse_result_text(txt)}


def _parse_result_text(txt: str) -> dict:
    """结果区 innerText → data dict(兼容旧 api 字段名)。"""
    block_start = txt.find("历史价格走势图")
    block = txt[block_start:block_start + 3000] if block_start >= 0 else txt

    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    sp_name, site_name = "", ""
    if len(lines) >= 3:
        sp_name = lines[1]          # 走势图下一行 = 商品名
        site_name = lines[2].split()[0] if lines[2] else ""  # 站点名行首词

    m_low = _RE_LOWEST.search(block)
    m_avg = _RE_AVG.search(block)

    deals = []
    for m in _RE_DEAL.finditer(block.replace("\n", " | ")):
        date_s, title, price_s = m.group(1), m.group(2).strip(), m.group(3).replace(",", "")
        try:
            ts = int(time.mktime(time.strptime(date_s, "%Y-%m-%d")))
            deals.append([ts, float(price_s), title[:40]])
        except Exception:
            continue
    deals.sort(key=lambda x: x[0])

    current = deals[-1][1] if deals else None
    return {
        "spName": sp_name[:100],
        "siteName": site_name,
        "currentPrice": current,
        "haveTrend": 1 if (m_low or deals) else 0,
        "lowestPrice": float(m_low.group(1)) if m_low else None,
        "lowestDate": m_low.group(2) if m_low else "",
        "avgPrice": float(m_avg.group(2)) if m_avg else None,
        "avgDays": int(m_avg.group(1)) if m_avg else 0,
        "datePrice": json.dumps(deals, ensure_ascii=False),
    }


async def _fetch_history_trend_async(item_url: str, timeout_s: int = 60) -> Optional[dict]:
    for fn in (_fetch_via_cdp, _fetch_via_temp):
        try:
            result = await fn(item_url, timeout_s)
        except Exception as e:
            print(f"[manmanbuy] {fn.__name__} 异常: {e.__class__.__name__} {e}")
            result = None
        if result is not None:
            return result
        print(f"[manmanbuy] {fn.__name__} 未取得结果,试下一路线")
    return None


def fetch_history_trend(item_url: str, timeout_s: int = 60) -> Union[Optional[dict], object]:
    """查询商品历史价(页面路线)。

    同步环境直接返回结果;已在事件循环内则返回协程(调用方 await)。
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        return _fetch_history_trend_async(item_url, timeout_s)
    return asyncio.run(_fetch_history_trend_async(item_url, timeout_s))


def parse_trend(data: dict) -> dict:
    """把 api data 解析为标准化历史价结构。"""
    if not data or not isinstance(data, dict):
        return {}
    trend = data.get("datePrice") or ""
    points: list[dict] = []
    if isinstance(trend, str) and trend.strip():
        try:
            raw = json.loads(trend)
        except json.JSONDecodeError:
            for ts, price in re.findall(r"\[(\d{9,13})\s*,\s*([\d.]+)", trend):
                points.append({"ts": int(ts), "price": float(price)})
        else:
            for item in raw:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    try:
                        points.append({"ts": int(item[0]), "price": float(item[1])})
                    except (TypeError, ValueError):
                        continue
    for p in points:
        if p["ts"] >= 1_000_000_000_000:
            p["ts"] //= 1000
    prices = [p["price"] for p in points]
    return {
        "site": data.get("siteName", ""),
        "title": data.get("spName", ""),
        "current_price": data.get("currentPrice"),
        "have_trend": bool(data.get("haveTrend")),
        "lowest": data.get("lowestPrice") or (min(prices) if prices else None),
        "lowest_date": data.get("lowestDate", ""),
        "avg_price": data.get("avgPrice"),
        "points": points,
        "highest": max(prices) if prices else None,
        "first_ts": points[0]["ts"] if points else None,
        "last_ts": points[-1]["ts"] if points else None,
    }


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    url = sys.argv[1] if len(sys.argv) > 1 else "https://item.jd.com/100012043978.html"
    result = fetch_history_trend(url)
    if result is None:
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False)[:300])
    data = result.get("data") or {}
    if data.get("haveTrend"):
        trend = parse_trend(data)
        print(f"站点: {trend['site']} | 商品: {trend['title'][:40]}")
        print(f"当前: ¥{trend['current_price']} | 历史最低: ¥{trend['lowest']}({trend.get('lowest_date', '')})"
              f" | {data.get('avgDays', 0)}天均价: ¥{trend.get('avg_price')}")
        print(f"到手价记录: {len(trend['points'])} 条")
    else:
        print("无趋势数据:", result.get("msg"))
