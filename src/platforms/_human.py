"""统一拟人化行为：滚动 / 鼠标移动 / 点击 / 停留。

供各平台适配器调用，替代机械滚动与固定延迟，降低被风控识别为机器人的概率。
"""
from __future__ import annotations

import random


async def human_pause(page, min_ms: int = 800, max_ms: int = 2200) -> None:
    """随机停留一段时间(模仿人阅读/思考)。"""
    await page.wait_for_timeout(random.randint(min_ms, max_ms))


async def human_scroll(page, rounds: int = 1, *, direction: int = 1) -> None:
    """拟人滚动：每轮随机距离与速度,轮间随机暂停,20% 概率反向小幅回滚。

    Args:
        page: Playwright Page
        rounds: 滚动轮数
        direction: 1 向下, -1 向上
    """
    for _ in range(rounds):
        await page.mouse.wheel(0, direction * random.randint(900, 1600))
        await page.wait_for_timeout(random.randint(800, 2200))
        if random.random() < 0.2:
            await page.mouse.wheel(0, -random.randint(200, 500))
            await page.wait_for_timeout(random.randint(300, 900))


async def human_move_to(page, box_loc, x_ratio: float = 0.5) -> None:
    """多段折线+随机抖动的鼠标轨迹(拟人核心,迁移自 taobao.py)。"""
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


async def human_click(page, locator) -> None:
    """拟人点击:移动过去→随机停留→点击。"""
    await human_move_to(page, locator)
    await human_pause(page, 200, 700)
    await locator.click()
