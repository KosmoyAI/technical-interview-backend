import uuid
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .utils.env import get_settings
from .db.db import engine, Base, AsyncSessionLocal
from .services.db.conversation_service import ConversationService
from .services.queue_service import fetch_job, enqueue_job
from .schemas import PromptIn, JobOut, JobStatusOut, ConversationOut
from .ai.llm_graph import stream_llm

settings = get_settings()
app = FastAPI(title="Kosmoy Technical Interview Backend API", version="0.1.0")


@app.on_event("startup")
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


@app.post("/jobs", response_model=JobOut, status_code=202)
async def create_job(payload: PromptIn, session: AsyncSession = Depends(get_session)):
    convo = await ConversationService.create(session, payload.prompt)
    job = enqueue_job(str(convo.id), payload.prompt)
    return JobOut(job_id=job.id, conversation_id=str(convo.id))


@app.get("/jobs/{job_id}", response_model=JobStatusOut)
async def job_status(job_id: str, session: AsyncSession = Depends(get_session)):
    job = fetch_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job id")

    convo = await ConversationService.get(session, uuid.UUID(job.args[0]))
    convo_out = (
        ConversationOut(
            id=str(convo.id),
            prompt=convo.prompt,
            response=convo.response,
            status=convo.status,
        )
        if convo
        else None
    )
    return JobStatusOut(status=job.get_status(refresh=True), conversation=convo_out)


@app.post("/stream")
async def stream_endpoint(payload: PromptIn):
    def gen():
        for chunk in stream_llm(payload.prompt):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain")

