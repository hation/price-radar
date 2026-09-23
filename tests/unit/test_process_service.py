import asyncio
import sys
from types import SimpleNamespace

from src.services.process_service import ProcessService


class FakeProcess:
    def __init__(self, pid: int):
        self.pid = pid
        self.returncode = None
        self._done = asyncio.Event()

    async def wait(self):
        await self._done.wait()
        return self.returncode

    def finish(self, returncode: int = 0):
        self.returncode = returncode
        self._done.set()

    def terminate(self):
        self.finish(-15)

    def kill(self):
        self.finish(-9)


def test_process_service_marks_task_stopped_when_process_exits(monkeypatch, tmp_path):
    fake_process = FakeProcess(pid=4321)
    events = []

    async def run_scenario():
        service = ProcessService()
        service.failure_guard.should_skip_start = lambda *args, **kwargs: SimpleNamespace(
            skip=False,
            should_notify=False,
            reason="",
            consecutive_failures=0,
            paused_until=None,
        )

        started_event = asyncio.Event()
        stopped = asyncio.Event()

        async def on_started(task_id: int):
            events.append(("started", task_id))
            started_event.set()

        async def on_stopped(task_id: int):
            events.append(("stopped", task_id))
            stopped.set()

        service.set_lifecycle_hooks(on_started=on_started, on_stopped=on_stopped)

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(
            "src.services.process_service.build_task_log_path",
            lambda task_id, _task_name: str(tmp_path / f"task-{task_id}.log"),
        )
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        enqueued = await service.enqueue_task(0, "task-a")
        assert enqueued is True
        service.start()
        assert service.is_queued(0) or service.is_running(0)

        await asyncio.wait_for(started_event.wait(), timeout=1)
        assert events == [("started", 0)]
        assert service.is_running(0) is True

        fake_process.finish(0)
        await asyncio.wait_for(stopped.wait(), timeout=1)

        assert ("stopped", 0) in events
        assert service.is_running(0) is False

        await service.shutdown()

    asyncio.run(run_scenario())


def test_process_service_adds_debug_limit_arg_when_env_enabled(monkeypatch):
    monkeypatch.setenv("SPIDER_DEBUG_LIMIT", "1")
    service = ProcessService()

    command = service._build_spawn_command("task-a")

    assert command == [
        sys.executable,
        "-u",
        "spider_v2.py",
        "--task-name",
        "task-a",
        "--debug-limit",
        "1",
    ]


def test_rotate_log_file_moves_oversized_log_to_dot_one(tmp_path, monkeypatch):
    # _task_log_max_bytes has a 1024-byte floor regardless of the env var, so the
    # fixture content must exceed that floor to actually trigger rotation.
    monkeypatch.setenv("TASK_LOG_MAX_BYTES", "10")
    service = ProcessService()
    assert service._task_log_max_bytes == 1024
    content = "x" * 2000
    log_path = tmp_path / "task-a.log"
    log_path.write_text(content, encoding="utf-8")

    service._rotate_log_file_if_too_large(str(log_path))

    assert not log_path.exists()
    rotated = tmp_path / "task-a.log.1"
    assert rotated.read_text(encoding="utf-8") == content


def test_rotate_log_file_leaves_small_log_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_LOG_MAX_BYTES", "1024")
    service = ProcessService()
    log_path = tmp_path / "task-a.log"
    log_path.write_text("small", encoding="utf-8")

    service._rotate_log_file_if_too_large(str(log_path))

    assert log_path.read_text(encoding="utf-8") == "small"
    assert not (tmp_path / "task-a.log.1").exists()


def test_rotate_log_file_is_noop_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_LOG_MAX_BYTES", "10")
    service = ProcessService()
    missing_path = tmp_path / "does-not-exist.log"

    service._rotate_log_file_if_too_large(str(missing_path))
