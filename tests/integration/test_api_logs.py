import os
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_task_service
from src.api.routes import logs
from src.utils import build_task_log_path


class _FakeTaskService:
    def __init__(self, tasks: dict[int, str]):
        self._tasks = tasks

    async def get_task(self, task_id: int):
        if task_id not in self._tasks:
            return None
        return SimpleNamespace(id=task_id, task_name=self._tasks[task_id])


def _build_client(tmp_path, monkeypatch, tasks: dict[int, str]) -> TestClient:
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(logs.router)
    app.dependency_overrides[get_task_service] = lambda: _FakeTaskService(tasks)
    return TestClient(app)


def _write_log(task_id: int, task_name: str, content: str) -> str:
    # newline="" avoids Windows text-mode \n -> \r\n translation: the real task
    # log file is a raw redirect of subprocess stdout, never opened in Python
    # text mode, so its bytes are whatever the subprocess wrote verbatim.
    log_path = build_task_log_path(task_id, task_name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return log_path


def test_get_logs_without_task_id_prompts_selection(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {})

    response = client.get("/api/logs")

    assert response.status_code == 200
    assert response.json()["new_pos"] == 0


def test_get_logs_returns_404_for_unknown_task(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {})

    response = client.get("/api/logs", params={"task_id": 1})

    assert response.status_code == 404


def test_get_logs_returns_incremental_content(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {1: "Task A"})
    _write_log(1, "Task A", "line1\nline2\n")

    first = client.get("/api/logs", params={"task_id": 1})
    assert first.status_code == 200
    assert first.json()["new_content"] == "line1\nline2\n"
    pos_after_first = first.json()["new_pos"]

    second = client.get("/api/logs", params={"task_id": 1, "from_pos": pos_after_first})
    assert second.json()["new_content"] == ""


def test_get_logs_tail_returns_last_lines(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {1: "Task A"})
    _write_log(1, "Task A", "\n".join(f"line{i}" for i in range(1, 11)))

    response = client.get("/api/logs/tail", params={"task_id": 1, "limit_lines": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "line8\nline9\nline10"
    assert body["has_more"] is True


def test_clear_logs_empties_existing_file(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {1: "Task A"})
    log_path = _write_log(1, "Task A", "some content")

    response = client.delete("/api/logs", params={"task_id": 1})

    assert response.status_code == 200
    assert response.json()["message"] == "日志已成功清空。"
    with open(log_path, encoding="utf-8") as f:
        assert f.read() == ""


def test_clear_logs_without_task_id_is_a_noop_message(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {})

    response = client.delete("/api/logs")

    assert response.status_code == 200
    assert "未指定任务" in response.json()["message"]
