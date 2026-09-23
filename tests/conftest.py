import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Add repository root to the path so package imports work consistently
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from src.api import dependencies as deps
from src.api.routes import tasks
from src.infrastructure.persistence.sqlite_task_repository import SqliteTaskRepository
from src.services.task_service import TaskService
from src.services.task_generation_service import TaskGenerationService


@pytest.fixture()
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def load_json_fixture(fixtures_dir):
    def _load(name: str):
        return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))

    return _load


@pytest.fixture()
def sample_task_payload():
    return {
        "task_name": "Sony A7M4",
        "enabled": True,
        "keyword": "sony a7m4",
        "description": "Good condition body with accessories",
        "analyze_images": True,
        "max_pages": 2,
        "personal_only": True,
        "min_price": "8000",
        "max_price": "16000",
        "cron": "*/15 * * * *",
        "ai_prompt_base_file": "prompts/base_prompt.txt",
        "ai_prompt_criteria_file": "prompts/sony_a7m4_criteria.txt",
        "decision_mode": "ai",
        "keyword_rules": [],
    }


class FakeProcessService:
    def __init__(self):
        self.started = []
        self.stopped = []
        self._on_started = None
        self._on_stopped = None

    def set_lifecycle_hooks(self, *, on_started=None, on_stopped=None):
        self._on_started = on_started
        self._on_stopped = on_stopped

    async def start_task(self, task_id: int, task_name: str) -> bool:
        self.started.append((task_id, task_name))
        if self._on_started:
            await self._on_started(task_id)
        return True

    async def stop_task(self, task_id: int):
        self.stopped.append(task_id)
        if self._on_stopped:
            await self._on_stopped(task_id)


class FakeSchedulerService:
    def __init__(self):
        self.reload_calls = 0
        self.next_run_times = {}

    async def reload_jobs(self, tasks):
        self.reload_calls += 1
        base = datetime(2026, 3, 19, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.next_run_times = {
            task.id: base + timedelta(minutes=(index + 1) * 15)
            for index, task in enumerate(tasks)
            if task.id is not None and task.enabled and task.cron
        }

    def get_next_run_time(self, task_id: int):
        return self.next_run_times.get(task_id)


@pytest.fixture()
def api_context(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text("[]", encoding="utf-8")
    db_path = tmp_path / "app.sqlite3"

    # SqliteTaskRepository(db_path=...) below only isolates the task table itself.
    # tasks.py's route handlers also reach into result_storage_service /
    # price_history_service on delete (delete_result_file_records,
    # delete_price_snapshots), and those always resolve the database path via
    # APP_DATABASE_FILE / the default "data/app.sqlite3" — without this env
    # override they would silently read/write the developer's real local
    # database instead of this test's temp one.
    monkeypatch.setenv("APP_DATABASE_FILE", str(db_path))

    repository = SqliteTaskRepository(
        db_path=str(db_path),
        legacy_config_file=None,
    )
    task_service = TaskService(repository)
    process_service = FakeProcessService()
    scheduler_service = FakeSchedulerService()
    task_generation_service = TaskGenerationService()

    app = FastAPI()
    app.include_router(tasks.router)

    def override_get_task_service():
        return task_service

    def override_get_process_service():
        return process_service

    def override_get_scheduler_service():
        return scheduler_service

    def override_get_task_generation_service():
        return task_generation_service

    async def mark_started(task_id: int):
        await task_service.update_task_status(task_id, True)

    async def mark_stopped(task_id: int):
        task = await task_service.get_task(task_id)
        if task:
            await task_service.update_task_status(task_id, False)

    process_service.set_lifecycle_hooks(on_started=mark_started, on_stopped=mark_stopped)

    app.dependency_overrides[deps.get_task_service] = override_get_task_service
    app.dependency_overrides[deps.get_process_service] = override_get_process_service
    app.dependency_overrides[deps.get_scheduler_service] = override_get_scheduler_service
    app.dependency_overrides[deps.get_task_generation_service] = override_get_task_generation_service

    return {
        "app": app,
        "config_file": config_file,
        "db_path": db_path,
        "process_service": process_service,
        "scheduler_service": scheduler_service,
        "task_generation_service": task_generation_service,
    }


@pytest.fixture()
def api_client(api_context):
    # 必须作为上下文管理器使用，否则 Starlette TestClient 会为每次请求单独开关一个
    # 事件循环，导致请求处理过程中通过 asyncio.create_task 启动的后台作业（例如
    # AI 任务生成）在响应返回后就被连带销毁，永远没有机会跑完。
    with TestClient(api_context["app"]) as client:
        yield client
