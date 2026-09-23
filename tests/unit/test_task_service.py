import pytest

from src.domain.models.task import Task, TaskCreate, TaskUpdate
from src.services.task_service import TaskService


class _InMemoryTaskRepository:
    def __init__(self):
        self._tasks: dict[int, Task] = {}
        self._next_id = 0

    async def find_all(self):
        return list(self._tasks.values())

    async def find_by_id(self, task_id: int):
        return self._tasks.get(task_id)

    async def save(self, task: Task) -> Task:
        if task.id is None:
            task = task.model_copy(update={"id": self._next_id})
            self._next_id += 1
        self._tasks[task.id] = task
        return task

    async def delete(self, task_id: int) -> bool:
        return self._tasks.pop(task_id, None) is not None


def _task_create(**overrides) -> TaskCreate:
    payload = dict(
        task_name="Sony A7M4",
        enabled=True,
        keyword="sony a7m4",
        description="Good condition body with accessories",
        max_pages=2,
        personal_only=True,
        ai_prompt_base_file="prompts/base_prompt.txt",
        ai_prompt_criteria_file="prompts/sony_a7m4_criteria.txt",
    )
    payload.update(overrides)
    return TaskCreate(**payload)


@pytest.mark.asyncio
async def test_create_task_persists_and_returns_task_with_id():
    service = TaskService(_InMemoryTaskRepository())

    task = await service.create_task(_task_create())

    assert task.id is not None
    assert task.is_running is False
    assert await service.get_task(task.id) == task


@pytest.mark.asyncio
async def test_get_all_tasks_returns_every_created_task():
    service = TaskService(_InMemoryTaskRepository())
    await service.create_task(_task_create(task_name="A", keyword="a"))
    await service.create_task(_task_create(task_name="B", keyword="b"))

    tasks = await service.get_all_tasks()

    assert sorted(t.task_name for t in tasks) == ["A", "B"]


@pytest.mark.asyncio
async def test_update_task_applies_changes():
    service = TaskService(_InMemoryTaskRepository())
    task = await service.create_task(_task_create())

    updated = await service.update_task(task.id, TaskUpdate(task_name="Renamed"))

    assert updated.task_name == "Renamed"
    assert (await service.get_task(task.id)).task_name == "Renamed"


@pytest.mark.asyncio
async def test_update_task_raises_when_task_missing():
    service = TaskService(_InMemoryTaskRepository())

    with pytest.raises(ValueError, match="不存在"):
        await service.update_task(999, TaskUpdate(task_name="Renamed"))


@pytest.mark.asyncio
async def test_update_task_status_flips_is_running():
    service = TaskService(_InMemoryTaskRepository())
    task = await service.create_task(_task_create())
    assert task.is_running is False

    updated = await service.update_task_status(task.id, True)

    assert updated.is_running is True


@pytest.mark.asyncio
async def test_delete_task_removes_it():
    service = TaskService(_InMemoryTaskRepository())
    task = await service.create_task(_task_create())

    deleted = await service.delete_task(task.id)

    assert deleted is True
    assert await service.get_task(task.id) is None


@pytest.mark.asyncio
async def test_delete_task_returns_false_when_missing():
    service = TaskService(_InMemoryTaskRepository())

    assert await service.delete_task(999) is False
