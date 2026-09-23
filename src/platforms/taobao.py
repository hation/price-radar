"""淘宝平台适配器(CDP 接管模式,2026-09-18 全线打通)。

实战定案(实测联调,证据见 logs/platform_samples/):
1. playwright launch 的浏览器带自动化指纹 → 淘宝弹滑块/静默扣数据,不可用
2. 正解 = CDP 接管独立数据目录的真 Chrome(--remote-debugging-port=9222),
   零自动化痕迹,风控放行(未登录都出 48 商品)
3. 直落搜索 URL 会被强制验证 → 必须拟人行为链:首页→鼠标轨迹→点击搜索框→逐字打字→点搜索按钮
4. 淘宝点击搜索 = **新 tab 打开结果页**(window.open),必须捕获新 tab 而非盯原 page
5. 结果数据用 DOM 解析(a[href*=item.htm] 卡片,innerText 含标题+¥价格),比接口拦截抗改版

前置:专用 Chrome 已启动(TAOBAO_USE_CDP=1,TAOBAO_CDP_ENDPOINT):
  <CDP_START_HINT>
"""
from __future__ import annotations

import os
import random
from datetime import datetime
from urllib.parse import quote

from src.platforms._web import (
    CDP_START_HINT,
    dump_api_sample,
    persist_platform_items,
    resolve_login_state_file,
)

# 结果页 DOM 解析:商品卡片 = a[href*=item.htm],innerText 含 标题+¥价格
DOM_PARSE_JS = """() => {
    const out = [];
    const seen = new Set();
    for (const a of document.querySelectorAll('a[href*="item.htm"]')) {
        const href = a.href || '';
        const m = href.match(/[?&]id=(\\d+)/);
        if (!m) continue;
        const itemId = m[1];
        if (seen.has(itemId)) continue;
        seen.add(itemId);
        const text = (a.innerText || '').replace(/\\n+/g, ' ').trim();
        const pm = text.match(/¥\\s*([\\d,]+\\.?\\d*)/);
        const price = pm ? pm[1].replace(/,/g, '') : '';
        let title = text;
        if (pm) {
            const idx = text.indexOf(pm[0]);
            title = text.slice(0, idx).trim();
        }
        if (!title || !price) continue;
        out.push({itemId, title, price, link: href});
    }
    return out;
}"""


async def _human_move_to(page, box_loc, x_ratio=0.5):
    """多段折线+随机抖动的鼠标轨迹(拟人核心)。"""
    bb = await box_loc.bounding_box()
    if not bb:
        return
    tx = bb["x"] + bb["width"] * x_ratio
    ty = bb["y"] + bb["height"] * random.uniform(0.4, 0.6)
    x, y = random.randint(80, 500), random.randint(120, 480)
    await page.mouse.move(x, y)
    segs = random.randint(5, 9)
    for i in range(1, segs + 1):
        t = i / segs
        nx = x + (tx - x) * t + random.uniform(-10, 10) * (1 - t)
        ny = y + (ty - y) * t + random.uniform(-8, 8) * (1 - t)
        await page.mouse.move(nx, ny, steps=random.randint(2, 6))
        await page.wait_for_timeout(random.randint(8, 50))
    await page.mouse.move(tx, ty)
    await page.wait_for_timeout(random.randint(120, 400))


async def _wait_new_search_tab(context, origin_page, timeout_s: int = 30):
    """淘宝点击搜索 = 新 tab 打开结果页;轮询捕获新增的 s.taobao.com/search tab。"""
    known = set(id(pg) for pg in context.pages)
    for _ in range(timeout_s * 2):
        await origin_page.wait_for_timeout(500)
        for pg in context.pages:
            if id(pg) not in known and "s.taobao.com/search" in pg.url:
                return pg
    # 兜底:原 tab 自己跳转了(行为变化时)
    for pg in context.pages:
        if pg is not origin_page and "s.taobao.com/search" in pg.url:
            return pg
    return None


async def scrape_taobao(task_config: dict, debug_limit: int = 0):
    """淘宝搜索采集(CDP 接管):返回本次落库的新商品数。"""
    platform = "taobao"
    keyword = task_config.get("keyword", "")
    task_name = task_config.get("task_name", "Untitled Task")
    max_pages = int(task_config.get("max_pages", 1) or 1)
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")

    cdp_endpoint = os.getenv("TAOBAO_CDP_ENDPOINT", "http://127.0.0.1:9222")
    if os.getenv("TAOBAO_USE_CDP", "1") != "1":
        print("[taobao] TAOBAO_USE_CDP=0:CDP 是唯一可用路线(指纹问题实证),请保持 1。")
        return 0

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(cdp_endpoint, timeout=10000)
        except Exception as e:
            print(f"[taobao] CDP 连接失败({cdp_endpoint}): {e.__class__.__name__}")
            print("[taobao] 请先启动专用 Chrome(指纹真,风控放行):")
            print(f"  {CDP_START_HINT}")
            return 0
        context = browser.contexts[0]
        print(f"[taobao] CDP 已接管 {cdp_endpoint}(tab 数 {len(context.pages)})")
        page = await context.new_page()

        try:
            # ---- 拟人行为链:首页 -> 轨迹移到搜索框 -> 点击 -> 逐字打字 -> 点击搜索按钮 ----
            print("[taobao] 拟人路径: 开淘宝首页……")
            await page.goto("https://www.taobao.com/", wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(random.randint(2500, 4500))

            box = page.locator("input[name='q'], #q, [class*='search'] input").first
            if not await box.count():
                print("[taobao] 首页搜索框未找到(页面改版?),样本落盘。")
                dump_api_sample(platform, keyword, page.url, {"error": "no_search_box"})
                return 0
            await _human_move_to(page, box)
            await page.mouse.down()
            await page.mouse.up()
            await page.wait_for_timeout(random.randint(500, 1200))
            for ch in keyword:
                await box.type(ch, delay=random.randint(80, 220))
                if random.random() < 0.15:
                    await page.wait_for_timeout(random.randint(200, 600))
            await page.wait_for_timeout(random.randint(600, 1500))

            btn = page.locator("button[class*='btn-search'], .btn-search, button[class*='btn']").first
            if await btn.count():
                await _human_move_to(page, btn)
                await page.mouse.down()
                await page.mouse.up()
                print("[taobao] 已点击搜索按钮(等待新 tab 结果页)……")
            else:
                await box.press("Enter")
                print("[taobao] 未找到搜索按钮,回车替代。")

            # ---- 捕获结果 tab(淘宝=新 tab 打开结果页) ----
            result_page = await _wait_new_search_tab(context, page, timeout_s=30)
            if not result_page:
                print("[taobao] 30 秒未等到搜索结果 tab。")
                dump_api_sample(platform, keyword, page.url, {"error": "no_result_tab"})
                return 0
            print(f"[taobao] 结果 tab 到手: {result_page.url[:90]}")
            await result_page.wait_for_timeout(6000)  # 等渲染

            # ---- 结果页 DOM 解析(拟人滚动触发懒加载) ----
            items: list[dict] = []
            for page_num in range(1, max_pages + 1):
                for _ in range(5):
                    await result_page.mouse.wheel(0, random.randint(900, 1600))
                    await result_page.wait_for_timeout(random.randint(900, 1800))
                rows = await result_page.evaluate(DOM_PARSE_JS)
                print(f"[taobao] 第 {page_num} 页 DOM 解析出 {len(rows)} 条商品。")
                for r in rows:
                    items.append(
                        {
                            "商品标题": r["title"],
                            "当前售价": f"¥{float(r['price']):.2f}",
                            "商品原价": "暂无",
                            "“想要”人数": "NaN",
                            "商品标签": [],
                            "发货地区": "",
                            "卖家昵称": "",
                            "商品链接": r["link"],
                            "发布时间": "未知时间",
                            "商品ID": r["itemId"],
                        }
                    )
                if page_num < max_pages:
                    nxt = result_page.locator("[class*='next-next'], button[next], a[class*='next']").first
                    if await nxt.count() and await nxt.is_enabled():
                        await _human_move_to(result_page, nxt)
                        await result_page.mouse.down()
                        await result_page.mouse.up()
                        await result_page.wait_for_timeout(4000)
                    else:
                        break

            if not items:
                dump_api_sample(platform, keyword, result_page.url, {"error": "dom_parse_empty"})
                return 0

            if debug_limit > 0:
                items = items[:debug_limit]
            return await persist_platform_items(platform, task_config, items, run_id)
        finally:
            # 只关自己开的 tab,不动用户其他浏览器窗口
            try:
                await page.close()
            except Exception:
                pass
            try:
                if "result_page" in dir() and result_page:
                    await result_page.close()
            except Exception:
                pass
            await browser.close()  # connect_over_cdp 的 close 仅断开连接
