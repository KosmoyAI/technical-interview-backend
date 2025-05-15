
import uuid
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...db.models import Conversation


class ConversationService:
    @staticmethod
    async def create(session: AsyncSession, prompt: str) -> Conversation:
        convo = Conversation(prompt=prompt)
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return convo

    @staticmethod
    async def update_status(session: AsyncSession, convo_id: uuid.UUID, *, status: str, response: str | None = None):
        result = await session.execute(select(Conversation).where(Conversation.id == convo_id))
        convo = result.scalar_one()
        convo.status = status
        if response is not None:
            convo.response = response
        await session.commit()
        return convo

    @staticmethod
    async def get(session: AsyncSession, convo_id: uuid.UUID) -> Conversation | None:
        result = await session.execute(select(Conversation).where(Conversation.id == convo_id))
        return result.scalar_one_or_none()
