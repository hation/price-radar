import asyncio

import pytest

from src.services.task_generation_service import TaskGenerationService


async def _drain_pending() -> None:
    # 让事件循环有机会跑完 track() 内部通过 asyncio.create_task 调度的协程
    for _ in range(20):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_track_runs_coroutine_on_current_loop_to_completion():
    service = TaskGenerationService()
    result = {}

    async def work():
        result["ran"] = True

    service.track(work())
    await _drain_pending()

    assert result.get("ran") is True
    assert service._background_tasks == set()


@pytest.mark.asyncio
async def test_track_catches_exceptions_instead_of_crashing(caplog):
    service = TaskGenerationService()

    async def failing_work():
        raise RuntimeError("boom")

    with caplog.at_level("ERROR"):
        service.track(failing_work())
        await _drain_pending()

    assert service._background_tasks == set()
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_shutdown_cancels_in_flight_background_tasks():
    service = TaskGenerationService()
    started = asyncio.Event()
    cancelled = {"value": False}

    async def long_running_work():
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled["value"] = True
            raise

    service.track(long_running_work())
    await started.wait()

    await service.shutdown()

    assert cancelled["value"] is True
    assert service._background_tasks == set()


@pytest.mark.asyncio
async def test_create_job_prunes_finished_jobs_past_ttl():
    service = TaskGenerationService(job_ttl_seconds=0.0)

    old_job = await service.create_job("old-task")
    await service.complete(old_job.job_id, task=None, message="done")

    # 创建下一个作业时会触发一次清理；TTL=0 意味着上一个已完成作业立刻可以被清理
    await service.create_job("new-task")

    assert await service.get_job(old_job.job_id) is None
