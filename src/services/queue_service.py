from redis import Redis
from rq import Queue

from ..utils.env import get_settings
from ..worker import job_runner

settings = get_settings()

redis_conn = Redis(
    host=settings.VALKEY_HOST,
    port=settings.VALKEY_PORT,
    decode_responses=False,
)

redis_queue = Queue(settings.QUEUE_NAME, connection=redis_conn)

def enqueue_job(conversation_id: str, prompt: str):
    """Push a job onto the Redis queue and return the RQ Job object."""
    return redis_queue.enqueue(job_runner, conversation_id, prompt)


def fetch_job(job_id: str):
    """Retrieve a job (or None) by id."""
    return redis_queue.fetch_job(job_id)

