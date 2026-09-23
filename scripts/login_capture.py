# -*- coding: utf-8 -*-
"""多平台登录态捕获器:打开登录页 -> 用户扫码 -> 自动存登录态到 state/<platform>_state.json。

用法(在项目根目录跑):
  python scripts/login_capture.py jd      # 京东
  python scripts/login_capture.py taobao  # 淘宝
  python scripts/login_capture.py goofish # 闲鱼(也可走 WebUI 登录状态页)

成功标志:轮询 cookies 出现平台关键 cookie,或页面跳离登录域。
保存后适配器经 resolve_login_state_file 自动取用,与旧 xianyu-monitor 的 state/acc1.json 完全隔离。
"""
import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

PLATFORMS = {
    "jd": {
        "login_url": "https://passport.jd.com/new/login.aspx",
        "login_host": "passport.jd.com",
        "cookie_marks": ["pt_key", "pt_pin"],
        "home": "https://www.jd.com/",
    },
    "taobao": {
        "login_url": "https://login.taobao.com/member/login.jhtml",
        "login_host": "login.taobao.com",
        "cookie_marks": ["unb", "tracknick", "dnk", "lgc"],
        "home": "https://www.taobao.com/",
    },
    "goofish": {
        "login_url": "https://www.goofish.com/",
        "login_host": "login.goofish.com",
        "cookie_marks": ["unb", "cookie2"],
        "home": "https://www.goofish.com/",
    },
    "1688": {
        "login_url": "https://login.1688.com/member/signin.htm",
        "login_host": "login.1688.com",
        "cookie_marks": ["cookie2", "unb"],
        "home": "https://www.1688.com/",
    },
}

WAIT_SECONDS = 180


async def main():
    platform = sys.argv[1] if len(sys.argv) > 1 else ""
    if platform not in PLATFORMS:
        sys.exit(f"用法: python scripts/login_capture.py {' / '.join(PLATFORMS)}")
    cfg = PLATFORMS[platform]

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # 扫码窗口弹在 2 号屏(右侧副屏),正常显示不含屏外参数
        browser = await p.chromium.launch(
            channel="chrome", headless=False,
            args=["--window-position=1920,0", "--window-size=1024,768"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 860},
            locale="zh-CN",
        )
        page = await context.new_page()
        await page.goto(cfg["login_url"], wait_until="domcontentloaded")
        print(f"[{platform}] 请在弹出的浏览器窗口扫码登录(限时 {WAIT_SECONDS} 秒)……")

        saved = False
        for i in range(WAIT_SECONDS // 3):
            await asyncio.sleep(3)
            cookies = await context.cookies()
            names = {c["name"] for c in cookies}
            hit = [m for m in cfg["cookie_marks"] if m in names]
            cur_url = page.url
            on_login_domain = any(d in cur_url for d in (cfg["login_host"], "passport", "login.taobao", "login.1688"))
            try:
                body_head = (await page.inner_text("body"))[:400]
            except Exception:
                body_head = ""
            login_prompt_visible = "请登录" in body_head
            # 硬条件:离开登录/passport 域 且 页面无登录提示 且 cookie 有用户标识(三者齐)
            if hit and not on_login_domain and not login_prompt_visible:
                await asyncio.sleep(3)
                state = await context.storage_state()
                os.makedirs("state", exist_ok=True)
                path = os.path.join("state", f"{platform}_state.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False)
                print(f"[{platform}] 登录态已保存: {path} (cookie关键项: {hit}, url: {cur_url[:70]})", flush=True)
                print(f"[{platform}] 窗口保持打开,登录完成后可手动关闭……", flush=True)
                saved = True
                break
            if i % 4 == 3:
                print(f"[{platform}] 等待中 {(i+1)*3}s | url={cur_url[:70]} | cookie关键项={hit or '无'} | 登录提示={'有' if login_prompt_visible else '无'}", flush=True)

        if not saved:
            print(f"[{platform}] 超时未捕获到登录态,请重跑。")
            await browser.close()
            return

        # 扫完不自动关,挂住等用户确认(确认无误后 Ctrl+C 结束)
        while True:
            await asyncio.sleep(60)


asyncio.run(main())
