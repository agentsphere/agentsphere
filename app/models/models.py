import asyncio
from enum import Enum
import re
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, PrivateAttr


class DifficultyLevel(str, Enum):
    """Enum representing different levels of difficulty."""
    EASY = "easy"
    MEDIUM = "medium"
    COMPLEX = "complex"

class User(BaseModel):
    """
    Represents a user in the system with optional metadata.
    """
    id: str = Field(..., description="Unique identifier for the user.")
    username: str = Field(..., description="The user's display name or handle.")
    role: Optional[str] = Field(default=None, description="The role assigned to the user, e.g., 'admin' or 'member'.")
    mail: Optional[EmailStr] = Field(default=None, description="The user's email address, if provided.")


class Roles(str, Enum):
    """Defines the role of a participant in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"  # Optional: commonly used in LLM/chat roles

    def __str__(self):
        return self.value


class Message(BaseModel):
    """
    Represents a message in a conversation with a defined role and content.
    """
    role: Roles = Field(..., description="The role of the message sender.")
    content: str = Field(..., description="The textual content of the message.")


class ResultType(str, Enum):
    """Defines the type of result"""
    TEXT = "text"
    REPO = "repo"

    def __str__(self):
        return self.value

class Task(BaseModel):
    """
    Represents a single task with rollback instructions, a description, and a test.
    """
    unique_id: str = Field(description="A unique jira style id for the task.")
    unique_name: str = Field(description="A unique name for the task.")
    description: str = Field(description="A detailed explanation of what the task entails.")
    context: str = Field(description="Context Information like repo urls, documentation, company programming guidelines")
    dependsOn: Optional[list[str]] = Field(description="A list of tasks refernced by task unique_id that this task depends on.")
    result_type: ResultType = Field(description="The type of result expected from the task.")

class Tasks(BaseModel):
    """
    Represents a collection of tasks.
    """
    repo_url: Optional[str] = Field(description="If mentioned the URL of the repository where the tasks are stored.")
    repo_name: Optional[str] = Field(description="Repo name.")
    tasks: list[Task] = Field(description="A list of individual tasks to be executed.")



class QuestionStatus(str, Enum):
    """Enum representing the Question Status."""
    OPEN = "open"
    ANSWERED = "answered"

class ClarificationQuestion(BaseModel):
    """
    Represents a clarification question with a counting number, the question itself, and its status.
    """
    number: str = Field(description="A number for the clarification question.i.e. 1, 2, 3,...")
    question: str = Field(description="The text of the clarification question.")
    status: QuestionStatus = Field(default=None, description="The status of the question (e.g., open, answered).")
    answer: Optional[str] = Field(default=None, description="The answer to the clarification question.")

class ClarificationQuestions(BaseModel):
    """
    Represents a list clarification questions.
    """
    questions: list[ClarificationQuestion] = Field(description="A list of clarification questions.")

class Chat(BaseModel):
    """
    Represents a chat session containing a unique ID, the user, and the messages exchanged.
    """
    id: str = Field(..., description="Unique identifier for the chat session.")
    user: User
    messages: list[Message] = Field(default_factory=list, description="List of messages in the chat.")
    category: Optional[DifficultyLevel] = Field(default = None, description="lvl of the chat")
    info: Optional[str] = Field(default=None, description="Additional information about the user request.")
    tasks: Optional[Tasks] = Field(default=None, description="tasks associated with the request.")
    clarification_questions: Optional[list[ClarificationQuestion]] = Field(default=None, description="Clarification questions to be asked to the user.")
    original_request: Optional[str] = Field(default=None, description="The original request made by the user.")
    project_description: Optional[str] = Field(default=None, description="Description of the project.")
    # Mark queue as a private attribute that's not part of the model schema
    _queue: asyncio.Queue = PrivateAttr(default_factory=asyncio.Queue)

    class Config:
        arbitrary_types_allowed = True  # Needed for asyncio.Queue and custom types

    async def get_queue_msg(self):
        return await self._queue.get()

    async def set_message(self, content: str, role: Roles = Roles.ASSISTANT):
        """
        Add a message to the chat and optionally process it via the queue.
        """
        self.messages.append(Message(role=role, content=content))
        tokens = re.findall(r'\S+|\s+', content)  # Matches non-whitespace sequences or whitespace sequences
        for token in tokens:
            await self._queue.put(token)
            await asyncio.sleep(0.03)



class ResponseToolCall(BaseModel):
    done: bool = Field(..., description="True if the task is done, False otherwise.")
    message: str = Field(..., description="Message to the user.")
    repo_update: dict = Field(..., description="Files updates format {filePath: content}.")
    text_result: str = Field(..., description="Text result of the task.")
    get_knowledge: list[str] = Field(..., description="Queries to use to retrieve knowledge.")
    commands: list[str] = Field(..., description="Commands to execute.")


class Parameters(BaseModel):
    """Defines the parameters for a tool, including type, name, and description."""
    type: str
    name: str
    description: str

class ExecutionResponse(BaseModel):
    responseText: str

class Agent(BaseModel):
    """
    Represents an agent with a specific role, background, skill set, and available tools.
    """

    role: str = Field(description="The primary role or job function of the agent.")
    background: str = Field(description="A brief background of the agent, including experience and expertise.")
    skills: str = Field(description="A list of key skills that the agent possesses.")

