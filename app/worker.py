import asyncio
import json
import logging
import time

import aio_pika
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import listener, setup_logging
from app.core.redis import redis_client
from app.core.rabbitmq import declare_topology 
from app.models.task import TaskStatus
from app.repository.metrics_cache_repository import MetricsCacheRepository
from app.repository.metrics_repository import MetricsRepository
from app.repository.task_repository import TaskRepository

logger = logging.getLogger(__name__)


async def process_heavy_task():
    await asyncio.sleep(5)


@retry(
    retry=retry_if_exception_type(OperationalError),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
)
async def _fetch_task_with_retry(repo: TaskRepository, task_id):
    return await repo.get_task_for_processing(task_id)


async def _invalidate_history_cache(user_id) -> None:
    keys = [k async for k in redis_client.scan_iter(match=f"task_history:{user_id}:*")]
    if keys:
        await redis_client.delete(*keys)


async def process_message(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            body = json.loads(message.body.decode())
            task_id = body["task_id"]
        except (json.JSONDecodeError, KeyError):
            logger.exception("Malformed message, dropping")
            return

        ctx = {"context": {"task_id": task_id}}
        logger.info("Message received", extra=ctx)

        async with AsyncSessionLocal() as db:
            repo = TaskRepository(db)
            metrics_repo = MetricsRepository(db)
            metrics_cache = MetricsCacheRepository()

            try:
                task = await _fetch_task_with_retry(repo, task_id)
            except OperationalError:
                logger.exception("DB unreachable after retries", extra=ctx)
                raise

            if task is None:
                logger.warning("Task not found, dropping message", extra=ctx)
                return

            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                logger.info("Duplicate delivery ignored", extra=ctx)
                return

            # Capture before any commit/rollback so we never lazy-load later.
            internal_task_id = task.id
            user_id = task.user_id

            task.status = TaskStatus.PROCESSING
            await db.commit()

            # --- Step A: run the job. Only this is inside the try. ---
            start = time.monotonic()
            error_message: str | None = None
            try:
                await asyncio.wait_for(process_heavy_task(), timeout=10.0)
            except asyncio.TimeoutError:
                error_message = "Processing timed out"
                logger.warning("Task processing timed out", extra=ctx)
            except Exception as e:
                error_message = str(e)
                logger.exception("Unexpected error during processing", extra=ctx)
            execution_time_ms = int((time.monotonic() - start) * 1000)

            # --- Step B: record the outcome in the DB (source of truth). ---
            succeeded = error_message is None
            task.status = TaskStatus.COMPLETED if succeeded else TaskStatus.FAILED
            await db.commit()

            # --- Step C: best-effort bookkeeping. Failure here must NOT change task status. ---
            try:
                if succeeded:
                    await metrics_cache.incr_completed(execution_time_ms)
                else:
                    await metrics_cache.incr_failed()

                await metrics_repo.create_log(
                    task_id=internal_task_id,
                    status="completed" if succeeded else "failed",
                    execution_time_ms=execution_time_ms,
                    message=error_message,
                )
                await _invalidate_history_cache(user_id)
            except Exception:
                logger.exception("Post-processing bookkeeping failed", extra=ctx)

            logger.info("Task finished", extra={"context": {"task_id": task_id, "status": "completed" if succeeded else "failed"}})


async def main():
    setup_logging()
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await declare_topology(channel)
        await queue.consume(process_message)

        logger.info("Worker started. Waiting for messages...")
        await asyncio.Future()
    finally:
        await connection.close()
        listener.stop()


if __name__ == "__main__":
    asyncio.run(main())