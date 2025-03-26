from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class User(BaseModel):
    id: str 
    role: Optional[str] = None
    username: str
    mail: Optional[str] = None
    token: Optional[str] = None 

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