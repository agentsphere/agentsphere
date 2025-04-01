import asyncio
from enum import Enum
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, PrivateAttr, model_validator, root_validator



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




class Chat(BaseModel):
    """
    Represents a chat session containing a unique ID, the user, and the messages exchanged.
    """
    id: str = Field(..., description="Unique identifier for the chat session.")
    user: User 
    messages: list[Message] = Field(default_factory=list, description="List of messages in the chat.")
    category: Optional[DifficultyLevel] = Field(default = None, description="lvl of the chat")

    # Mark queue as a private attribute that's not part of the model schema
    _queue: asyncio.Queue = PrivateAttr(default_factory=asyncio.Queue)


    class Config:
        arbitrary_types_allowed = True  # Needed for asyncio.Queue and custom types

    async def getQueueMsg(self):
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
    
class ToolCall(BaseModel):
    tool: str = Field(..., description="The name of the tool to call.")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="The parameters to pass to the tool as a dictionary.",
    )

    @model_validator(mode="before")
    @classmethod
    def parse_params(cls, values: Any) -> Any:
        """
        Parses the `params` field if it is provided as a string in the format `key1=value1, key2=value2`.
        """
        if isinstance(values, dict) and isinstance(values.get("params"), str):
            params_str = values["params"]
            try:
                values["params"] = dict(
                    item.strip().split("=", 1) for item in params_str.split(",") if "=" in item
                )
            except Exception as e:
                raise ValueError(f"Invalid params format: {params_str}. Error: {e}")
        return values


class ResultType(str, Enum):   
    """Defines the type of result."""
    TEXT = "text"
    REPO = "repo"

    def __str__(self):
        return self.value
    

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


class Tool(BaseModel):
    """Represents a tool with metadata including name, description, parameters, code, and file location."""
    id: Optional[str] = Field(None, alias='_id')
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[list[Parameters]] = None
    code: Optional[str] = None
    file: Optional[str] = None
    command: Optional[str] = None
    type: Optional[str] = None


class ExecutionRequest(BaseModel):
    """Represents a request to execute a tool with specific parameters."""
    user: Optional[User] = None
    token: Optional[str] = None
    toolname: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    file: Optional[str] = None
    uuid: Optional[str] = None
    tool: Optional[Tool] = None

class ExecutionResponse(BaseModel):
    responseText: str

class ToolSuggestionRequest(BaseModel):
    """Represents a request for tool suggestions based on a query and parameters."""
    user: Optional[User] = None
    #token: str
    queries: list[str]


class ToolCreationRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[List[Parameters]] = None
    user: Optional[User] = None

class ToolCreationResponse(BaseModel):
    created: bool
    toComplex: bool
    duplicate: bool
    tool: Optional[Tool] = None
    
class ToolSuggestionResponse(BaseModel):
    """Represents the response for tool suggestions, containing a list of suggested tools."""
    tools: Optional[list[Tool]] = None


class ToolFindRequest(BaseModel):
    """Represents a request to find tools based on a token and query."""
    user: Optional[User] = None
    #token: str
    queries: list[str]

class ToolFindResponse(BaseModel):
    """Represents a response to a tool find request, containing a list of tool names."""
    tools: Optional[list[str]] = None

class TokenResponse(BaseModel):
    token: str
# Define __all__ for easier imports




__all__ = [
    "User",
    "ExecutionRequest",
    "ExecutionResponse",
    "ToolSuggestionRequest",
    "Parameters",
    "Tool",
    "ToolSuggestionResponse",
    "ToolFindRequest",
    "ToolFindResponse",
    "TokenResponse"
]


class Agent(BaseModel):
    """
    Represents an agent with a specific role, background, skill set, and available tools.
    """

    role: str = Field(description="The primary role or job function of the agent.")
    background: str = Field(description="A brief background of the agent, including experience and expertise.")
    skills: str = Field(description="A list of key skills that the agent possesses.")


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

