# CLI 爬取工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `pr.py` 命令行入口，支持按关键词爬取、任务管理、历史走势查询、结构化输出，脱离 Web UI 使用。

**Architecture:** 根目录新建 `pr.py` 单文件 CLI（argparse 单命令多参数），直接复用 src 服务层（平台注册表 `get_scraper`、`SqliteTaskRepository`、`price_history_service`、`result_storage_service`），不依赖 Web 服务进程，不新增第三方依赖。`spider_v2.py` 职责不动。

**Tech Stack:** Python 3.10+ / argparse（标准库）/ asyncio / pytest（测试）/ SQLite（任务与结果存储）

**关键接口（实现前必读）：**
- 平台函数：`get_scraper(platform)(task_config=dict, debug_limit=int) -> int`，返回本次新增商品数；内部已调用 `persist_platform_items` 落库（价格快照 + result_items）。定义于 `src/platforms/__init__.py`
- 平台规范化：`normalize_platform_key(value) -> str`、`platform_display_name(key) -> str`
- 任务仓储：`SqliteTaskRepository` 的 `find_all() / find_by_id(id) / save(task) / delete(id)` 均为 async。`src/infrastructure/persistence/sqlite_task_repository.py`
- 任务模型：`src/domain/models/task.py` 的 `Task`，必填字段见 Task 1
- 走势：`load_price_snapshots(keyword) -> list[dict]`（同步）、`build_price_history_insights(keyword, window_days=30) -> dict`（同步，含 `market_summary/history_summary/daily_trend/latest_snapshot_at`）。`src/services/price_history_service.py`
- 结果读取：`query_result_records(filename, sort_by, sort_order, page, limit, ...) -> (total, items)`（async），items 元素为 record dict，商品字段在 `record["商品信息"]`，AI 推荐在 `record["ai_analysis"]["is_recommended"]`。`src/services/result_storage_service.py`
- criteria 路径：`build_criteria_filename(keyword)`（`src/services/task_generation_runner.py`）
- 闲鱼 CDP 探测：`http://127.0.0.1:9222/json/version`；CDP profile 目录：`src/platforms/_web.py` 的 `CDP_PROFILE_DIR`

---

### Task 1: pr.py 骨架（argparse + main 路由）

**Files:**
- Create: `pr.py`
- Test: `tests/unit/test_pr_cli.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from pr import _parse_args, main

def test_parse_crawl():
    args = _parse_args(["--crawl", "三星/SK 64G5600", "--pages", "2"])
    assert args.crawl == "三星/SK 64G5600"
    assert args.pages == 2
    assert args.platform == "goofish"
    assert args.mode == "keyword"

def test_parse_trend():
    args = _parse_args(["--trend", "三星/SK 64G5600", "--json"])
    assert args.trend == "三星/SK 64G5600"
    assert args.json is True

def test_parse_requires_one_action():
    with pytest.raises(SystemExit):
        _parse_args([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pr_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pr'`

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""price-radar 命令行入口：按关键词爬取 / 任务管理 / 历史走势查询。"""
import argparse
import asyncio


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="price-radar CLI：按关键词爬取、任务管理、历史走势查询",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用示例:
  python pr.py --crawl "三星/SK 64G5600" --pages 3
  python pr.py --task list
  python pr.py --task start --id 0
  python pr.py --task create --name "xxx" --keyword "xxx" --pages 3
  python pr.py --trend "三星/SK 64G5600" --days 30 --json
""",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--crawl", metavar="KEYWORD", help="按关键词爬取并落库")
    action.add_argument("--task", metavar="ACTION", help="任务管理动作: list|create|start|stop|delete")
    action.add_argument("--trend", metavar="KEYWORD", help="查询关键词历史价格走势")
    parser.add_argument("--platform", default="goofish", help="平台: goofish|jd|taobao|1688 (默认 goofish)")
    parser.add_argument("--pages", type=int, default=3, help="爬取页数 (默认 3)")
    parser.add_argument("--mode", choices=["ai", "keyword"], default="keyword", help="crawl 模式 (默认 keyword)")
    parser.add_argument("--json", action="store_true", help="结构化 JSON 输出")
    parser.add_argument("--days", type=int, default=30, help="走势窗口天数 (默认 30)")
    parser.add_argument("--export", metavar="PATH", help="trend 导出 CSV 路径")
    parser.add_argument("--name", help="task create 的任务名")
    parser.add_argument("--keyword", help="task create 的关键词")
    parser.add_argument("--id", type=int, help="task start/stop/delete 的任务 ID")
    return parser.parse_args(argv)


async def main(argv=None):
    args = _parse_args(argv)
    if args.crawl:
        from pr import cmd_crawl
        await cmd_crawl(args)
    elif args.task:
        from pr import cmd_task
        await cmd_task(args)
    elif args.trend:
        from pr import cmd_trend
        await cmd_trend(args)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pr_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add pr.py tests/unit/test_pr_cli.py
git commit -m "feat(cli): pr.py 参数解析骨架"
```

---

### Task 2: 表格与 JSON 输出工具

**Files:**
- Modify: `pr.py`（追加 `_render_table` / `_print_json`）
- Test: `tests/unit/test_pr_cli.py`（追加）

- [ ] **Step 1: Write the failing test**

```python
import json

from pr import _render_table, _print_json

def test_render_table_aligns_headers(capsys):
    _render_table(["ID", "名称"], [[1, "三星/SK"], [10, "很长很长的名字"]])
    out = capsys.readouterr().out
    assert "ID" in out and "名称" in out
    assert "三星/SK" in out and "很长很长的名字" in out

def test_render_table_empty():
    assert _render_table(["A", "B"], []) is None  # 打印 "(无数据)"，不抛异常

def test_print_json(capsys):
    _print_json({"a": 1, "中文": "值"})
    parsed = json.loads(capsys.readouterr().out)
    assert parsed == {"a": 1, "中文": "值"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pr_cli.py -k render -v`
Expected: FAIL with `ImportError: cannot import name '_render_table'`

- [ ] **Step 3: Write minimal implementation**（追加到 pr.py，`import json` 加入顶部）

```python
def _render_table(headers, rows):
    """标准库文本对齐表格；rows 为空时打印 (无数据)。"""
    if not rows:
        print("(无数据)")
        return
    widths = [len(str(header)) for header in headers]
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(str(value)))
    print("  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(v).ljust(widths[i]) for i, v in enumerate(row)))


def _print_json(obj):
    """JSON 结构化输出（机器可解析）。"""
    print(json.dumps(obj, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pr_cli.py -k render -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pr.py tests/unit/test_pr_cli.py
git commit -m "feat(cli): 表格与 JSON 输出工具"
```

---

### Task 3: --trend 历史走势查询

**Files:**
- Modify: `pr.py`（追加 `cmd_trend`）
- Test: `tests/unit/test_pr_cli.py`（追加）

- [ ] **Step 1: Write the failing test**

```python
import json

import pytest

from pr import cmd_trend

SNAPSHOTS = [
    {"snapshot_time": "2026-10-01T10:00:00", "snapshot_day": "2026-10-01",
     "item_id": "1", "title": "A", "price": 100.0},
    {"snapshot_time": "2026-10-02T10:00:00", "snapshot_day": "2026-10-02",
     "item_id": "1", "title": "A", "price": 90.0},
]
INSIGHTS = {
    "market_summary": {"sample_count": 1, "avg_price": 90.0, "min_price": 90.0, "max_price": 90.0},
    "history_summary": {"unique_items": 1, "sample_count": 1, "avg_price": 90.0,
                        "median_price": 90.0, "min_price": 90.0, "max_price": 90.0},
    "daily_trend": [
        {"day": "2026-10-01", "sample_count": 1, "min_price": 100.0, "avg_price": 100.0, "max_price": 100.0},
        {"day": "2026-10-02", "sample_count": 1, "min_price": 90.0, "avg_price": 90.0, "max_price": 90.0},
    ],
    "latest_snapshot_at": "2026-10-02T10:00:00",
}

@pytest.mark.asyncio
async def test_trend_json_output(monkeypatch, capsys):
    monkeypatch.setattr(
        "src.services.price_history_service.load_price_snapshots",
        lambda kw: SNAPSHOTS,
    )
    monkeypatch.setattr(
        "src.services.price_history_service.build_price_history_insights",
        lambda kw, window_days: INSIGHTS,
    )

    class Args:
        trend = "三星"
        days = 30
        json = True
        export = None

    await cmd_trend(Args())
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["latest_snapshot_at"] == "2026-10-02T10:00:00"
    assert len(parsed["daily_trend"]) == 2

@pytest.mark.asyncio
async def test_trend_no_snapshots(monkeypatch, capsys):
    monkeypatch.setattr(
        "src.services.price_history_service.load_price_snapshots",
        lambda kw: [],
    )

    class Args:
        trend = "无数据词"
        days = 30
        json = False
        export = None

    await cmd_trend(Args())
    assert "暂无价格快照" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pr_cli.py -k trend -v`
Expected: FAIL with `ImportError: cannot import name 'cmd_trend'`

- [ ] **Step 3: Write minimal implementation**（追加到 pr.py；顶部 `import csv, os`）

```python
def cmd_trend(args):
    """查询关键词历史价格走势（每日 min/avg/max）。"""
    from src.services.price_history_service import (
        build_price_history_insights,
        load_price_snapshots,
    )

    snapshots = load_price_snapshots(args.trend)
    if not snapshots:
        print(f"关键词 '{args.trend}' 暂无价格快照。请先 --crawl 或运行任务积累数据。")
        return

    insights = build_price_history_insights(args.trend, window_days=args.days)
    if args.json:
        _print_json(insights)
        return

    print(f"关键词: {args.trend}（近 {args.days} 天）  最新快照: {insights['latest_snapshot_at']}")
    market = insights["market_summary"]
    print(
        f"市场样本: {market['sample_count']} 条 | 均价 ¥{market['avg_price']} | "
        f"最低 ¥{market['min_price']} | 最高 ¥{market['max_price']}"
    )
    trend = insights["daily_trend"]
    _render_table(
        ["日期", "样本", "最低价", "均价", "最高价"],
        [
            [p["day"], p["sample_count"], p["min_price"], p["avg_price"], p["max_price"]]
            for p in trend
        ],
    )
    if args.export:
        _export_trend_csv(args.export, trend)
        print(f"已导出: {args.export}")


def _export_trend_csv(path, trend):
    """导出每日走势为 CSV。"""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["day", "sample_count", "min_price", "avg_price", "max_price"])
        for p in trend:
            writer.writerow(
                [p["day"], p["sample_count"], p["min_price"], p["avg_price"], p["max_price"]]
            )
```

注意：`cmd_trend` 为同步函数。`main()` 中调用改为同步调用（见 Task 3 Step 4）。

- [ ] **Step 4: Update main() 调用并跑测试**

在 `pr.py` 的 `main()` 中，将 `await cmd_trend(args)` 改为 `cmd_trend(args)`。

Run: `pytest tests/unit/test_pr_cli.py -k trend -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pr.py tests/unit/test_pr_cli.py
git commit -m "feat(cli): --trend 历史走势查询与 CSV 导出"
```

---

### Task 4: --task list / create / delete

**Files:**
- Modify: `pr.py`（追加 `cmd_task`，先实现 list/create/delete）
- Test: `tests/unit/test_pr_cli.py`（追加）

- [ ] **Step 1: Write the failing test**

```python
import pytest

from pr import cmd_task
from src.domain.models.task import Task


def make_repo(tmp_path, monkeypatch):
    """用临时 SQLite 构造 repository 并替换 cmd_task 内部创建的实例。"""
    from src.infrastructure.persistence.sqlite_task_repository import SqliteTaskRepository
    repo = SqliteTaskRepository(db_path=str(tmp_path / "test.db"))
    monkeypatch.setattr("pr.SqliteTaskRepository", lambda: repo)
    return repo


@pytest.mark.asyncio
async def test_task_create_then_list(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, monkeypatch)

    class CreateArgs:
        task = "create"
        name = "新任务"
        keyword = "新关键词"
        pages = 2
        platform = "goofish"
        id = None

    await cmd_task(CreateArgs())
    tasks = await repo.find_all()
    assert len(tasks) == 1
    assert tasks[0].task_name == "新任务"
    assert tasks[0].decision_mode == "keyword"

    class ListArgs:
        task = "list"
        id = None

    await cmd_task(ListArgs())
    out = capsys.readouterr().out
    assert "新任务" in out


@pytest.mark.asyncio
async def test_task_delete(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, monkeypatch)
    task = Task(
        task_name="t", keyword="k", enabled=True, max_pages=1,
        decision_mode="keyword", ai_prompt_base_file="prompts/base_prompt.txt",
        ai_prompt_criteria_file="",
    )
    saved = await repo.save(task)

    class DeleteArgs:
        task = "delete"
        id = saved.id

    await cmd_task(DeleteArgs())
    assert await repo.find_by_id(saved.id) is None
    assert "已删除" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_task_delete_missing(tmp_path, monkeypatch, capsys):
    make_repo(tmp_path, monkeypatch)

    class DeleteArgs:
        task = "delete"
        id = 999

    await cmd_task(DeleteArgs())
    assert "不存在" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pr_cli.py -k task -v`
Expected: FAIL with `ImportError: cannot import name 'cmd_task'`

- [ ] **Step 3: Write minimal implementation**（追加到 pr.py；顶部 `import os` 已加，`from src.domain.models.task import Task`、`from src.infrastructure.persistence.sqlite_task_repository import SqliteTaskRepository`、`from src.platforms import normalize_platform_key` 放在函数内）

```python
def cmd_task(args):
    """任务管理: list / create / start / stop / delete（复用 Web 同一 SQLite）。"""
    from src.domain.models.task import Task
    from src.infrastructure.persistence.sqlite_task_repository import SqliteTaskRepository
    from src.platforms import normalize_platform_key

    repo = SqliteTaskRepository()
    action = args.task

    if action == "list":
        tasks = asyncio.run(repo.find_all())
        _render_table(
            ["ID", "名称", "关键词", "平台", "启用", "运行中", "定时"],
            [
                [t.id, t.task_name, t.keyword, t.platform, t.enabled, t.is_running, t.cron or ""]
                for t in tasks
            ],
        )
        return

    if action == "create":
        if not args.name or not args.keyword:
            print("create 需要 --name 和 --keyword。示例: --task create --name x --keyword x")
            return
        task = Task(
            task_name=args.name,
            keyword=args.keyword,
            enabled=True,
            max_pages=args.pages,
            platform=normalize_platform_key(args.platform),
            decision_mode="keyword",
            ai_prompt_base_file="prompts/base_prompt.txt",
            ai_prompt_criteria_file="",
        )
        saved = asyncio.run(repo.save(task))
        print(f"已创建任务 #{saved.id}: {saved.task_name}（keyword 模式，不依赖 AI）")
        return

    if action == "delete":
        if args.id is None:
            print("delete 需要 --id")
            return
        ok = asyncio.run(repo.delete(args.id))
        print(f"已删除任务 #{args.id}" if ok else f"任务 #{args.id} 不存在")
        return

    if action in ("start", "stop"):
        _cmd_task_start_stop(args, repo)
        return

    print(f"未知 task 动作: {action}（可选 list/create/start/stop/delete）")


def _cmd_task_start_stop(args, repo):
    """start/stop 的占位实现（Task 5 补全）。"""
    print("待实现")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pr_cli.py -k task -v`
Expected: PASS（start/stop 分支走占位，list/create/delete 通过）

- [ ] **Step 5: Commit**

```bash
git add pr.py tests/unit/test_pr_cli.py
git commit -m "feat(cli): --task list/create/delete 任务管理"
```

---

### Task 5: --task start / stop

**Files:**
- Modify: `pr.py`（补全 `_cmd_task_start_stop`）
- Test: `tests/unit/test_pr_cli.py`（追加）

- [ ] **Step 1: Write the failing test**

```python
import pytest

from pr import _cmd_task_start_stop
from src.domain.models.task import Task


def make_task():
    return Task(
        id=0, task_name="t", keyword="k", enabled=True, max_pages=1,
        decision_mode="keyword", ai_prompt_base_file="prompts/base_prompt.txt",
        ai_prompt_criteria_file="",
    )


@pytest.mark.asyncio
async def test_task_start_runs_scraper(tmp_path, monkeypatch, capsys):
    from src.infrastructure.persistence.sqlite_task_repository import SqliteTaskRepository
    repo = SqliteTaskRepository(db_path=str(tmp_path / "test.db"))
    task = await repo.save(make_task())

    captured = {}

    async def fake_scraper(task_config=None, debug_limit=0):
        captured["config"] = task_config
        return 7

    monkeypatch.setattr("src.platforms.get_scraper", lambda plat: fake_scraper)

    class StartArgs:
        task = "start"
        id = task.id

    _cmd_task_start_stop(StartArgs(), repo)
    assert captured["config"]["keyword"] == "k"
    assert "新增 7 个" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_task_stop_clears_running_flag(tmp_path, monkeypatch):
    from src.infrastructure.persistence.sqlite_task_repository import SqliteTaskRepository
    repo = SqliteTaskRepository(db_path=str(tmp_path / "test.db"))
    running = make_task()
    running = running.model_copy(update={"is_running": True, "execution_status": "running"})
    saved = await repo.save(running)

    class StopArgs:
        task = "stop"
        id = saved.id

    _cmd_task_start_stop(StopArgs(), repo)
    after = await repo.find_by_id(saved.id)
    assert after.is_running is False
    assert after.execution_status == "idle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pr_cli.py -k start_stop -v`
Expected: FAIL（占位实现打印"待实现"，captured 为空）

- [ ] **Step 3: Write the real implementation**（替换 `_cmd_task_start_stop` 占位体）

```python
def _cmd_task_start_stop(args, repo):
    """start: 终端前台运行任务（Ctrl+C 中断）；stop: 清理任务运行状态标记。"""
    from src.platforms import get_scraper, platform_display_name

    task = asyncio.run(repo.find_by_id(args.id))
    if task is None:
        print(f"任务 #{args.id} 不存在")
        return

    if args.task == "stop":
        if not task.is_running:
            print(f"任务 #{args.id} 未在运行")
            return
        cleaned = task.model_copy(
            update={"is_running": False, "execution_status": "idle"}
        )
        asyncio.run(repo.save(cleaned))
        print(
            f"已清理任务 #{args.id} 运行状态；若该任务由 Web 服务进程启动，"
            f"请到 Web UI 停止对应进程"
        )
        return

    # start
    if not task.enabled:
        print(f"任务 #{args.id} 已被禁用，跳过执行")
        return
    if not _check_platform_ready(task.platform):
        return
    task_config = task.model_dump()
    plat = task_config.get("platform") or "goofish"
    print(f"-> 任务 '{task.task_name}' [{platform_display_name(plat)}] 开始运行（Ctrl+C 中断）")
    try:
        count = asyncio.run(
            get_scraper(plat)(task_config=task_config, debug_limit=0)
        )
    except KeyboardInterrupt:
        print("\n已中断")
        return
    print(f"任务 '{task.task_name}' 结束，本次新增 {count} 个商品")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pr_cli.py -k start_stop -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pr.py tests/unit/test_pr_cli.py
git commit -m "feat(cli): --task start/stop 前台运行与状态清理"
```

---

### Task 6: --crawl 按关键词爬取

**Files:**
- Modify: `pr.py`（追加 `cmd_crawl` / `_check_platform_ready` / `_print_items`；`main()` 中 `await cmd_crawl(args)` 改为同步调用）
- Test: `tests/unit/test_pr_cli.py`（追加）

- [ ] **Step 1: Write the failing test**

```python
import json

import pytest

from pr import cmd_crawl, _check_platform_ready


def make_args(**overrides):
    defaults = dict(crawl="三星", platform="goofish", pages=3, mode="keyword", json=True)
    defaults.update(overrides)
    return type("Args", (), defaults)()


@pytest.mark.asyncio
async def test_crawl_calls_scraper_and_reads_results(monkeypatch, capsys):
    captured = {}

    async def fake_scraper(task_config=None, debug_limit=0):
        captured["config"] = task_config
        return 2

    monkeypatch.setattr("src.platforms.get_scraper", lambda plat: fake_scraper)
    monkeypatch.setattr("pr._check_platform_ready", lambda plat: True)

    async def fake_query(filename, sort_by, sort_order, page, limit,
                         ai_recommended_only=False, keyword_recommended_only=False,
                         include_hidden=False, recent_days=None):
        items = [
            {"商品信息": {"商品标题": "货A", "当前售价": "¥100", "商品链接": "http://a"},
             "ai_analysis": {"is_recommended": True}},
            {"商品信息": {"商品标题": "货B", "当前售价": "¥200", "商品链接": "http://b"},
             "ai_analysis": {"is_recommended": False}},
        ]
        return 2, items

    monkeypatch.setattr("src.services.result_storage_service.query_result_records", fake_query)

    await cmd_crawl(make_args())
    assert captured["config"]["keyword"] == "三星"
    assert captured["config"]["platform"] == "goofish"
    out = capsys.readouterr().out
    assert "货A" in out and "货B" in out


def test_platform_ready_goofish_cdp_down(capsys, monkeypatch):
    def fake_urlopen(url, timeout=3):
        raise OSError("down")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert _check_platform_ready("goofish") is False
    assert "9222" in capsys.readouterr().out


def test_platform_ready_non_goofish_returns_true():
    assert _check_platform_ready("jd") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pr_cli.py -k crawl -v`
Expected: FAIL with `ImportError: cannot import name 'cmd_crawl'`

- [ ] **Step 3: Write minimal implementation**（追加到 pr.py；顶部加 `import os, sys` 与 `import urllib.request`）

```python
def cmd_crawl(args):
    """按关键词爬取并落库（默认 keyword 模式，纯采集）。"""
    from src.platforms import get_scraper, normalize_platform_key, platform_display_name
    from src.services.result_storage_service import query_result_records
    from src.services.task_generation_runner import build_criteria_filename
    from src.infrastructure.persistence.storage_names import build_result_filename

    platform = normalize_platform_key(args.platform)
    if not _check_platform_ready(platform):
        return

    if args.mode == "ai":
        criteria = build_criteria_filename(args.crawl)
        if not os.path.exists(criteria):
            print(f"关键词 '{args.crawl}' 尚无分析标准文件: {criteria}")
            print("请先在 Web UI 用 AI 生成任务，或改用 --mode keyword 纯采集。")
            return
        print(f"[info] 将采用分析标准: {criteria}（当前采集管线为纯抓取，AI 分析由任务管线执行）")

    task_config = {
        "task_name": args.crawl,
        "keyword": args.crawl,
        "platform": platform,
        "max_pages": args.pages,
        "decision_mode": args.mode,
    }
    print(f"开始爬取: {args.crawl} [{platform_display_name(platform)}] {args.pages} 页")
    count = asyncio.run(get_scraper(platform)(task_config=task_config, debug_limit=0))
    print(f"本次新增 {count} 个商品")
    if count <= 0:
        return

    total, items = asyncio.run(
        query_result_records(
            build_result_filename(args.crawl),
            sort_by="crawl_time",
            sort_order="desc",
            page=1,
            limit=min(count, 50),
        )
    )
    _print_items(items, json_out=args.json)


def _print_items(items, json_out=False):
    """输出商品结果：JSON 或表格。"""
    if json_out:
        _print_json(items)
        return
    rows = []
    for record in items:
        item = record.get("商品信息", {})
        analysis = record.get("ai_analysis", {}) or {}
        rows.append(
            [
                str(item.get("商品标题") or "")[:30],
                str(item.get("当前售价") or ""),
                "推荐" if analysis.get("is_recommended") else "-",
                str(item.get("商品链接") or ""),
            ]
        )
    _render_table(["标题", "价格", "AI推荐", "链接"], rows)


def _check_platform_ready(platform):
    """平台前置检查：闲鱼需 CDP 专用 Chrome(9222)，其余平台由平台函数内部处理登录态。"""
    if platform != "goofish":
        return True
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3)
        return True
    except Exception:
        from src.platforms._web import CDP_PROFILE_DIR
        print("闲鱼需要 CDP 专用 Chrome（端口 9222），当前未启动。启动命令：")
        print(
            f'  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" '
            f"--remote-debugging-port=9222 --user-data-dir={CDP_PROFILE_DIR}"
        )
        print("启动后需在 Chrome 里登录闲鱼一次（登录态持久化）。")
        return False
```

同时修改 `main()`：`await cmd_crawl(args)` 改为 `cmd_crawl(args)`，`await cmd_task(args)` 改为 `cmd_task(args)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pr_cli.py -v`
Expected: PASS（全部测试）

- [ ] **Step 5: Commit**

```bash
git add pr.py tests/unit/test_pr_cli.py
git commit -m "feat(cli): --crawl 按关键词爬取并输出结果"
```

---

### Task 7: 端到端手动验证

**Files:**
- 无代码改动（验证清单）

- [ ] **Step 1: 语法与帮助检查**

Run: `python pr.py --help`
Expected: 显示全部参数与示例

- [ ] **Step 2: 任务管理验证**

Run: `python pr.py --task list`
Expected: 显示任务 0（三星/SK 64G5600）等现有任务

Run: `python pr.py --task create --name "CLI测试" --keyword "测试词" --pages 1`
Run: `python pr.py --task list`
Run: `python pr.py --task delete --id <新建ID>`
Expected: 创建→列表可见→删除成功

- [ ] **Step 3: 历史走势验证**

Run: `python pr.py --trend "三星/SK 64G5600" --json`
Expected: 返回 10 月 12 日的快照走势（已有一次快照数据）

- [ ] **Step 4: 爬取验证（需要 CDP Chrome 已启动并登录）**

Run: `python pr.py --crawl "三星/SK 64G5600" --pages 1`
Expected: 打印新增商品数并输出表格（标题/价格/链接）；再次运行 `--trend` 可见新增快照

- [ ] **Step 5: Commit 收尾（如需 README 说明）**

如无需改动则跳过。

---

## Self-Review

**1. Spec coverage（对照规格 docs/superpowers/specs/2026-10-31-cli-crawler-design.md）：**
- 命令界面：Task 1（argparse）+ Task 6（--crawl）+ Task 4/5（--task）+ Task 3（--trend）✓
- 架构 pr.py 单文件复用服务层：所有 Task ✓
- 数据流（crawl 构造临时任务→平台函数→读回输出）：Task 6 ✓
- 错误处理（无关键词、CDP 未启动、ai 模式缺 criteria、任务不存在）：Task 6 `_check_platform_ready` / Task 4/5 / Task 6 ai 分支 ✓
- 测试（参数解析/表格/trend/task CRUD）：Task 1-6 各测试 ✓
- YAGNI（无 --no-save、无交互菜单、无新依赖、不动 spider_v2）：✓

**2. Placeholder scan：** 无 TBD/TODO；Task 4 的 `_cmd_task_start_stop` 占位在 Task 5 补全为真实实现（有明确衔接）。✓

**3. Type consistency：**
- `cmd_crawl`/`cmd_task`/`cmd_trend` 为同步函数，`main()` 中同步调用（Task 3/6 已更新 main）✓
- 平台函数签名 `(task_config=..., debug_limit=...)` 与 `src/platforms` 一致 ✓
- `query_result_records` 调用参数与 `result_storage_service` 一致（含默认关键字参数）✓
- `Task` 构造字段与 `src/domain/models/task.py` 一致 ✓
