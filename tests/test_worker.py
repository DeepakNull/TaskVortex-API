import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest_asyncio

from app.core.identifier import generate_uuid
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.repository.metrics_cache_repository import MetricsCacheRepository
from app.repository.metrics_repository import MetricsRepository
from app.worker import process_message


class FakeMessage:
    def __init__(self, body: bytes):
        self.body = body

    @asynccontextmanager
    async def process(self):
        yield


class _SessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


@pytest_asyncio.fixture(autouse=True)
async def worker_uses_test_session(monkeypatch, db_session):
    monkeypatch.setattr("app.worker.AsyncSessionLocal", lambda: _SessionCtx(db_session))


@pytest_asyncio.fixture
async def queued_task(db_session):
    user = User(name="worker", email="worker@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    task = Task(
        title="job", task_type="web_scraping", payload={},
        status=TaskStatus.QUEUED, user_id=user.id,
    )
    db_session.add(task)
    await db_session.flush()
    return task


async def deliver(task_id):
    await process_message(FakeMessage(json.dumps({"task_id": str(task_id)}).encode()))


async def test_success_marks_completed_and_records_metrics(queued_task, db_session, monkeypatch):
    monkeypatch.setattr("app.worker.process_heavy_task", AsyncMock())
    await deliver(queued_task.id)
    await db_session.refresh(queued_task)

    assert queued_task.status == TaskStatus.COMPLETED
    logs = await MetricsRepository(db_session).get_logs_by_task(queued_task.id)
    assert [log.status for log in logs] == ["completed"]
    snapshot = await MetricsCacheRepository().get_snapshot()
    assert (snapshot["completed"], snapshot["failed"]) == (1, 0)


async def test_job_exception_marks_failed_with_message(queued_task, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.worker.process_heavy_task", AsyncMock(side_effect=RuntimeError("boom"))
    )
    await deliver(queued_task.id)
    await db_session.refresh(queued_task)

    assert queued_task.status == TaskStatus.FAILED
    logs = await MetricsRepository(db_session).get_logs_by_task(queued_task.id)
    assert logs[0].message == "boom"
    assert (await MetricsCacheRepository().get_snapshot())["failed"] == 1


async def test_timeout_marks_failed(queued_task, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.worker.process_heavy_task", AsyncMock(side_effect=asyncio.TimeoutError)
    )
    await deliver(queued_task.id)
    await db_session.refresh(queued_task)

    assert queued_task.status == TaskStatus.FAILED
    logs = await MetricsRepository(db_session).get_logs_by_task(queued_task.id)
    assert logs[0].message == "Processing timed out"


async def test_duplicate_delivery_is_ignored(queued_task, db_session, monkeypatch):
    job = AsyncMock()
    monkeypatch.setattr("app.worker.process_heavy_task", job)
    queued_task.status = TaskStatus.COMPLETED
    await db_session.flush()

    await deliver(queued_task.id)

    job.assert_not_called()
    assert await MetricsRepository(db_session).get_logs_by_task(queued_task.id) == []


async def test_bookkeeping_failure_does_not_flip_completed_task(queued_task, db_session, monkeypatch):
    monkeypatch.setattr("app.worker.process_heavy_task", AsyncMock())
    monkeypatch.setattr(
        MetricsCacheRepository, "incr_completed", AsyncMock(side_effect=RuntimeError("redis down"))
    )
    await deliver(queued_task.id)
    await db_session.refresh(queued_task)
    assert queued_task.status == TaskStatus.COMPLETED


async def test_malformed_message_is_dropped_without_error():
    await process_message(FakeMessage(b"not json"))
    await process_message(FakeMessage(b'{"unexpected": 1}'))


async def test_unknown_task_is_dropped_without_error():
    await deliver(generate_uuid())