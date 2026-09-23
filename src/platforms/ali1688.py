"""1688 平台适配器(CDP 接管版,2026-09-19 实测定型)。

路线:专用 CDP Chrome(9222,阿里通行证随淘宝账号自动登录)→ 搜索页 DOM 解析。
- 登录:无需单独登录,专用 Chrome 里淘宝账号通行证直接继承(login.1688.com 会
  自动跳 work.1688.com 工作台即已登录)
- 滑块:**风控敏感,连续自动化查询必触发**(2026-09-19 实测弹爬虫拦截)。
  纪律:人工过一次滑块后养 cookie,采集频率每天最多一次;脚本绝不连续导航
- 数据:搜索页 a.search-offer-item 卡片(offerId 在 href 或内部 offerIds 参数);
  1688 是批发市场,整机品类少、配件多(比价引擎配件过滤会兜住)
- 解析输出统一中文键,与底座 parsers 对齐
"""
from __future__ import annotations

import os
import random
from datetime import datetime
from urllib.parse import quote

from src.platforms._web import CDP_START_HINT, dump_api_sample, persist_platform_items

CDP_ENDPOINT = os.getenv("ALI1688_CDP_ENDPOINT", "http://127.0.0.1:9222")

# 卡片解析(2026-09-19 实测定型:43 条全字段成功)
DOM_PARSE_JS = """() => {
    const out = [];
    const seen = new Set();
    for (const card of document.querySelectorAll('a.search-offer-item')) {
        let href = card.getAttribute('href') || '';
        let m = href.match(/offer\\/(\\d{6,})\\.html/);
        if (!m) {
            const inner = card.querySelector('a[href*="offerIds"]');
            if (inner) { const im = (inner.getAttribute('href')||'').match(/offerIds=(\\d{6,})/); if (im) { m = im; } }
        }
        if (!m) continue;
        const offerId = m[1];
        if (seen.has(offerId)) continue;
        seen.add(offerId);
        const text = (card.innerText || '').replace(/\\n+/g, ' ').trim();
        let price = '';
        const pEl = card.querySelector('[class*="price"]');
        if (pEl) {
            const pm = (pEl.textContent || '').replace(/\\s+/g, '').match(/\\d+(?:\\.\\d+)?/);
            if (pm) price = pm[0];
        }
        if (!price) {
            const pm = text.match(/¥\\s*([\\d,]+\\.?\\d*)/);
            if (pm) price = pm[1].replace(/,/g, '');
        }
        if (!price) continue;
        let title = text.slice(0, text.indexOf('¥')).trim();
        let seller = '';
        const sm = text.match(/([\\u4e00-\\u9fa5A-Za-z0-9]+(?:公司|厂|经营部|商行|工作室))/g);
        if (sm) seller = sm[sm.length - 1];
        const qm = text.match(/(\\d+\\+?)件/);
        const qty = qm ? qm[1] : '';
        const link = href.startsWith('http') ? href
            : 'https://detail.1688.com/offer/' + offerId + '.html';
        out.push({offerId, title: title.slice(0, 120), price, seller, qty, link});
    }
    return out;
}"""


async def scrape_ali1688(task_config: dict, debug_limit: int = 0):
    """1688 搜索采集(CDP 接管):返回本次落库的新商品数。"""
    platform = "1688"
    keyword = task_config.get("keyword", "")
    task_name = task_config.get("task_name", "Untitled Task")
    max_pages = int(task_config.get("max_pages", 1) or 1)
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_ENDPOINT, timeout=8000)
        except Exception as e:
            print(f"[1688] CDP 连接失败({CDP_ENDPOINT}): {e.__class__.__name__}")
            print("[1688] 请先启动专用 Chrome(淘宝账号通行证自动登录 1688):")
            print(f"  {CDP_START_HINT}")
            return 0
        context = browser.contexts[0]
        print(f"[1688] CDP 已接管 {CDP_ENDPOINT}")
        page = await context.new_page()

        try:
            url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={quote(keyword)}"
            print(f"[1688] 打开搜索页: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(random.randint(6000, 9000))

            body_head = (await page.inner_text("body"))[:400]
            if "请登录" in body_head or "验证" in body_head or "拦截" in body_head:
                print("[1688] 命中登录/风控拦截,本轮放弃(请人工过滑块养 cookie,明日再采)。")
                dump_api_sample(platform, keyword, page.url,
                                {"error": "blocked_or_login", "body_head": body_head})
                return 0

            items: list[dict] = []
            for page_num in range(1, max_pages + 1):
                # 轻滚动促懒加载(1688 风控敏感,只滚两轮不深翻)
                for _ in range(2):
                    await page.mouse.wheel(0, random.randint(1100, 1500))
                    await page.wait_for_timeout(random.randint(1500, 2500))
                rows = await page.evaluate(DOM_PARSE_JS)
                print(f"[1688] 第 {page_num} 轮解析出 {len(rows)} 条商品。")
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
                            "“想要”人数": r.get("qty", "") or "NaN",
                            "商品标签": [],
                            "发货地区": "",
                            "卖家昵称": r.get("seller", ""),
                            "商品链接": r["link"],
                            "发布时间": "未知时间",
                            "商品ID": r["offerId"],
                        }
                    )
                if page_num < max_pages:
                    await page.wait_for_timeout(random.randint(3000, 5000))

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
