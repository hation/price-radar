# -*- coding: utf-8 -*-
"""慢慢买京东授权二维码弹出(CDP 专用 Chrome)+ 打开图片供用户扫。

流程:注入慢慢买 cookies → 查询 → 弹京东授权层 → 截二维码图并全屏打开
→ 用户手机(慢慢买App)扫码授权 → 脚本验证 checkJdAuth。
授权标记落 CDP Chrome profile 持久 cookies,一劳永逸。

用法: python scripts/manmanbuy_auth_qrcode.py
"""
import asyncio
import json
import os
import random
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ITEM_URL = sys.argv[1] if len(sys.argv) > 1 else "https://item.jd.com/100012043978.html"
QR_SHOT = os.path.abspath("logs/manmanbuy_jd_auth_qr.png")


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=8000)
        except Exception as e:
            print(f"[FAIL] CDP 连不上: {e.__class__.__name__};先起专用 Chrome(9222)")
            return
        ctx = browser.contexts[0]

        # 慢慢买登录态若没注入过则补(幂等:json 不在就跳过,靠 profile 已有)
        if os.path.exists("state/manmanbuy_browser.json"):
            with open("state/manmanbuy_browser.json", encoding="utf-8") as f:
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
            try:
                await ctx.add_cookies(to_add)
                print(f"[auth] 注入/刷新 {len(to_add)} 条慢慢买 cookies")
            except Exception:
                print("[auth] cookies 已在 profile,跳过注入")

        page = await ctx.new_page()
        await page.goto("https://tool.manmanbuy.com/HistoryLowest.aspx",
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)
        await page.click("#historykey")
        for ch in ITEM_URL:
            await page.keyboard.type(ch, delay=random.randint(10, 40))
        await page.click("#searchHistory")
        await page.wait_for_timeout(6000)

        # 确认授权层出现
        has_layer = await page.evaluate(
            "() => !!document.querySelector('.jd-auth-popup canvas')")
        if not has_layer:
            print("[auth] 授权弹层未出现——可能已授权过!验证:")
        else:
            # 放大二维码 canvas(160 -> 480)再截,手机好扫
            await page.evaluate("""() => {
                const c = document.querySelector('.jd-auth-popup canvas');
                if (!c) return;
                const data = c.toDataURL('image/png');
                const big = document.createElement('canvas');
                big.width = 480; big.height = 480;
                const g = big.getContext('2d');
                g.imageSmoothingEnabled = false;
                g.drawImage(c, 0, 0, 480, 480);
                big.style.cssText = 'position:fixed;top:0;left:0;z-index:99999999;background:#fff';
                big.id = '__bigqr__';
                document.body.appendChild(big);
            }""")
            await page.wait_for_timeout(600)
            el = await page.query_selector("#__bigqr__")
            if el:
                os.makedirs(os.path.dirname(QR_SHOT), exist_ok=True)
                await el.screenshot(path=QR_SHOT)
                print(f"[QR] 二维码已截图: {QR_SHOT}")
                # 全屏打开二维码给用户扫
                subprocess.Popen(
                    ["cmd", "/c", "start", "", QR_SHOT],
                    shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
                print("[QR] 已用系统看图打开,请用手机【慢慢买App 或 微信】扫码授权!")

            # 等用户扫码授权(最多 300 秒),期间轮询 checkJdAuth
            print("[auth] 等待扫码授权……(最多 300s,完成请等脚本自动检测)")
            authorized = False
            for i in range(60):
                await page.wait_for_timeout(5000)
                state_txt = await page.evaluate("""async () => {
                    try {
                        const r = await fetch('HistoryLowest.aspx?action=checkJdAuth',
                                              {credentials: 'include'});
                        return await r.text();
                    } catch (e) { return 'ERR'; }
                }""")
                if '"auth":true' in state_txt or '"auth": true' in state_txt:
                    authorized = True
                    print(f"[auth] ✅ 授权成功!(t={i*5}s) {state_txt[:120]}")
                    break
                if i % 6 == 5:
                    print(f"[auth] …仍在等待 ({i*5}s)")
            if not authorized:
                print("[auth] 超时未授权。用户扫完码后可手动点页面'已完成授权'按钮,再重跑本脚本验证。")

        # 最终验证 + 若已授权直接跑一次完整查询看结果渲染
        final = await page.evaluate("""async () => {
            try {
                const r = await fetch('HistoryLowest.aspx?action=checkJdAuth',
                                      {credentials: 'include'});
                return await r.text();
            } catch (e) { return 'ERR'; }
        }""")
        print("[checkJdAuth]", final[:160])

        # tab 保留(用户可能还要看页面)
        print("[done] 查询 tab 保留在专用 Chrome。")


asyncio.run(main())
