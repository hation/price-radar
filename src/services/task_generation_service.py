"""
任务生成作业服务
"""
import asyncio
import time
from copy import deepcopy
import threading
from typing import Awaitable, Dict, Iterable, Optional
from uuid import uuid4

from src.domain.models.task import Task
from src.domain.models.task_generation import TaskGenerationJob, TaskGenerationStep
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

DEFAULT_GENERATION_STEPS: tuple[tuple[str, str], ...] = (
    ("prepare", "接收创建请求"),
    ("reference", "读取参考文件"),
    ("prompt", "构建提示词"),
    ("llm", "调用 AI 生成标准"),
    ("persist", "保存分析标准"),
    ("task", "创建任务记录"),
)

# 已完成/失败的作业保留多久后才允许被清理，避免用户轮询结果时job已被回收
DEFAULT_JOB_TTL_SECONDS = 3600.0


class TaskGenerationService:
    """管理 AI 任务生成的后台作业状态"""

    def __init__(
        self,
        step_specs: Iterable[tuple[str, str]] = DEFAULT_GENERATION_STEPS,
        *,
        job_ttl_seconds: float = DEFAULT_JOB_TTL_SECONDS,
    ):
        self._step_specs = tuple(step_specs)
        self._jobs: Dict[str, TaskGenerationJob] = {}
        self._finished_at: Dict[str, float] = {}
        self._job_ttl_seconds = job_ttl_seconds
        self._lock = threading.Lock()
        self._background_tasks: "set[asyncio.Task]" = set()

    async def create_job(self, task_name: str) -> TaskGenerationJob:
        job = TaskGenerationJob(
            job_id=uuid4().hex,
            task_name=task_name,
            steps=[
                TaskGenerationStep(key=key, label=label)
                for key, label in self._step_specs
            ],
        )
        with self._lock:
            self._prune_stale_jobs_locked()
            self._jobs[job.job_id] = job
            return deepcopy(job)

    async def get_job(self, job_id: str) -> Optional[TaskGenerationJob]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return deepcopy(job)

    def _prune_stale_jobs_locked(self) -> None:
        """清理已完成/失败超过 TTL 的作业。调用方需持有 self._lock。"""
        now = time.monotonic()
        expired = [
            job_id
            for job_id, finished_at in self._finished_at.items()
            if now - finished_at >= self._job_ttl_seconds
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
            self._finished_at.pop(job_id, None)

    def track(self, coroutine: Awaitable[None]) -> None:
        """在当前事件循环内跟踪后台作业协程，取代此前脱离事件循环、
        异常会被静默丢弃的裸 threading.Thread + asyncio.run 实现。"""

        async def _runner() -> None:
            try:
                await coroutine
            except Exception as exc:
                logger.error(f"任务生成后台作业出现未捕获异常: {exc}")
            finally:
                current = asyncio.current_task()
                if current is not None:
                    self._background_tasks.discard(current)

        task = asyncio.create_task(_runner())
        self._background_tasks.add(task)

    async def shutdown(self) -> None:
        """应用关闭时取消所有仍在运行的后台生成作业。"""
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def advance(self, job_id: str, step_key: str, message: str) -> TaskGenerationJob:
        with self._lock:
            job = self._require_job(job_id)
            target_index = self._find_step_index(job, step_key)
            job.status = "running"
            job.current_step = step_key
            job.message = message
            for index, step in enumerate(job.steps):
                if step.status == "failed":
                    continue
                if index < target_index:
                    step.status = "completed"
                elif index == target_index:
                    step.status = "running"
                    step.message = message
                elif step.status != "pending":
                    step.status = "pending"
                    step.message = ""
            return deepcopy(job)

    async def complete(self, job_id: str, task: Task, message: str) -> TaskGenerationJob:
        with self._lock:
            job = self._require_job(job_id)
            job.status = "completed"
            job.current_step = None
            job.message = message
            job.error = None
            job.task = task
            for step in job.steps:
                if step.status != "failed":
                    step.status = "completed"
            self._finished_at[job_id] = time.monotonic()
            return deepcopy(job)

    async def fail(
        self,
        job_id: str,
        error: str,
        step_key: Optional[str] = None,
    ) -> TaskGenerationJob:
        with self._lock:
            job = self._require_job(job_id)
            failed_step = step_key or job.current_step
            job.status = "failed"
            job.error = error
            job.message = error
            job.current_step = failed_step
            if failed_step:
                step = self._find_step(job, failed_step)
                if step:
                    step.status = "failed"
                    step.message = error
            self._finished_at[job_id] = time.monotonic()
            return deepcopy(job)

    def _require_job(self, job_id: str) -> TaskGenerationJob:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"任务生成作业不存在: {job_id}")
        return job

    def _find_step(self, job: TaskGenerationJob, step_key: str) -> Optional[TaskGenerationStep]:
        for step in job.steps:
            if step.key == step_key:
                return step
        return None

    def _find_step_index(self, job: TaskGenerationJob, step_key: str) -> int:
        for index, step in enumerate(job.steps):
            if step.key == step_key:
                return index
        raise KeyError(f"未知的任务生成步骤: {step_key}")
