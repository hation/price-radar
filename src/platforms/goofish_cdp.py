"""闲鱼平台适配器(CDP 接管模式)。

与底座原生 scrape_xianyu 的关系:原生版(playwright launch+AI 打分管线)因自动化指纹
不可用(淘宝同款问题),本适配器走 CDP 接管+DOM 解析的纯数据路;AI 打分管线后置。

闲鱼特殊性(vs 淘宝/京东):
- 登录态:专用 Chrome 里以淘宝账号授权登录一次即持久(阿里通行证,2026-09-19 实证)
- 搜索 URL 直达(www.goofish.com/search?q=)在旧监控器实战数月,闲鱼对此宽容,无需拟人链
- 商品链接形态:goofish.com/item?id=<itemId>
"""
from __future__ import annotations

import os
import random
from datetime import datetime

from src.platforms._web import CDP_START_HINT, dump_api_sample, persist_platform_items

# 结果页 DOM 解析:闲鱼商品卡 a[href*=item?id=],innerText 含标题+¥价格
DOM_PARSE_JS = """() => {
    const out = [];
    const seen = new Set();
    for (const a of document.querySelectorAll('a[href*="item?id="]')) {
        const href = a.href || '';
        const m = href.match(/[?&]id=(\\d+)/);
        if (!m) continue;
        const itemId = m[1];
        if (seen.has(itemId)) continue;
        seen.add(itemId);
        const text = (a.innerText || '').replace(/\\n+/g, ' ').trim();
        const pm = text.match(/¥\\s*([\\d,]+\\.?\\d*)/) || text.match(/[￥¥]\\s*([\\d,]+)/);
        const price = pm ? pm[1].replace(/,/g, '') : '';
        let title = pm ? text.slice(0, text.indexOf(pm[0])).trim() : text;
        if (!title || !price) continue;
        out.push({itemId, title: title.slice(0, 200), price, link: 'https://www.goofish.com/item?id=' + itemId});
    }
    return out;
}"""


async def scrape_goofish(task_config: dict, debug_limit: int = 0):
    """闲鱼搜索采集(CDP 接管):返回本次落库的新商品数。"""
    platform = "goofish"
    keyword = task_config.get("keyword", "")
    task_name = task_config.get("task_name", "Untitled Task")
    max_pages = int(task_config.get("max_pages", 1) or 1)
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")

    cdp_endpoint = os.getenv("GOOFISH_CDP_ENDPOINT", "http://127.0.0.1:9222")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(cdp_endpoint, timeout=10000)
        except Exception as e:
            print(f"[goofish] CDP 连接失败({cdp_endpoint}): {e.__class__.__name__}")
            print("[goofish] 请先启动专用 Chrome 并登录闲鱼:")
            print(f"  {CDP_START_HINT}")
            return 0
        context = browser.contexts[0]
        print(f"[goofish] CDP 已接管 {cdp_endpoint}")
        page = await context.new_page()

        try:
            from urllib.parse import quote

            url = f"https://www.goofish.com/search?q={quote(keyword)}"
            print(f"[goofish] 打开搜索页: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(random.randint(4000, 6000))

            body_head = (await page.inner_text("body"))[:400]
            if "登录" in body_head[:200] and "¥" not in body_head:
                print("[goofish] 页面命中登录提示,登录态可能失效。")
                dump_api_sample(platform, keyword, page.url, {"error": "login_required", "body_head": body_head})
                return 0

            items: list[dict] = []
            for page_num in range(1, max_pages + 1):
                for _ in range(4):
                    await page.mouse.wheel(0, random.randint(900, 1500))
                    await page.wait_for_timeout(random.randint(1000, 1800))
                rows = await page.evaluate(DOM_PARSE_JS)
                print(f"[goofish] 第 {page_num} 轮解析出 {len(rows)} 条商品。")
                if not rows and page_num == 1:
                    dump_api_sample(platform, keyword, page.url,
                                    {"error": "dom_parse_empty", "body_head": body_head})
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
                    # 闲鱼滚动加载(无限流),继续滚即可
                    await page.mouse.wheel(0, 2000)
                    await page.wait_for_timeout(2500)

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
            await browser.close()  # 仅断开连接
