"""
进程管理服务
负责管理爬虫进程的启动和停止
"""

import asyncio
import contextlib
import os
import signal
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, TextIO

from src.ai_handler import send_ntfy_notification
from src.config import STATE_FILE
from src.failure_guard import FailureGuard
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.persistence.sqlite_task_repository import find_task_by_name_sync
from src.utils import build_task_log_path

logger = get_logger(__name__)

STOP_TIMEOUT_SECONDS = 20
SPIDER_DEBUG_LIMIT_ENV = "SPIDER_DEBUG_LIMIT"
DEFAULT_TASK_LOG_MAX_BYTES = 5 * 1024 * 1024
LifecycleHook = Callable[[int], Awaitable[None] | None]
QueueChangedHook = Callable[[], Awaitable[None] | None]


@dataclass
class _QueuedTask:
    task_id: int
    task_name: str


class ProcessService:
    """进程管理服务

    任务执行改为串行队列：所有启动请求进入 FIFO 队列，由单个 worker 按顺序
    取出并执行，同一时间只有一个任务在运行。这样可以避免多个爬虫子进程并发
    抢占账号 / 触发风控。
    """

    def __init__(self):
        self.processes: Dict[int, asyncio.subprocess.Process] = {}
        self.log_paths: Dict[int, str] = {}
        self.log_handles: Dict[int, TextIO] = {}
        self.task_names: Dict[int, str] = {}
        self.exit_watchers: Dict[int, asyncio.Task] = {}
        self.failure_guard = FailureGuard()
        self._task_log_max_bytes = max(
            1024, int(os.getenv("TASK_LOG_MAX_BYTES", "") or DEFAULT_TASK_LOG_MAX_BYTES)
        )
        self._on_started: LifecycleHook | None = None
        self._on_stopped: LifecycleHook | None = None
        self._on_enqueued: LifecycleHook | None = None
        self._on_queue_changed: QueueChangedHook | None = None
        # 串行队列相关状态
        self._queue: deque[_QueuedTask] = deque()
        self._enqueued: Dict[int, _QueuedTask] = {}
        self._queue_event = asyncio.Event()
        self._worker_task: asyncio.Task | None = None
        self._shutting_down = False

    def set_lifecycle_hooks(
        self,
        *,
        on_started: LifecycleHook | None = None,
        on_stopped: LifecycleHook | None = None,
        on_enqueued: LifecycleHook | None = None,
        on_queue_changed: QueueChangedHook | None = None,
    ) -> None:
        self._on_started = on_started
        self._on_stopped = on_stopped
        self._on_enqueued = on_enqueued
        self._on_queue_changed = on_queue_changed

    async def _invoke_hook(self, hook: LifecycleHook | None, task_id: int) -> None:
        if hook is None:
            return
        result = hook(task_id)
        if asyncio.iscoroutine(result):
            await result

    async def _broadcast_queue_changed(self) -> None:
        if self._on_queue_changed is None:
            return
        result = self._on_queue_changed()
        if asyncio.iscoroutine(result):
            await result

    def start(self) -> None:
        """启动串行队列 worker（需在事件循环内调用）。"""
        self._shutting_down = False
        self._ensure_worker()

    def _ensure_worker(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())

    def _resolve_cookie_path(self, task_name: str) -> str | None:
        """Best-effort cookie/state path for a task."""
        try:
            task = find_task_by_name_sync(task_name)
            if task and isinstance(task.account_state_file, str) and task.account_state_file.strip():
                return task.account_state_file.strip()
        except Exception:
            pass

        return STATE_FILE if os.path.exists(STATE_FILE) else None

    def is_running(self, task_id: int) -> bool:
        """检查任务是否正在运行"""
        process = self.processes.get(task_id)
        return process is not None and process.returncode is None

    async def _drain_finished_process(self, task_id: int) -> None:
        process = self.processes.get(task_id)
        if process is None or process.returncode is None:
            return

        watcher = self.exit_watchers.get(task_id)
        if watcher is not None:
            await asyncio.shield(watcher)
            return

        self._cleanup_runtime(task_id, process)
        await self._invoke_hook(self._on_stopped, task_id)

    def _rotate_log_file_if_too_large(self, log_file_path: str) -> None:
        """任务日志是子进程 stdout/stderr 的直接重定向，不经过 Python logging，
        没法用 RotatingFileHandler；这里退而求其次，在每次任务启动前检查一次
        大小，超过阈值就把旧内容挪到 .1（覆盖上一份），重新开始追加。"""
        try:
            if os.path.getsize(log_file_path) <= self._task_log_max_bytes:
                return
        except OSError:
            return

        rotated_path = f"{log_file_path}.1"
        try:
            os.replace(log_file_path, rotated_path)
        except OSError as exc:
            logger.warning(f"轮转任务日志文件失败，将继续追加写入: {log_file_path} ({exc})")

    def _open_log_file(self, task_id: int, task_name: str) -> tuple[str, TextIO]:
        os.makedirs("logs", exist_ok=True)
        log_file_path = build_task_log_path(task_id, task_name)
        self._rotate_log_file_if_too_large(log_file_path)
        log_file_handle = open(log_file_path, "a", encoding="utf-8")
        return log_file_path, log_file_handle

    def _build_spawn_command(self, task_name: str) -> list[str]:
        command = [
            sys.executable,
            "-u",
            "spider_v2.py",
            "--task-name",
            task_name,
        ]
        debug_limit = str(os.getenv(SPIDER_DEBUG_LIMIT_ENV, "")).strip()
        if debug_limit.isdigit() and int(debug_limit) > 0:
            command.extend(["--debug-limit", debug_limit])
        return command

    async def _spawn_process(
        self,
        task_name: str,
        log_file_handle: TextIO,
    ) -> asyncio.subprocess.Process:
        preexec_fn = os.setsid if sys.platform != "win32" else None
        child_env = os.environ.copy()
        child_env["PYTHONIOENCODING"] = "utf-8"
        child_env["PYTHONUTF8"] = "1"
        return await asyncio.create_subprocess_exec(
            *self._build_spawn_command(task_name),
            stdout=log_file_handle,
            stderr=log_file_handle,
            preexec_fn=preexec_fn,
            env=child_env,
        )

    def _register_runtime(
        self,
        task_id: int,
        task_name: str,
        process: asyncio.subprocess.Process,
        log_file_path: str,
        log_file_handle: TextIO,
    ) -> None:
        self.processes[task_id] = process
        self.log_paths[task_id] = log_file_path
        self.log_handles[task_id] = log_file_handle
        self.task_names[task_id] = task_name
        self.exit_watchers[task_id] = asyncio.create_task(self._watch_process_exit(process))

    def is_queued(self, task_id: int) -> bool:
        """检查任务是否在串行队列中等待"""
        return task_id in self._enqueued

    def get_queue_state(self) -> dict:
        """返回当前串行队列状态：running + 排队顺序"""
        running = [tid for tid, proc in self.processes.items() if proc.returncode is None]
        queued = [item.task_id for item in self._queue]
        return {"running": running, "queued": queued}

    async def enqueue_task(self, task_id: int, task_name: str) -> bool:
        """将任务加入串行执行队列，返回是否成功入队"""
        await self._drain_finished_process(task_id)
        if self.is_running(task_id):
            logger.warning(f"任务 '{task_name}' (ID: {task_id}) 已在运行中")
            return False
        if self.is_queued(task_id):
            logger.warning(f"任务 '{task_name}' (ID: {task_id}) 已在队列中")
            return False

        decision = self.failure_guard.should_skip_start(
            task_name,
            cookie_path=self._resolve_cookie_path(task_name),
        )
        if decision.skip:
            await self._notify_skip(task_name, decision)
            return False

        item = _QueuedTask(task_id=task_id, task_name=task_name)
        self._queue.append(item)
        self._enqueued[task_id] = item
        self._ensure_worker()
        self._queue_event.set()
        logger.info(f"任务 '{task_name}' (ID: {task_id}) 已加入串行执行队列")
        await self._invoke_hook(self._on_enqueued, task_id)
        await self._broadcast_queue_changed()
        return True

    async def _worker_loop(self) -> None:
        """串行队列 worker：一次只执行一个任务"""
        while not self._shutting_down:
            if not self._queue:
                try:
                    await self._queue_event.wait()
                except asyncio.CancelledError:
                    break
            if self._shutting_down:
                break
            if not self._queue:
                # 事件被触发但队列已空（空唤醒），清掉标志重新等待
                self._queue_event.clear()
                continue

            item = self._queue.popleft()
            self._enqueued.pop(item.task_id, None)
            await self._broadcast_queue_changed()
            await self._run_queued(item)

    async def _run_queued(self, item: _QueuedTask) -> None:
        """实际运行队列中的一个任务，直到其进程退出再返回"""
        task_id, task_name = item.task_id, item.task_name
        await self._drain_finished_process(task_id)
        if self.is_running(task_id):
            return

        decision = self.failure_guard.should_skip_start(
            task_name,
            cookie_path=self._resolve_cookie_path(task_name),
        )
        if decision.skip:
            await self._notify_skip(task_name, decision)
            return

        log_file_path = ""
        log_file_handle = None
        try:
            log_file_path, log_file_handle = self._open_log_file(task_id, task_name)
            process = await self._spawn_process(task_name, log_file_handle)
        except Exception as exc:
            self._close_log_handle(log_file_handle)
            logger.error(f"启动任务 '{task_name}' 失败: {exc}")
            # 启动失败：把状态复位为空闲，避免任务永远卡在“排队中”
            await self._invoke_hook(self._on_stopped, task_id)
            await self._broadcast_queue_changed()
            return

        self._register_runtime(task_id, task_name, process, log_file_path, log_file_handle)
        logger.info(f"启动任务 '{task_name}' (PID: {process.pid})")
        await self._invoke_hook(self._on_started, task_id)
        # 阻塞直到当前任务进程退出，保证串行
        await self._await_exit_watcher(task_id)

    async def _notify_skip(self, task_name: str, decision) -> None:
        logger.warning(
            f"[FailureGuard] 跳过启动任务 '{task_name}'，已暂停重试 "
            f"(连续失败 {decision.consecutive_failures}/{self.failure_guard.threshold})"
        )
        if not decision.should_notify:
            return
        try:
            await send_ntfy_notification(
                {
                    "商品标题": f"[任务暂停] {task_name}",
                    "当前售价": "N/A",
                    "商品链接": "#",
                },
                "任务处于暂停状态，将跳过执行。\n"
                f"原因: {decision.reason}\n"
                f"连续失败: {decision.consecutive_failures}/{self.failure_guard.threshold}\n"
                f"暂停到: {decision.paused_until.strftime('%Y-%m-%d %H:%M:%S') if decision.paused_until else 'N/A'}\n"
                "修复方法: 更新登录态/cookies文件后会自动恢复。",
            )
        except Exception as exc:
            logger.warning(f"发送任务暂停通知失败: {exc}")

    async def _watch_process_exit(self, process: asyncio.subprocess.Process) -> None:
        await process.wait()
        task_id = self._find_task_id_by_process(process)
        if task_id is None:
            return
        self._cleanup_runtime(task_id, process)
        await self._invoke_hook(self._on_stopped, task_id)
        await self._broadcast_queue_changed()

    def _find_task_id_by_process(self, process: asyncio.subprocess.Process) -> int | None:
        for task_id, current_process in self.processes.items():
            if current_process is process:
                return task_id
        return None

    def _cleanup_runtime(
        self,
        task_id: int,
        process: asyncio.subprocess.Process,
    ) -> None:
        if self.processes.get(task_id) is not process:
            return
        self.processes.pop(task_id, None)
        self.log_paths.pop(task_id, None)
        self.task_names.pop(task_id, None)
        self._close_log_handle(self.log_handles.pop(task_id, None))
        self.exit_watchers.pop(task_id, None)

    def _close_log_handle(self, log_handle: TextIO | None) -> None:
        if log_handle is None:
            return
        with contextlib.suppress(Exception):
            log_handle.close()

    def _append_stop_marker(self, log_path: str | None) -> None:
        if not log_path:
            return
        try:
            timestamp = datetime.now().strftime(" %Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"[{timestamp}] !!! 任务已被终止 !!!\n")
        except Exception as exc:
            logger.warning(f"写入任务终止标记失败: {exc}")

    async def stop_task(self, task_id: int) -> bool:
        """停止任务进程，或从串行队列中移除待执行任务"""
        # 若任务还在队列中，直接从队列移除（取消排队）
        if task_id in self._enqueued:
            self._queue = deque(i for i in self._queue if i.task_id != task_id)
            self._enqueued.pop(task_id, None)
            self._queue_event.set()
            logger.info(f"任务 ID {task_id} 已从串行队列中移除")
            await self._invoke_hook(self._on_stopped, task_id)
            await self._broadcast_queue_changed()
            return True

        await self._drain_finished_process(task_id)
        process = self.processes.get(task_id)
        if process is None:
            logger.warning(f"任务 ID {task_id} 没有正在运行的进程")
            return False
        if process.returncode is not None:
            await self._await_exit_watcher(task_id)
            logger.info(f"任务进程 {process.pid} (ID: {task_id}) 已退出，略过停止")
            return False

        try:
            await self._terminate_process(process, task_id)
            self._append_stop_marker(self.log_paths.get(task_id))
            await self._await_exit_watcher(task_id)
            logger.info(f"任务进程 {process.pid} (ID: {task_id}) 已终止")
            return True
        except ProcessLookupError:
            logger.warning(f"进程 (ID: {task_id}) 已不存在")
            return False
        except Exception as exc:
            logger.error(f"停止任务进程 (ID: {task_id}) 时出错: {exc}")
            return False

    async def _terminate_process(
        self,
        process: asyncio.subprocess.Process,
        task_id: int,
    ) -> None:
        if sys.platform != "win32":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=STOP_TIMEOUT_SECONDS)
            return
        except asyncio.TimeoutError:
            logger.warning(
                f"任务进程 {process.pid} (ID: {task_id}) 未在 "
                f"{STOP_TIMEOUT_SECONDS} 秒内退出，准备强制终止..."
            )

        if sys.platform != "win32":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()
        await process.wait()

    async def _await_exit_watcher(self, task_id: int) -> None:
        watcher = self.exit_watchers.get(task_id)
        if watcher is None:
            return
        await asyncio.shield(watcher)

    async def stop_all(self) -> None:
        """停止所有运行中的任务，并清空串行队列（保留 worker 继续待命）"""
        queued_ids = list(self._enqueued.keys())
        self._queue.clear()
        self._enqueued.clear()
        self._queue_event.set()
        for task_id in queued_ids:
            await self._invoke_hook(self._on_stopped, task_id)
        await self._broadcast_queue_changed()

        task_ids = list(self.processes.keys())
        for task_id in task_ids:
            await self.stop_task(task_id)

    async def shutdown(self) -> None:
        """应用关闭时调用：停止所有任务并终止 worker"""
        self._shutting_down = True
        self._queue.clear()
        self._enqueued.clear()
        self._queue_event.set()
        if self._worker_task is not None:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None

        task_ids = list(self.processes.keys())
        for task_id in task_ids:
            await self.stop_task(task_id)
