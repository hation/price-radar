import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, JobExecutionEvent

from src.domain.models.task import Task
from src.services.scheduler_service import SchedulerService


def _build_task(task_id: int, cron: str = "*/15 * * * *") -> Task:
    return Task(
        id=task_id,
        task_name=f"task-{task_id}",
        enabled=True,
        keyword="sony a7m4",
        max_pages=2,
        personal_only=True,
        cron=cron,
        ai_prompt_base_file="prompts/base_prompt.txt",
        ai_prompt_criteria_file="prompts/sony_a7m4_criteria.txt",
        is_running=False,
    )


class _FakeProcessService:
    def __init__(self, *, raise_on_start: bool = False):
        self.started = []
        self.raise_on_start = raise_on_start

    async def start_task(self, task_id: int, task_name: str) -> bool:
        self.started.append((task_id, task_name))
        if self.raise_on_start:
            raise RuntimeError("boom")
        return True


@pytest.mark.asyncio
async def test_reload_jobs_configures_misfire_and_concurrency_guards():
    service = SchedulerService(_FakeProcessService())
    task = _build_task(1)

    await service.reload_jobs([task])

    job = service.scheduler.get_job("task_1")
    assert job is not None
    assert job.max_instances == 1
    assert job.coalesce is True
    assert job.misfire_grace_time == 60


@pytest.mark.asyncio
async def test_run_task_logs_and_reraises_on_start_failure(caplog):
    process_service = _FakeProcessService(raise_on_start=True)
    service = SchedulerService(process_service)

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError, match="boom"):
            await service._run_task(1, "task-1")

    assert process_service.started == [(1, "task-1")]
    assert "启动失败" in caplog.text


def test_job_error_listener_logs_exception(caplog):
    service = SchedulerService(_FakeProcessService())

    event = JobExecutionEvent(
        code=EVENT_JOB_ERROR,
        job_id="task_2",
        jobstore="default",
        scheduled_run_time=None,
        exception=RuntimeError("boom"),
    )
    with caplog.at_level("ERROR"):
        service._on_job_event(event)

    assert "task_2" in caplog.text
    assert "boom" in caplog.text


def test_job_missed_listener_logs_without_exception(caplog):
    service = SchedulerService(_FakeProcessService())

    event = JobExecutionEvent(
        code=EVENT_JOB_MISSED,
        job_id="task_3",
        jobstore="default",
        scheduled_run_time=None,
    )
    with caplog.at_level("WARNING"):
        service._on_job_event(event)

    assert "task_3" in caplog.text
