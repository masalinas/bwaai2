import asyncio
import os
import socket
import uuid

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from app.core import constants
from app.core.config import settings
from app.core.logging import logger
from app.worker.processor import JobProcessor


def generate_consumer_name() -> str:
    """Generates unique consumer name: hostname-pid-uuid."""
    hostname = socket.gethostname().split(".")[0]
    pid = os.getpid()
    unique_suffix = uuid.uuid4().hex[:6]
    return f"{hostname}-{pid}-{unique_suffix}"


class StreamConsumer:
    def __init__(
        self,
        redis: Redis,
        processor: JobProcessor | None = None,
        consumer_name: str | None = None,
    ) -> None:
        self.redis = redis
        self.consumer_name = consumer_name or generate_consumer_name()
        self.processor = processor or JobProcessor(redis=self.redis)
        self.semaphore = asyncio.Semaphore(settings.WORKER_CONCURRENCY)
        self._active_tasks: set[asyncio.Task] = set()

    async def init_group(self) -> None:
        """Idempotently creates the consumer group on the stream."""
        try:
            await self.redis.xgroup_create(
                name=constants.STREAM_DOCUMENTS_JOBS,
                groupname=constants.GROUP_DOCUMENTS_WORKERS,
                id="0",
                mkstream=True,
            )
            logger.info(
                "[%s] Created consumer group '%s' on stream '%s'",
                self.consumer_name,
                constants.GROUP_DOCUMENTS_WORKERS,
                constants.STREAM_DOCUMENTS_JOBS,
            )
        except ResponseError as ex:
            if "BUSYGROUP" in str(ex):
                logger.info(
                    "[%s] Consumer group '%s' already exists on stream '%s'",
                    self.consumer_name,
                    constants.GROUP_DOCUMENTS_WORKERS,
                    constants.STREAM_DOCUMENTS_JOBS,
                )
            else:
                logger.error("[%s] Failed to create consumer group: %s", self.consumer_name, ex)
                raise

    async def read_and_process_batch(self) -> int:
        """Reads a batch of new messages using XREADGROUP and dispatches them."""
        try:
            res = await self.redis.xreadgroup(
                groupname=constants.GROUP_DOCUMENTS_WORKERS,
                consumername=self.consumer_name,
                streams={constants.STREAM_DOCUMENTS_JOBS: ">"},
                count=settings.WORKER_BATCH_SIZE,
                block=settings.WORKER_BLOCK_MS,
            )
        except RedisConnectionError as ex:
            logger.warning(
                "[%s] Redis connection error during XREADGROUP: %s", self.consumer_name, ex
            )
            await asyncio.sleep(1)
            return 0

        if not res:
            return 0

        total_processed = 0
        for _stream_name, messages in res:
            for raw_msg in messages:
                msg_id = raw_msg[0]
                fields = raw_msg[1]
                msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)

                # Determine delivery count from XPENDING
                delivery_count = await self._get_delivery_count(msg_id_str)

                task = asyncio.create_task(
                    self._dispatch_with_semaphore(msg_id_str, fields, delivery_count)
                )
                self._active_tasks.add(task)
                task.add_done_callback(self._active_tasks.discard)
                total_processed += 1

        return total_processed

    async def _get_delivery_count(self, msg_id: str) -> int:
        try:
            pending = await self.redis.xpending_range(
                name=constants.STREAM_DOCUMENTS_JOBS,
                groupname=constants.GROUP_DOCUMENTS_WORKERS,
                min=msg_id,
                max=msg_id,
                count=1,
            )
            if pending:
                return pending[0].get("times_delivered", 1)
        except Exception:
            pass
        return 1

    async def _dispatch_with_semaphore(
        self,
        msg_id_str: str,
        fields: dict[str | bytes, str | bytes],
        delivery_count: int,
    ) -> None:
        async with self.semaphore:
            await self.processor.process_message(
                msg_id=msg_id_str,
                fields=fields,
                consumer_name=self.consumer_name,
                delivery_count=delivery_count,
            )

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        """Continuous consumer loop polling for jobs until stop_event is set."""
        logger.info("[%s] Started consumer polling loop", self.consumer_name)
        while not stop_event.is_set():
            try:
                await self.read_and_process_batch()
            except Exception as ex:
                logger.error(
                    "[%s] Unexpected error in consumer loop: %s",
                    self.consumer_name,
                    ex,
                    exc_info=True,
                )
                await asyncio.sleep(1)

    async def drain_in_flight(self, timeout_seconds: int = 15) -> None:
        """Awaits currently in-flight worker tasks up to timeout."""
        if not self._active_tasks:
            return

        logger.info(
            "[%s] Waiting for %d in-flight tasks to complete (timeout: %ds)",
            self.consumer_name,
            len(self._active_tasks),
            timeout_seconds,
        )
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._active_tasks, return_exceptions=True),
                timeout=timeout_seconds,
            )
            logger.info("[%s] All in-flight tasks drained successfully", self.consumer_name)
        except TimeoutError:
            logger.warning(
                "[%s] Drain timeout exceeded; aborting remaining in-flight tasks",
                self.consumer_name,
            )
