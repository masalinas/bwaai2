import asyncio

from redis.asyncio import Redis

from app.core import constants
from app.core.config import settings
from app.core.logging import logger
from app.worker.processor import JobProcessor


class AutoClaimer:
    def __init__(
        self,
        redis: Redis,
        consumer_name: str,
        processor: JobProcessor,
        semaphore: asyncio.Semaphore,
    ) -> None:
        self.redis = redis
        self.consumer_name = consumer_name
        self.processor = processor
        self.semaphore = semaphore
        self.start_id = "0-0"

    async def sweep_once(self) -> int:
        """Executes a single XAUTOCLAIM cycle to reclaim stuck messages."""
        try:
            res = await self.redis.xautoclaim(
                name=constants.STREAM_DOCUMENTS_JOBS,
                groupname=constants.GROUP_DOCUMENTS_WORKERS,
                consumername=self.consumer_name,
                min_idle_time=settings.CLAIM_IDLE_MS,
                start_id=self.start_id,
                count=settings.CLAIM_BATCH_SIZE,
            )

            # Response structure in redis-py / fakeredis: (next_id, messages, deleted_ids)
            next_start_id, messages, _ = res
            self.start_id = (
                next_start_id.decode("utf-8")
                if isinstance(next_start_id, bytes)
                else str(next_start_id)
            )

            if not messages:
                return 0

            logger.info(
                "[%s] Autoclaimed %d stuck messages from stream %s",
                self.consumer_name,
                len(messages),
                constants.STREAM_DOCUMENTS_JOBS,
            )

            for raw_msg in messages:
                msg_id = raw_msg[0]
                fields = raw_msg[1]
                msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)

                # Check if document is actively locked by another worker
                doc_id = None
                for k, v in fields.items():
                    k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                    if k_str == "document_id":
                        doc_id = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                        break

                if doc_id:
                    lock_held = await self.redis.exists(constants.doc_lock_key(doc_id))
                    if lock_held:
                        logger.warning(
                            "[%s] Document %s lock is actively held by another worker; skipping autoclaim dispatch",
                            self.consumer_name,
                            doc_id,
                        )
                        continue

                # Determine delivery count from XPENDING
                delivery_count = await self._get_delivery_count(msg_id_str)

                # Process claimed job under concurrency limit
                asyncio.create_task(self._process_claimed(msg_id_str, fields, delivery_count))

            return len(messages)

        except Exception as ex:
            logger.warning("[%s] Autoclaim sweep error: %s", self.consumer_name, ex)
            return 0

    async def _get_delivery_count(self, msg_id: str) -> int:
        try:
            # Query XPENDING for this specific message ID
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
        return 2  # Reclaimed messages have been delivered at least twice

    async def _process_claimed(
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
        logger.info("[%s] Started autoclaim background loop", self.consumer_name)
        while not stop_event.is_set():
            try:
                await self.sweep_once()
            except Exception as ex:
                logger.error("[%s] Error in autoclaim loop: %s", self.consumer_name, ex)

            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.AUTOCLAIM_INTERVAL_SECONDS
                )
            except TimeoutError:
                pass
