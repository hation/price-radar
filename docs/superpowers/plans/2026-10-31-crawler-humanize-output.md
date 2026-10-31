# 爬虫拟人化 + 搜索结果输出目录重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 4 个平台爬虫增加统一拟人化行为（防风控），并新增 `--platform all` 一键多平台 + `output/关键词_时间戳/` 目录导出（分平台 CSV + 合并 CSV + JSONL）。

**Architecture:** 新增 `src/platforms/_human.py`（拟人滚动/鼠标移动/点击/停留）替换各平台机械行为；新增 `src/services/search_output_service.py`（目录构建与文件导出）；CLI `cmd_crawl` 支持 `--platform all` 遍历平台并在爬完后自动导出。复用现有 `query_result_records`、平台注册表、`build_result_filename`。

**Tech Stack:** Python 3.10+ / Playwright（page.mouse / locator）/ pytest / SQLite

**关键接口（实现前必读）：**
- 拟人原型（迁移自 `src/platforms/taobao.py:54-71` 的 `_human_move_to`）
- 平台函数：`get_scraper(platform)(task_config=dict, debug_limit=int) -> int`
- 平台遍历：`src/platforms/__init__.py` 的 `SCRAPER_REGISTRY.keys()`（= goofish/jd/taobao/1688）、`platform_display_name(key)`
- 结果读取：`query_result_records(filename, ai_recommended_only, keyword_recommended_only, sort_by, sort_order, page, limit, ...) -> (total, items)`（async），record 含 `商品信息`（dict）与 `platform` 字段
- 文件名：`build_result_filename(keyword)`（`src/infrastructure/persistence/storage_names.py`）
- CLI 入口：`pr.py` 的 `cmd_crawl(args)`（第 220 行起）

---

### Task 1: 拟人工具 _human.py

**Files:**
- Create: `src/platforms/_human.py`
- Test: `tests/unit/test_human_utils.py`

- [ ] **Step 1: Write the failing test**

```python
"""拟人工具测试：用 stub page 验证函数调用不抛错且行为合理。"""
import pytest

from src.platforms._human import human_click, human_move_to, human_pause, human_scroll


class StubLocator:
    """简化 locator：只暴露 bounding_box，支持 count()。"""
    def __init__(self, box=None):
        self._box = box or {"x": 100, "y": 200, "width": 300, "height": 50}

    async def bounding_box(self):
        return self._box

    async def count(self):
        return 1


class StubPage:
    """记录调用；不真正执行鼠标事件。"""
    def __init__(self):
        self.calls = []

    async def mouse_move(self, x, y, steps=1):
        self.calls.append(("move", x, y, steps))

    async def mouse_wheel(self, dx, dy):
        self.calls.append(("wheel", dx, dy))

    async def mouse_down(self):
        self.calls.append(("down",))

    async def mouse_up(self):
        self.calls.append(("up",))

    async def wait_for_timeout(self, ms):
        self.calls.append(("wait", ms))

    async def click(self, locator=None):
        self.calls.append(("click",))


def test_human_pause_random():
    page = StubPage()
    # 多次调用应产生不同延迟(随机性),且都在区间内
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
    assert len(moves) >= 2  # 起点 + 至少一段轨迹


def test_human_click_clicks_target():
    page = StubPage()
    loc = StubLocator()
    import asyncio
    asyncio.run(human_click(page, loc))
    assert ("click",) in page.calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_human_utils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.platforms._human'`

- [ ] **Step 3: Write minimal implementation**（新建文件，`import random`）

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_human_utils.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platforms/_human.py tests/unit/test_human_utils.py
git commit -m "feat(crawler): 统一拟人化工具 human_scroll/move/click/pause"
```

---

### Task 2: taobao.py 改用 _human.py

**Files:**
- Modify: `src/platforms/taobao.py`
- Test: `tests/unit/test_taobao_imports.py`

- [ ] **Step 1: Write the failing test**

```python
"""验证 taobao 模块能正常导入,且不再定义本地 _human_move_to(已迁移)。"""
import importlib
import src.platforms.taobao as tb


def test_taobao_imports_and_uses_human_module():
    assert not hasattr(tb, "_human_move_to")  # 本地函数已删除
    assert hasattr(tb, "scrape_taobao")


def test_human_utils_reexported():
    from src.platforms._human import human_move_to
    assert callable(human_move_to)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_taobao_imports.py -v`
Expected: FAIL（taobao 仍定义本地 `_human_move_to`）

- [ ] **Step 3: Modify taobao.py**

删除 taobao.py 中的 `_human_move_to` 函数定义（第 54-71 行），改为导入：

```python
from src.platforms._human import human_move_to, human_pause
```

将 taobao.py 中所有 `_human_move_to(...)` 调用改为 `human_move_to(...)`（grep 确认调用点）。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_taobao_imports.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platforms/taobao.py tests/unit/test_taobao_imports.py
git commit -m "refactor(taobao): 拟人移动改用 _human 模块"
```

---

### Task 3: goofish_cdp.py 集成拟人行为

**Files:**
- Modify: `src/platforms/goofish_cdp.py`

爬虫依赖真实浏览器，单元测试成本高，本任务以"导入验证 + 端到端验证"为主（Task 8 做真机验证）。

- [ ] **Step 1: 修改滚动与点击**

在 `goofish_cdp.py` 顶部 import 后加入：

```python
from src.platforms._human import human_click, human_scroll
```

将采集循环中的机械滚动（第 80-82 行）：

```python
                for _ in range(4):
                    await page.mouse.wheel(0, random.randint(900, 1500))
                    await page.wait_for_timeout(random.randint(1000, 1800))
```

替换为：

```python
                await human_scroll(page, rounds=4)
```

将翻页时的页码/箭头点击（第 109-121 行）中的 `await target.click()` 与 `await arrow.click()` 替换为拟人点击：

```python
                    if await target.count():
                        await human_click(page, target)
                    else:
                        arrow = page.locator(
                            '[class*="search-pagination-arrow-container"]'
                        ).nth(1)
                        if await arrow.count():
                            await human_click(page, arrow)
                        else:
                            break
```

- [ ] **Step 2: 语法与导入验证**

Run: `python3 -c "from src.platforms.goofish_cdp import scrape_goofish; print('ok')"`
Expected: 输出 ok

- [ ] **Step 3: 现有测试回归**

Run: `python3 -m pytest tests/unit -q 2>&1 | tail -3`
Expected: 全部通过（无单元测试直接覆盖爬虫,但确保无 import 破坏）

- [ ] **Step 4: Commit**

```bash
git add src/platforms/goofish_cdp.py
git commit -m "feat(goofish): 滚动与翻页点击改用拟人行为"
```

---

### Task 4: jd.py 集成拟人行为

**Files:**
- Modify: `src/platforms/jd.py`

- [ ] **Step 1: 修改滚动与翻页等待**

顶部 import 后加入：

```python
from src.platforms._human import human_pause, human_scroll
```

将采集循环的机械滚动（第 154-156 行）：

```python
                for _ in range(5):
                    await result_page.mouse.wheel(0, random.randint(900, 1600))
                    await result_page.wait_for_timeout(random.randint(900, 1800))
```

替换为：

```python
                await human_scroll(result_page, rounds=5)
```

翻页点击（第 188-191 行）在点击前加入拟人停留：

```python
                        try:
                            await human_pause(result_page, 400, 1200)
                            await nxt.click(timeout=5000)
                        except Exception:
```

- [ ] **Step 2: 语法与导入验证**

Run: `python3 -c "from src.platforms.jd import scrape_jd; print('ok')"`
Expected: 输出 ok

- [ ] **Step 3: 回归**

Run: `python3 -m pytest tests/unit -q 2>&1 | tail -3`
Expected: 全部通过

- [ ] **Step 4: Commit**

```bash
git add src/platforms/jd.py
git commit -m "feat(jd): 滚动与翻页点击改用拟人行为"
```

---

### Task 5: ali1688.py 集成拟人行为

**Files:**
- Modify: `src/platforms/ali1688.py`

- [ ] **Step 1: 修改滚动与翻页等待**

顶部 import 后加入：

```python
from src.platforms._human import human_pause, human_scroll
```

将采集循环的机械滚动（第 115-118 行附近）：

```python
                # 轻滚动促懒加载(1688 风控敏感,只滚几轮不深翻)
                for _ in range(3):
                    await page.mouse.wheel(0, random.randint(1200, 1600))
                    await page.wait_for_timeout(random.randint(1500, 2500))
```

替换为：

```python
                # 拟人滚动促懒加载(1688 风控敏感)
                await human_scroll(page, rounds=3)
```

翻页 goto 前（第 108-112 行）加入拟人停留：

```python
                if page_num > 1:
                    await human_pause(page, 1500, 3000)
                    page_url = f"{base_url}&beginPage={page_num}"
                    print(f"[1688] 翻页 -> beginPage={page_num}")
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
```

- [ ] **Step 2: 语法与导入验证**

Run: `python3 -c "from src.platforms.ali1688 import scrape_ali1688; print('ok')"`
Expected: 输出 ok

- [ ] **Step 3: 回归**

Run: `python3 -m pytest tests/unit -q 2>&1 | tail -3`
Expected: 全部通过

- [ ] **Step 4: Commit**

```bash
git add src/platforms/ali1688.py
git commit -m "feat(1688): 滚动与翻页改用拟人行为"
```

---

### Task 6: 导出服务 search_output_service.py

**Files:**
- Create: `src/services/search_output_service.py`
- Test: `tests/unit/test_search_output_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""导出服务测试：目录构建 + 分平台/合并 CSV + JSONL。"""
import json
import os

from src.services.search_output_service import build_search_output_dir, export_search_results

RECORDS = {
    "goofish": [
        {"商品信息": {"商品标题": "闲鱼货", "当前售价": "¥100", "商品链接": "http://x", "商品ID": "1",
                     "卖家昵称": "卖家A", "发货地区": "广东", "发布时间": "2026-10-31"},
         "爬取时间": "2026-10-31T10:00:00", "platform": "goofish"},
    ],
    "jd": [
        {"商品信息": {"商品标题": "京东货", "当前售价": "¥200", "商品链接": "http://j", "商品ID": "2",
                     "卖家昵称": "", "发货地区": "", "发布时间": ""},
         "爬取时间": "2026-10-31T10:00:00", "platform": "jd"},
    ],
}


def test_build_search_output_dir_format(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.search_output_service.datetime",
        type("DT", (), {"now": lambda: type("N", (), {"strftime": lambda self, f: "202610311030"})()}),
    )
    out = build_search_output_dir("希捷")
    assert out == os.path.join("output", "希捷_202610311030")


def test_export_search_results_writes_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out_dir = export_search_results("希捷", RECORDS)
    assert os.path.isdir(out_dir)
    files = os.listdir(out_dir)
    assert "希捷_goofish.csv" in files
    assert "希捷_jd.csv" in files
    assert "希捷_merged.csv" in files
    assert "希捷_merged.jsonl" in files

    # 合并 CSV 含 platform 列
    with open(os.path.join(out_dir, "希捷_merged.csv"), encoding="utf-8-sig") as f:
        head = f.readline()
    assert "平台" in head or "platform" in head

    # JSONL 每行一条,含 platform
    with open(os.path.join(out_dir, "希捷_merged.jsonl"), encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2
    assert {line["platform"] for line in lines} == {"goofish", "jd"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_search_output_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.search_output_service'`

- [ ] **Step 3: Write minimal implementation**

```python
"""搜索结果导出服务：output/关键词_时间戳/ 目录下写分平台 CSV、合并 CSV 与 JSONL。"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime

from src.infrastructure.persistence.storage_names import RESULT_FILE_SUFFIX

COLUMNS = [
    "标题", "价格", "链接", "商品ID", "卖家", "地区", "发布时间", "爬取时间", "platform",
]
_ILLEGAL_DIR_CHARS = re.compile(r"[/\\:*?\"<>|\s]+")


def _sanitize_dir_part(keyword: str) -> str:
    cleaned = _ILLEGAL_DIR_CHARS.sub("_", str(keyword or ""))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "task"


def build_search_output_dir(keyword: str, now: datetime | None = None) -> str:
    """生成 output/{关键词}_{yyyymmddhhmm} 目录路径。"""
    ts = (now or datetime.now()).strftime("%Y%m%d%H%M")
    return os.path.join("output", f"{_sanitize_dir_part(keyword)}_{ts}")


def _extract_row(record: dict) -> dict:
    item = record.get("商品信息", {}) or {}
    return {
        "标题": item.get("商品标题", ""),
        "价格": item.get("当前售价", ""),
        "链接": item.get("商品链接", ""),
        "商品ID": item.get("商品ID", ""),
        "卖家": item.get("卖家昵称", ""),
        "地区": item.get("发货地区", ""),
        "发布时间": item.get("发布时间", ""),
        "爬取时间": record.get("爬取时间", ""),
        "platform": record.get("platform", ""),
    }


def export_search_results(keyword: str, items_by_platform: dict) -> str:
    """导出搜索结果到 output 目录,返回目录路径。

    items_by_platform: {platform: [record, ...]}，record 含 商品信息/爬取时间/platform。
    写入:
      - {关键词}_{platform}.csv (分平台, 无 platform 列)
      - {关键词}_merged.csv (合并, 含 platform 列, UTF-8-BOM)
      - {关键词}_merged.jsonl (合并, 每行一条含 platform)
    """
    out_dir = build_search_output_dir(keyword)
    os.makedirs(out_dir, exist_ok=True)
    merged_rows = []
    for platform, records in items_by_platform.items():
        rows = [_extract_row(r) for r in records]
        if not rows:
            continue
        merged_rows.extend(rows)
        with open(
            os.path.join(out_dir, f"{_sanitize_dir_part(keyword)}_{platform}.csv"),
            "w", newline="", encoding="utf-8-sig",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS[:-1])
            writer.writeheader()
            writer.writerows(rows)
    if merged_rows:
        base = _sanitize_dir_part(keyword)
        with open(
            os.path.join(out_dir, f"{base}_merged.csv"),
            "w", newline="", encoding="utf-8-sig",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(merged_rows)
        with open(
            os.path.join(out_dir, f"{base}_merged.jsonl"),
            "w", encoding="utf-8",
        ) as f:
            for row in merged_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out_dir
```

注意：`RESULT_FILE_SUFFIX` 导入未使用，可省略该 import（保持文件无未用导入）。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_search_output_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/search_output_service.py tests/unit/test_search_output_service.py
git commit -m "feat(export): 搜索输出服务(分平台CSV+合并CSV+JSONL)"
```

---

### Task 7: CLI --platform all + 自动导出

**Files:**
- Modify: `pr.py`
- Test: `tests/unit/test_pr_cli.py`（追加）

- [ ] **Step 1: Write the failing test**

```python
"""--platform all: 遍历全部平台并调用导出;单平台也导出。"""
from pr import cmd_crawl

def _args(platform="all", crawl="希捷", pages=1, mode="keyword", json=False):
    return type("Args", (), dict(platform=platform, crawl=crawl, pages=pages,
                                 mode=mode, json=json))()


def test_crawl_all_iterates_platforms_and_exports(monkeypatch, capsys):
    captured = {}

    async def fake_scraper(task_config=None, debug_limit=0):
        captured.setdefault("platforms", []).append(task_config["platform"])
        return 1

    monkeypatch.setattr("src.platforms.get_scraper", lambda plat: fake_scraper)
    monkeypatch.setattr("pr._check_platform_ready", lambda plat: True)

    async def fake_query(filename, **kwargs):
        return 4, [
            {"商品信息": {"商品标题": "货", "当前售价": "¥1", "商品链接": f"http://{i}",
                         "商品ID": str(i)}, "爬取时间": "2026-10-31T00:00:00",
             "platform": "goofish"}
            for i in range(4)
        ]

    monkeypatch.setattr("src.services.result_storage_service.query_result_records", fake_query)
    exported = {}
    monkeypatch.setattr(
        "pr.export_search_results",
        lambda kw, items_by_platform: exported.setdefault("x", (kw, items_by_platform)) or "/tmp/x",
    )

    cmd_crawl(_args())
    # 遍历了全部平台(4 个)
    assert captured["platforms"] == ["goofish", "jd", "taobao", "1688"]
    # 调用了导出
    assert "x" in exported
    kw, by_platform = exported["x"]
    assert kw == "希捷"
    assert "goofish" in by_platform
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_pr_cli.py -k crawl_all -v`
Expected: FAIL（cmd_crawl 尚不支持 all,`normalize_platform_key("all")` 回落闲鱼）

- [ ] **Step 3: Modify cmd_crawl（pr.py 第 220 行起）**

将 `cmd_crawl` 替换为：

```python
def cmd_crawl(args):
    """按关键词爬取并落库；--platform all 遍历全部平台；爬完自动导出到 output/。"""
    from src.infrastructure.persistence.storage_names import build_result_filename
    from src.platforms import (
        SCRAPER_REGISTRY,
        get_scraper,
        normalize_platform_key,
        platform_display_name,
    )
    from src.services.result_storage_service import query_result_records
    from src.services.search_output_service import export_search_results
    from src.services.task_generation_runner import build_criteria_filename

    platforms = list(SCRAPER_REGISTRY.keys())
    if args.platform != "all":
        platforms = [normalize_platform_key(args.platform)]
        if not _check_platform_ready(platforms[0]):
            return

    if args.mode == "ai":
        criteria = build_criteria_filename(args.crawl)
        if not os.path.exists(criteria):
            print(f"关键词 '{args.crawl}' 尚无分析标准文件: {criteria}")
            print("请先在 Web UI 用 AI 生成任务，或改用 --mode keyword 纯采集。")
            return
        print(f"[info] 将采用分析标准: {criteria}（当前采集管线为纯抓取）")

    failed = []
    for platform in platforms:
        if platform == "goofish" and not _check_platform_ready(platform):
            failed.append((platform, "闲鱼 CDP 未就绪"))
            continue
        task_config = {
            "task_name": args.crawl,
            "keyword": args.crawl,
            "platform": platform,
            "max_pages": args.pages,
            "decision_mode": args.mode,
        }
        print(f"开始爬取: {args.crawl} [{platform_display_name(platform)}] {args.pages} 页")
        count = asyncio.run(get_scraper(platform)(task_config=task_config, debug_limit=0))
        print(f"[{platform}] 新增 {count} 个商品")
    for platform, reason in failed:
        print(f"[{platform}] 跳过: {reason}")

    # 读回该关键词全部平台结果,按平台分组
    total, items = asyncio.run(
        query_result_records(
            build_result_filename(args.crawl),
            ai_recommended_only=False,
            keyword_recommended_only=False,
            sort_by="crawl_time",
            sort_order="desc",
            page=1,
            limit=3000,
        )
    )
    items_by_platform: dict[str, list] = {}
    for record in items:
        plat = record.get("platform") or "未知"
        items_by_platform.setdefault(plat, []).append(record)

    if args.json and items:
        _print_json(items)
        return

    if items_by_platform:
        out_dir = export_search_results(args.crawl, items_by_platform)
        print(f"已导出到: {out_dir}")
        print(f"  分平台 CSV + 合并 CSV({out_dir}/<关键词>_merged.csv) + JSONL")
    else:
        print("本次没有可导出的结果。")
```

同时修改 `pr.py` 的 `cmd_crawl` 顶部 import 区，确保 `SCRAPER_REGISTRY` 可从 `src.platforms` 导入（在函数内 import 即可）。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_pr_cli.py -q`
Expected: PASS（含新增 crawl_all 测试）

- [ ] **Step 5: Commit**

```bash
git add pr.py tests/unit/test_pr_cli.py
git commit -m "feat(cli): --platform all 一键多平台并自动导出 output/"
```

---

### Task 8: 端到端手动验证

**Files:**
- 无代码改动（验证清单）

- [ ] **Step 1: 全量单元测试**

Run: `python3 -m pytest tests/unit -q`
Expected: 全部通过

- [ ] **Step 2: 单平台验证（闲鱼,CDP 已就绪）**

Run: `python3 pr.py --crawl "希捷" --pages 2 --platform goofish`
Expected: 爬取 2 页,打印输出目录;检查 `output/希捷_20261031xxxx/` 下有 3 类文件

- [ ] **Step 3: 多平台验证（--platform all）**

Run: `python3 pr.py --crawl "希捷" --pages 2 --platform all`
Expected: 遍历 4 平台,无登录态的平台打印跳过原因;有结果则导出

- [ ] **Step 4: 检查导出文件**

Run: `ls output/希捷_*/` 与 `head -3 output/希捷_*/希捷_merged.csv`
Expected: 分平台 CSV + merged CSV(含 platform 列) + JSONL 存在

- [ ] **Step 5: 收尾提交（如需）**

如有验证期修复则提交;否则跳过。

---

## Self-Review

**1. Spec coverage（对照 docs/superpowers/specs/2026-10-31-crawler-humanize-output-design.md）：**
- 拟人工具 _human.py（滚动/移动/点击/停留）：Task 1 ✓
- 平台集成（goofish/jd/1688/taobao）：Task 2-5 ✓
- 导出服务（分平台 CSV + 合并 CSV + JSONL + 目录名）：Task 6 ✓
- CLI --platform all + 自动导出：Task 7 ✓
- 入库说明：spec 已陈述,无需代码 ✓
- 测试（_human/export/CLI）：Task 1/6/7 测试,Task 2 导入测试 ✓

**2. Placeholder scan：** 无 TBD/TODO;所有代码步骤完整。✓

**3. Type consistency：**
- `human_scroll(page, rounds=..., direction=...)` / `human_move_to(page, box_loc, x_ratio=...)` / `human_click(page, locator)` / `human_pause(page, min_ms, max_ms)` 在 Task 1 定义,Task 2-5 使用一致 ✓
- `export_search_results(keyword, items_by_platform)` / `build_search_output_dir(keyword, now=None)` 在 Task 6 定义,Task 7 调用一致 ✓
- `SCRAPER_REGISTRY.keys()` 返回 goofish/jd/taobao/1688 与 `--platform all` 遍历一致 ✓
- CSV 列名 `COLUMNS` 与 `_extract_row` 输出一致 ✓
