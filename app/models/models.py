import asyncio
from enum import Enum
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, PrivateAttr, model_validator, root_validator



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


class ResponseToolCall(BaseModel):
    tool_calls_str: list[str] = Field(..., description="List of tool calls to execute.")

    done: bool = Field(..., description="True if the task is done, False otherwise.")
    message: str = Field(..., description="Message to the user.")
    work_result: str = Field(..., description="Work result of the task.")

    # Mark queue as a private attribute that's not part of the model schema
    tool_calls: List[ToolCall] = Field(default_factory=list, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def parse_tool_calls_str(cls, values):
        tool_calls_str = values.get("tool_calls_str", [])
        parsed_tool_calls = []

        for call_str in tool_calls_str:
            try:
                name_part, params_part = call_str.split("(", 1)
                tool = name_part.strip()
                params_raw = params_part.rstrip(")")
                # Handle multiple params, e.g. key1=value1, key2=value2
                params = dict(
                    item.strip().split("=", 1)
                    for item in params_raw.split(",")
                    if "=" in item
                )
                parsed_tool_calls.append(ToolCall(tool=tool, params=params))
            except Exception as e:
                raise ValueError(f"Failed to parse tool call string '{call_str}': {e}")

        values["tool_calls"] = parsed_tool_calls
        return values

    class Config:
        arbitrary_types_allowed = True





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