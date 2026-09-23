# -*- coding: utf-8 -*-
"""持久化 profile 登录器(对付淘宝级风控的正路)。

与 login_capture.py 的区别:用 launch_persistent_context(user_data_dir),
浏览器指纹+cookie+localStorage 全部持久化在 state/<platform>_profile/,
风控视为"同一台真浏览器"。采集器平移用同一 profile 即免登录。

用法: python scripts/login_capture_persistent.py taobao
流程: 开窗口 -> 用户登录 -> 登录成功后脚本自动检测 -> 存盘标志 -> 手动关窗
"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

PLATFORMS = {
    "taobao": {
        "home": "https://www.taobao.com/",
        "login_mark": "请登录",
        "user_mark": "我的淘宝",
    },
    "jd": {
        "home": "https://www.jd.com/",
        "login_mark": "你好，请登录",
        "user_mark": "我的京东",
    },
    "1688": {
        "home": "https://www.1688.com/",
        "login_mark": "请登录",
        "user_mark": "我的阿里",
    },
    "goofish": {
        "home": "https://www.goofish.com/",
        "login_mark": "登录",
        "user_mark": "消息",
    },
}


async def main():
    platform = sys.argv[1] if len(sys.argv) > 1 else ""
    if platform not in PLATFORMS:
        sys.exit(f"用法: python scripts/login_capture_persistent.py {' / '.join(PLATFORMS)}")
    cfg = PLATFORMS[platform]
    profile_dir = os.path.join("state", f"{platform}_profile")
    os.makedirs(profile_dir, exist_ok=True)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            profile_dir,
            channel="chrome",
            headless=False,
            args=["--window-position=1920,0", "--window-size=1024,768"],
            viewport={"width": 1024, "height": 768},
            locale="zh-CN",
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(cfg["home"], wait_until="domcontentloaded", timeout=45000)
        print(f"[{platform}] 已打开 {cfg['home']}(持久 profile: {profile_dir})")
        print(f"[{platform}] 请在窗口里手动完成登录(扫码/账密均可)。登录成功的标志:页面出现'{cfg['user_mark']}'且'{cfg['login_mark']}'消失。")
        print(f"[{platform}] 每次状态变化都会打印,完成后发消息给 Claude 关窗。", flush=True)

        logged = False
        for i in range(600):  # 挂 30 分钟
            await asyncio.sleep(5)
            try:
                body = (await page.inner_text("body"))[:600]
                url = page.url
            except Exception:
                continue
            has_user = cfg["user_mark"] in body
            has_login = cfg["login_mark"] in body
            if i % 6 == 0:
                print(f"[{platform}] url={url[:70]} 已登录标志={'有' if has_user else '无'} 登录提示={'有' if has_login else '无'}", flush=True)
            if has_user and not has_login and not logged:
                logged = True
                print(f"\n[{platform}] ✅ 登录成功确认!(profile 已自动持久化,无需另存)", flush=True)
                print(f"[{platform}] 窗口保持打开,登录完成后可手动关闭……", flush=True)
                break

        if logged:
            while True:
                await asyncio.sleep(60)  # 挂住等 Claude kill
        else:
            print(f"[{platform}] 30 分钟未检测到登录,退出。")
            await context.close()


asyncio.run(main())
