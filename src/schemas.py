from pydantic import BaseModel, Field

class PromptIn(BaseModel):
    prompt: str = Field(..., examples=["Tell me a joke about cats."])

class JobOut(BaseModel):
    job_id: str
    conversation_id: str

class ConversationOut(BaseModel):
    id: str | None
    prompt: str | None
    response: str | None
    status: str | None

class JobStatusOut(BaseModel):
    status: str
    conversation: ConversationOut | None
