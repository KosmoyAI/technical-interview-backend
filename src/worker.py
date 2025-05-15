import asyncio
import uuid

from redis import Redis
from rq import Worker

from .utils.env import get_settings
from .db.db import engine, Base, AsyncSessionLocal
from .services.db.conversation_service import ConversationService
from .ai.llm_graph import run_llm

settings = get_settings()

redis_conn = Redis(
    host=settings.VALKEY_HOST,
    port=settings.VALKEY_PORT,
    decode_responses=False,
)


async def _setup_db() -> None:
    """Create tables once when the worker process starts."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def job_runner(conversation_id: str, prompt: str) -> None:
    """
    Entry point executed by RQ (synchronous context).

    We spin up a short-lived asyncio event loop for each job so we can use the
    async SQLAlchemy session helpers without leaking a loop between jobs.
    """

    async def _process() -> None:
        async with AsyncSessionLocal() as session:
            await ConversationService.update_status(
                session,
                uuid.UUID(conversation_id),
                status="running",
            )

        try:
            result = run_llm(prompt)

            async with AsyncSessionLocal() as session:
                await ConversationService.update_status(
                    session,
                    uuid.UUID(conversation_id),
                    status="done",
                    response=result,
                )
        except Exception as exc:
            async with AsyncSessionLocal() as session:
                await ConversationService.update_status(
                    session,
                    uuid.UUID(conversation_id),
                    status="failed",
                    response=str(exc),
                )
            raise

    asyncio.run(_process())


if __name__ == "__main__":
    asyncio.run(_setup_db())

    worker = Worker([settings.QUEUE_NAME], connection=redis_conn)
    worker.work(with_scheduler=True)

