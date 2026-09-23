# -*- coding: utf-8 -*-
"""慢慢买京东授权一次性脚本(CDP 专用 Chrome)。

背景(2026-09-19 实证):慢慢买查京东商品必须先 OAuth 授权
(checkJdAuth 返回 auth=false + authUrl),未授权则查询流程停摆。
本脚本:专用 Chrome 注入慢慢买登录 cookies → 查询 → 走 authUrl 授权
(京东已登录,一键确认)→ 回跳验证。

用法: python scripts/manmanbuy_jd_oauth.py
前置: 专用 Chrome 已起(CDP 9222)且京东已登录
"""
import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ITEM_URL = "https://item.jd.com/100012043978.html"


async def main():
    from playwright.async_api import async_playwright

    with open("state/manmanbuy_browser.json", encoding="utf-8") as f:
        state = json.load(f)
    cookies = state.get("cookies", [])
    print(f"[auth] 慢慢买 cookies {len(cookies)} 条待注入")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=8000)
        except Exception as e:
            print(f"[FAIL] CDP 连不上: {e.__class__.__name__};先起专用 Chrome(9222)")
            return
        ctx = browser.contexts[0]

        # 注入慢慢买 cookies(转 playwright add_cookies 格式)
        to_add = []
        for c in cookies:
            nc = {k: c[k] for k in ("name", "value", "domain", "path") if k in c}
            for k in ("expires", "httpOnly", "secure", "sameSite"):
                if k in c and c[k] is not None:
                    nc[k] = c[k]
            if "domain" not in nc:
                nc["url"] = "https://www.manmanbuy.com/"
            to_add.append(nc)
        try:
            await ctx.add_cookies(to_add)
            print(f"[auth] 已注入 {len(to_add)} 条 cookies 到专用 Chrome")
        except Exception as e:
            print(f"[FAIL] 注入 cookies 失败: {e}")
            return

        page = await ctx.new_page()

        # 直接打开授权入口
        auth_url = "https://apapia-config.manmanbuy.com/h5/jd_oauth_redirect.html?invokeScene=baoliao"
        print("[auth] 打开京东授权入口:", auth_url[:80])
        try:
            await page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print("[auth] 导航异常(可能在跳转链中):", e.__class__.__name__)
        await page.wait_for_timeout(4000)

        for hop in range(6):
            cur = page.url
            print(f"[hop{hop}] {cur[:120]}")
            if "jd.com" in cur and ("oauth" in cur or "authorize" in cur or "sso" in cur):
                # 京东授权确认页:找同意/授权按钮
                clicked = await page.evaluate("""() => {
                    const els = [...document.querySelectorAll('a,button,input,div,span')]
                        .filter(e => e.offsetParent);
                    for (const el of els) {
                        const t = (el.textContent || el.value || '').trim();
                        if (/^(同意|授权并登录|授权|确认授权|允许)$/.test(t)) { el.click(); return t; }
                    }
                    return null;
                }""")
                print("[auth] 授权按钮点击:", clicked)
            if "manmanbuy" in cur and hop > 0:
                print("[auth] 已回跳慢慢买,授权链走完")
                break
            # 通用:页面上若有明显授权入口则点
            await page.wait_for_timeout(3000)

        # 授权后验证:查询一次
        print("[verify] 授权后查询验证……")
        await page.goto("https://tool.manmanbuy.com/HistoryLowest.aspx",
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)
        check = await page.evaluate("""async () => {
            const r = await fetch('HistoryLowest.aspx?action=checkJdAuth', {credentials: 'include'});
            return await r.text();
        }""")
        print("[verify] checkJdAuth:", check[:200])

        await page.wait_for_timeout(1000)
        # 不关 tab,留给用户看授权结果(如需手动扫码/确认)
        print("[done] tab 保留在专用 Chrome 里,如页面要求确认请手动点一下。")


asyncio.run(main())
