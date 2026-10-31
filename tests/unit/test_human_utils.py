"""拟人工具测试：用 stub page 验证函数调用不抛错且行为合理。"""
import pytest

from src.platforms._human import human_click, human_move_to, human_pause, human_scroll


class StubLocator:
    """简化 locator：只暴露 bounding_box，支持 count() 与 click()。"""
    def __init__(self, box=None, page=None):
        self._box = box or {"x": 100, "y": 200, "width": 300, "height": 50}
        self._page = page

    async def bounding_box(self):
        return self._box

    async def count(self):
        return 1

    async def click(self):
        if self._page is not None:
            self._page.calls.append(("click",))


class StubMouse:
    """模拟 page.mouse 子对象（真实 Playwright API）。"""
    def __init__(self, page):
        self._page = page

    async def move(self, x, y, steps=1):
        self._page.calls.append(("move", x, y, steps))

    async def wheel(self, dx, dy):
        self._page.calls.append(("wheel", dx, dy))


class StubPage:
    """记录调用；不真正执行鼠标事件。"""
    def __init__(self):
        self.calls = []
        self.mouse = StubMouse(self)

    async def wait_for_timeout(self, ms):
        self.calls.append(("wait", ms))

    async def click(self, locator=None):
        self.calls.append(("click",))


def test_human_pause_random():
    page = StubPage()
    delays = []
    for _ in range(20):
        import asyncio
        asyncio.run(human_pause(page, 100, 200))
        d = [c for c in page.calls if c[0] == "wait"][-1][1]
        delays.append(d)
    assert all(100 <= d <= 200 for d in delays)
    assert len(set(delays)) > 1


def test_human_scroll_issues_wheels():
    page = StubPage()
    import asyncio
    asyncio.run(human_scroll(page, rounds=2))
    wheels = [c for c in page.calls if c[0] == "wheel"]
    assert len(wheels) >= 2


def test_human_move_to_moves_mouse():
    page = StubPage()
    loc = StubLocator()
    import asyncio
    asyncio.run(human_move_to(page, loc))
    moves = [c for c in page.calls if c[0] == "move"]
    assert len(moves) >= 2


def test_human_click_clicks_target():
    page = StubPage()
    loc = StubLocator(page=page)
    import asyncio
    asyncio.run(human_click(page, loc))
    assert ("click",) in page.calls
