# -*- coding: utf-8 -*-
"""慢慢买会话捕获(正式工具):登录态落盘 + api.ashx 凭据提取 + 历史价响应。

- state/manmanbuy_browser.json  浏览器登录态(存了以后免扫码)
- state/manmanbuy_auth.json     api.ashx 的 Authorization/Cookie(供 manmanbuy_client.py)
- logs/platform_samples/manmanbuy_*.json  历史价响应样本

用法: python scripts/capture_manmanbuy_auth.py [商品URL]
"""
import asyncio
import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

ITEM_URL = sys.argv[1] if len(sys.argv) > 1 else "https://item.jd.com/100012043978.html"
BROWSER_STATE = os.path.join("state", "manmanbuy_browser.json")
AUTH_STATE = os.path.join("state", "manmanbuy_auth.json")


async def fill_and_query(page, url):
    await page.evaluate("""(url) => {
        const inp = document.querySelector('#historykey');
        if (inp) { inp.value = url; inp.dispatchEvent(new Event('input', {bubbles: true})); }
    }""", url)
    await page.evaluate("""() => {
        const btn = document.querySelector('#searchHistory');
        if (btn) btn.click();
    }""")


async def main():
    from playwright.async_api import async_playwright

    api_hits = []  # api.ashx 请求(headers+post_data)
    api_responses = []  # api.ashx 响应体

    async with async_playwright() as p:
        # 扫码窗口默认主屏;双屏用户想弹副屏可改 --window-position=X,0
        browser = await p.chromium.launch(
            channel="chrome", headless=False,
            args=["--window-size=1024,768"],
        )
        kwargs = {
            "user_agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
            "viewport": {"width": 1280, "height": 860},
            "locale": "zh-CN",
        }
        if os.path.exists(BROWSER_STATE):
            kwargs["storage_state"] = BROWSER_STATE
            print("[state] 已加载历史登录态(免扫码)。")
        context = await browser.new_context(**kwargs)
        page = await context.new_page()

        def on_request(request):
            if "api.ashx" in request.url:
                api_hits.append({"url": request.url[:150],
                                 "headers": dict(request.headers),
                                 "post_data": request.post_data or ""})

        def on_response(resp):
            if "api.ashx" in resp.url:
                try:
                    api_responses.append({"url": resp.url[:150], "body": resp.text()})
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        await page.goto("https://tool.manmanbuy.com/HistoryLowest.aspx",
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)

        # 登录检查:页面顶部含"请登录"则等扫码
        body = await page.inner_text("body")
        if "请登录" in body[:300]:
            print("=" * 60)
            print("[登录] 请在弹出的窗口【微信扫码】登录(150 秒内)……")
            print("=" * 60)
            logged = False
            for i in range(50):
                await page.wait_for_timeout(3000)
                txt = await page.inner_text("body")
                if "请登录" not in txt[:300]:
                    logged = True
                    print(f"[登录] 登录成功(第 {(i+1)*3} 秒)")
                    break
                if i % 5 == 4:
                    print(f"[登录] 等待扫码……({(i+1)*3}s)")
            if not logged:
                print("[登录] 超时,退出。")
                await browser.close()
                return
            os.makedirs("state", exist_ok=True)
            state = await context.storage_state()
            with open(BROWSER_STATE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
            print(f"[save] 浏览器登录态已存 {BROWSER_STATE}(以后免扫码)")
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
        else:
            print("[login] 已是登录态。")

        # 发起查询
        await fill_and_query(page, ITEM_URL)
        print(f"[query] 已发起查询: {ITEM_URL}")

        # 等待 api.ashx(30 秒)
        for _ in range(30):
            await page.wait_for_timeout(1000)
            if api_hits:
                break

        if api_hits:
            os.makedirs("state", exist_ok=True)
            os.makedirs(os.path.join("logs", "platform_samples"), exist_ok=True)
            h = api_hits[0]["headers"]
            auth = h.get("authorization", "")
            cookie = h.get("cookie", "")
            with open(AUTH_STATE, "w", encoding="utf-8") as f:
                json.dump({"authorization": auth, "cookie": cookie,
                           "captured_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
            print(f"[save] api 凭据已存 {AUTH_STATE}")
            print(f"       Authorization: {auth[:50]}...")
            if api_responses:
                sample_path = os.path.join("logs", "platform_samples",
                                           f"manmanbuy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                with open(sample_path, "w", encoding="utf-8") as f:
                    json.dump(api_responses, f, ensure_ascii=False, indent=2)
                print(f"[save] 响应样本已存 {sample_path}")
                try:
                    payload = json.loads(api_responses[0]["body"])
                    print(f"[result] code={payload.get('code')} msg={payload.get('msg','')!r}")
                    data = payload.get("data") or {}
                    if payload.get("code") == 0 and data:
                        print(f"[result] {data.get('siteName')} {data.get('spName','')[:40]} "
                              f"现价 {data.get('currentPrice')}")
                except Exception as e:
                    print(f"[result] 响应解析失败: {e}")
        else:
            # 深挖:dump localStorage/cookies 找 token 来源 + 页面状态
            print("[miss] 未捕获 api.ashx。dump 诊断信息:")
            ls = await page.evaluate("""() => {
                const out = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    out[k] = (localStorage.getItem(k) || '').slice(0, 120);
                }
                return out;
            }""")
            print("[localStorage]", json.dumps(ls, ensure_ascii=False)[:600])
            cookies = await context.cookies()
            interesting = [c["name"] for c in cookies if any(
                s in c["name"].lower() for s in ("auth", "token", "ticket", "user", "member"))]
            print("[cookies 关键项]", interesting)
            tip = await page.evaluate("""() => {
                const els = [...document.querySelectorAll('div,span,p,b')].filter(e => e.offsetParent);
                return els.map(e => (e.textContent||'').trim())
                    .filter(s => s && s.length < 100 && /授权|京东|绑定|失败|错|微信/.test(s)).slice(0, 8);
            }""")
            print("[页面提示]", tip)

        await asyncio.sleep(2)
        await browser.close()


asyncio.run(main())
