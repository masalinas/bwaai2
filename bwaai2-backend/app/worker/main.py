import asyncio
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.core import constants
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.services.storage import close_redis_pool, get_redis_client
from app.worker.autoclaim import AutoClaimer
from app.worker.consumer import StreamConsumer


async def heartbeat_loop(redis, consumer_name: str, stop_event: asyncio.Event) -> None:
    """Periodically writes a heartbeat key in Redis and a local file for worker health inspection."""
    key = constants.worker_heartbeat_key(consumer_name)
    logger.info("[%s] Started heartbeat task on key '%s'", consumer_name, key)
    heartbeat_file = Path("/tmp/worker_heartbeat")
    while not stop_event.is_set():
        try:
            now_iso = datetime.now(UTC).isoformat()
            await redis.set(key, now_iso, ex=30)
            heartbeat_file.write_text(now_iso, encoding="utf-8")
        except Exception as ex:
            logger.warning("[%s] Heartbeat update failed: %s", consumer_name, ex)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.HEARTBEAT_INTERVAL_SECONDS)
        except TimeoutError:
            pass

    try:
        heartbeat_file.unlink(missing_ok=True)
    except Exception:
        pass


async def run_worker() -> None:
    setup_logging(debug=settings.DEBUG)
    redis = get_redis_client()

    # Pre-flight Redis check with retry
    retries = 5
    for attempt in range(retries):
        try:
            await redis.ping()
            logger.info("Connected to Redis successfully at %s", settings.REDIS_URL)
            break
        except Exception as ex:
            if attempt == retries - 1:
                logger.error("Could not connect to Redis at %s: %s", settings.REDIS_URL, ex)
                sys.exit(1)
            logger.warning("Redis ping attempt %d failed (%s), retrying in 2s...", attempt + 1, ex)
            await asyncio.sleep(2)

    stop_event = asyncio.Event()

    consumer = StreamConsumer(redis=redis)
    processor = consumer.processor
    autoclaimer = AutoClaimer(
        redis=redis,
        consumer_name=consumer.consumer_name,
        processor=processor,
        semaphore=consumer.semaphore,
    )

    # Initialize consumer group
    await consumer.init_group()

    # Setup signal handlers for graceful termination
    loop = asyncio.get_running_loop()

    def handle_signal(sig_name: str) -> None:
        logger.info(
            "[%s] Received %s, initiating graceful shutdown...", consumer.consumer_name, sig_name
        )
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_signal, sig.name)
        except NotImplementedError:
            # Signal handling may differ on Windows
            pass

    # Start concurrent worker loops
    tasks = [
        asyncio.create_task(consumer.run_loop(stop_event), name="consumer_loop"),
        asyncio.create_task(autoclaimer.run_loop(stop_event), name="autoclaim_loop"),
        asyncio.create_task(
            heartbeat_loop(redis, consumer.consumer_name, stop_event), name="heartbeat_loop"
        ),
    ]

    logger.info(
        "[%s] Worker initialized with concurrency=%d, claim_idle_ms=%d",
        consumer.consumer_name,
        settings.WORKER_CONCURRENCY,
        settings.CLAIM_IDLE_MS,
    )

    # Wait until stop event is signaled
    await stop_event.wait()

    # Cancel background maintenance loops
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    # Drain active in-flight worker tasks
    await consumer.drain_in_flight(timeout_seconds=settings.SHUTDOWN_TIMEOUT_SECONDS)

    # Clean shutdown of Redis pool
    await close_redis_pool()
    logger.info("[%s] Worker shutdown complete.", consumer.consumer_name)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
