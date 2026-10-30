import json

import pytest

from pr import _parse_args, main, _render_table, _print_json

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

def test_trend_json_output(monkeypatch, capsys):
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

    cmd_trend(Args())
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["latest_snapshot_at"] == "2026-10-02T10:00:00"
    assert len(parsed["daily_trend"]) == 2

def test_trend_no_snapshots(monkeypatch, capsys):
    monkeypatch.setattr(
        "src.services.price_history_service.load_price_snapshots",
        lambda kw: [],
    )

    class Args:
        trend = "无数据词"
        days = 30
        json = False
        export = None

    cmd_trend(Args())
    assert "暂无价格快照" in capsys.readouterr().out


import pytest

from pr import cmd_task
from src.domain.models.task import Task


def make_repo(tmp_path, monkeypatch):
    """用临时 SQLite 构造 repository 并替换 cmd_task 内部创建的实例。"""
    from src.infrastructure.persistence.sqlite_task_repository import SqliteTaskRepository
    repo = SqliteTaskRepository(db_path=str(tmp_path / "test.db"))
    monkeypatch.setattr("pr.SqliteTaskRepository", lambda: repo)
    return repo


def test_task_create_then_list(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, monkeypatch)

    class CreateArgs:
        task = "create"
        name = "新任务"
        keyword = "新关键词"
        pages = 2
        platform = "goofish"
        id = None

    cmd_task(CreateArgs())
    tasks = asyncio_run(repo.find_all())
    assert len(tasks) == 1
    assert tasks[0].task_name == "新任务"
    assert tasks[0].decision_mode == "keyword"

    class ListArgs:
        task = "list"
        id = None

    cmd_task(ListArgs())
    out = capsys.readouterr().out
    assert "新任务" in out


def test_task_delete(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, monkeypatch)
    task = Task(
        task_name="t", keyword="k", enabled=True, max_pages=1,
        personal_only=True,
        decision_mode="keyword", ai_prompt_base_file="prompts/base_prompt.txt",
        ai_prompt_criteria_file="",
    )
    saved = asyncio_run(repo.save(task))

    class DeleteArgs:
        task = "delete"
        id = saved.id

    cmd_task(DeleteArgs())
    assert asyncio_run(repo.find_by_id(saved.id)) is None
    assert "已删除" in capsys.readouterr().out


def test_task_delete_missing(tmp_path, monkeypatch, capsys):
    make_repo(tmp_path, monkeypatch)

    class DeleteArgs:
        task = "delete"
        id = 999

    cmd_task(DeleteArgs())
    assert "不存在" in capsys.readouterr().out


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
