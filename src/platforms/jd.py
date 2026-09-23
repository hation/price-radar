"""京东平台适配器(CDP 接管模式,2026-09-18 实测打通)。

实战定案:
1. 无登录直抓 → 403 风控(spike 实测);CDP 接管真 Chrome + 拟人链 = 与淘宝同款解法
2. 京东登录态存 state/jd_state.json;专用 Chrome 登录一次京东更稳(cookie 注入免扫码)
3. 拟人链:首页 → 鼠标轨迹 → 点击搜索框 → 逐字打字 → 点击搜索按钮
4. 京东搜索跳转可能是同 tab 导航或新 tab(双兼容捕获)
5. 结果 DOM 解析:商品链接 item.jd.com/item.htm?id=,innerText 含 ¥ 价格

前置:专用 Chrome(同淘宝共用,数据目录见 _web.CDP_PROFILE_DIR):
  <CDP_START_HINT>
"""
from __future__ import annotations

import os
import random
from datetime import datetime

from src.platforms._web import CDP_START_HINT, dump_api_sample, persist_platform_items

# 结果页 DOM 解析(京东新版 2026-09 实测):商品卡 = [data-sku] 元素(hash class 化,
# 无 <a href>,跳转靠 JS),sku 在 data-sku 属性,价格/标题在卡内文本
DOM_PARSE_JS = """() => {
    const out = [];
    const seen = new Set();
    for (const card of document.querySelectorAll('[data-sku]')) {
        const sku = card.getAttribute('data-sku');
        if (!sku || !/^\\d{6,}$/.test(sku) || seen.has(sku)) continue;
        seen.add(sku);
        const txt = (card.innerText || '').replace(/\\n+/g, ' ').trim();
        const pm = txt.match(/¥\\s*([\\d,]+\\.?\\d*)/) || txt.match(/[￥¥]\\s*([\\d,]+)/);
        const price = pm ? pm[1].replace(/,/g, '') : '';
        let title = '';
        const tEl = card.querySelector('[class*="title" i], [class*="name" i]');
        if (tEl) title = (tEl.innerText || '').replace(/\\n+/g, ' ').trim();
        if (!title && pm) title = txt.slice(0, txt.indexOf(pm[0])).trim();
        if (!title || !price) continue;
        out.push({itemId: sku, title: title.slice(0, 200), price, link: 'https://item.jd.com/' + sku + '.html'});
    }
    return out;
}"""


async def _human_move_to(page, box_loc, x_ratio=0.5):
    """多段折线+随机抖动的鼠标轨迹。"""
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


async def scrape_jd(task_config: dict, debug_limit: int = 0):
    """京东搜索采集(CDP 接管):返回本次落库的新商品数。"""
    platform = "jd"
    keyword = task_config.get("keyword", "")
    task_name = task_config.get("task_name", "Untitled Task")
    max_pages = int(task_config.get("max_pages", 1) or 1)
    min_price = task_config.get("min_price")
    max_price = task_config.get("max_price")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")

    cdp_endpoint = os.getenv("JD_CDP_ENDPOINT", "http://127.0.0.1:9222")
    if os.getenv("JD_USE_CDP", "1") != "1":
        print("[jd] JD_USE_CDP=0:CDP 是首选路线,请保持 1。")
        return 0

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(cdp_endpoint, timeout=10000)
        except Exception as e:
            print(f"[jd] CDP 连接失败({cdp_endpoint}): {e.__class__.__name__}")
            print("[jd] 请先启动专用 Chrome(与淘宝共用):")
            print(f"  {CDP_START_HINT}")
            return 0
        context = browser.contexts[0]
        print(f"[jd] CDP 已接管 {cdp_endpoint}")
        page = await context.new_page()

        try:
            # ---- 拟人行为链:京东首页 -> 轨迹 -> 点击搜索框 -> 逐字打字 -> 点搜索按钮 ----
            print("[jd] 拟人路径: 开京东首页……")
            await page.goto("https://www.jd.com/", wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(random.randint(2500, 4500))

            box = page.locator(
                "input.jd_pc_search_bar_react_search_input, input#key, input[name='keyword'], [class*='search'] input[type='text']"
            ).first
            if not await box.count():
                print("[jd] 首页搜索框未找到(页面改版?),样本落盘。")
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

            known_tabs = {id(pg) for pg in context.pages}
            btn = page.locator(
                "button.jd_pc_search_bar_react_search_btn, button:has-text('搜索'), button[class*='search_btn']"
            ).first
            if await btn.count():
                await _human_move_to(page, btn)
                await page.mouse.down()
                await page.mouse.up()
                print("[jd] 已点击搜索按钮。")
            else:
                await box.press("Enter")
                print("[jd] 未找到搜索按钮,回车替代。")

            # ---- 捕获结果页(同 tab 导航或新 tab 双兼容) ----
            result_page = None
            for _ in range(30):
                await page.wait_for_timeout(1000)
                # 新 tab?
                for pg in context.pages:
                    if id(pg) not in known_tabs and ("search.jd.com" in pg.url or "so.jd.com" in pg.url or "search" in pg.url):
                        result_page = pg
                        break
                if result_page:
                    break
                # 原 tab 导航?
                if "search" in page.url and "jd.com" in page.url and page.url != "https://www.jd.com/":
                    result_page = page
                    break
            if not result_page:
                print("[jd] 30 秒未等到搜索结果页。")
                dump_api_sample(platform, keyword, page.url, {"error": "no_result_page", "final_url": page.url})
                return 0
            print(f"[jd] 结果页到手: {result_page.url[:90]}")
            await result_page.wait_for_timeout(6000)

            # ---- DOM 解析 + 拟人滚动 ----
            items: list[dict] = []
            for page_num in range(1, max_pages + 1):
                for _ in range(5):
                    await result_page.mouse.wheel(0, random.randint(900, 1600))
                    await result_page.wait_for_timeout(random.randint(900, 1800))
                rows = await result_page.evaluate(DOM_PARSE_JS)
                print(f"[jd] 第 {page_num} 页 DOM 解析出 {len(rows)} 条商品。")
                if not rows and page_num == 1:
                    body = await result_page.inner_text("body")
                    dump_api_sample(platform, keyword, result_page.url,
                                    {"error": "dom_parse_empty", "body_head": body[:400]})
                    if "验证" in body or "访问频繁" in body or "登录" in body[:300]:
                        print("[jd] 命中风控/登录提示——建议在专用 Chrome 里登录一次京东。")
                    return 0
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
                    nxt = result_page.locator("a.pf-next, a.next, [class*='next']").first
                    if await nxt.count() and await nxt.is_enabled():
                        await _human_move_to(result_page, nxt)
                        await result_page.mouse.down()
                        await result_page.mouse.up()
                        await result_page.wait_for_timeout(4000)
                    else:
                        break

            if not items:
                return 0
            if debug_limit > 0:
                items = items[:debug_limit]
            return await persist_platform_items(platform, task_config, items, run_id)
        finally:
            try:
                await page.close()
            except Exception:
                pass
            try:
                if "result_page" in dir() and result_page and result_page is not page:
                    await result_page.close()
            except Exception:
                pass
            await browser.close()  # connect_over_cdp 的 close 仅断开连接
