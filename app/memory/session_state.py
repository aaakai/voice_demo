from pydantic import BaseModel, Field
from typing import List, Literal, Optional
import uuid


class Message(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class SessionState(BaseModel):
    session_id: str
    state: str = "idle"
    assistant_speaking: bool = False
    playback_stage: str = "idle"
    current_turn_id: Optional[str] = None
    last_interrupt_action: Optional[str] = None
    last_assistant_reply: Optional[str] = None
    history: List[Message] = Field(default_factory=list)

    def add_user_message(self, text: str) -> None:
        self.history.append(Message(role="user", text=text))

    def add_assistant_message(self, text: str) -> None:
        self.history.append(Message(role="assistant", text=text))
        self.last_assistant_reply = text

    def new_turn_id(self) -> str:
        self.current_turn_id = str(uuid.uuid4())
        return self.current_turn_id