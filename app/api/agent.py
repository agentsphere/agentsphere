import asyncio


from fastapi import Depends
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.config import TZINFO, logger
import json

from app.models.models import Message, User, Chat
from app.services.auth import get_user, validate_token
from app.services.helpers import generate_hash
from pydantic import BaseModel
from app.services.llm import process_request



class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    stream: Optional[bool] = False


class ModelDetails(BaseModel):
    format: str
    family: str
    families: Optional[List[str]] = None
    parameter_size: str
    quantization_level: str


class Model(BaseModel):
    name: str
    model: str
    modified_at: datetime
    size: int
    digest: str
    details: ModelDetails


router = APIRouter()


@router.get("/api/tags", response_model=Dict[str, List[Model]])
def list_models(token: str = Depends(validate_token)):
    return {
        "models": [
            {
                "name": "superman:latest",
                "model": "superman:latest",
                "modified_at": "2023-12-07T09:32:18.757212583-08:00",
                "size": 3825819519,
                "digest": "fe938a131f40e6f6d40083c9f0f430a515233eb2edaa6d72eb85c50d64f2300e",
                "details": {
                    "format": "gguf",
                    "family": "llama",
                    "families": None,
                    "parameter_size": "7B",
                    "quantization_level": "Q4_0"
                }
            }
        ]
    }


@router.get("/api/version")
def get_version(token: str = Depends(validate_token)):
    return {"version": "0.5.7"}


def getResponseObject(message: str, finish: bool = False):
    return json.dumps({
        "model": "superman",
        "created_at": f"{datetime.now(TZINFO)}",
        "message": {
            "role": "assistant",
            "content": f""
        },
        "done": True,
        "total_duration": 2,
        "load_duration": 2,
        "prompt_eval_count": 2,
        "prompt_eval_duration": 2,
        "eval_count": 2,
        "eval_duration": 2
    })


class CallbackData(BaseModel):
    data: str


@router.post("/callback/{chat_id}")
async def subagent_callback(chat_id: str, data: CallbackData):
    #add_to_queue(chat_id, data.data)
    return {"status": "ok"}


def stream_response(content, role="assistant", finish=False):
    """
    Formats a message for SSE compatible with Open WebUI.

    Parameters:
    - content (str): The content of the message.
    - message_id (str): A unique identifier for the message.
    - finish_reason (str, optional): Reason for finishing the message stream. Use None for intermediate messages and "stop" for the final message.

    Returns:
    - str: A formatted SSE data string.
    """
    sse_data = {
        "model": "superman:latest",
        "created_at": f"{datetime.now(TZINFO)}",
        "message": {
            "role": role,
            "content": f"{content}",
            "images": None
        },
        "done": finish
    }

    return json.dumps(sse_data)

chats = {}

@router.post("/api/chat")
async def handle_models(request: ChatRequest, user: User = Depends(get_user)):
    """
    Handles chat requests and streams responses to OpenWebUI.
    """
    logger.info(f"Incoming request: {request}")

    id = generate_hash(user.id + request.messages[0].content)
    chat = None
    if len(request.messages) == 1:
        chat = Chat(id=id, user=user)
        chats[id] = chat
    else:
        chat = chats[id]
    logger.info(f"Incoming chat: {chat.user.id}")

    if request.stream:
        # Generate a unique chat ID
        async def event_stream():
            """
            Async generator to stream messages to the client.
            """
            try:
                asyncio.create_task(process_request(chat=chat, messages=request.messages))

                while True:
                    # Wait for the next message from the queue
                    msg = await chat.getQueueMsg()
                    if msg == "[DONE]":
                        logger.info(f"Streaming completed for chat_id: {chat.id}")
                        yield getResponseObject("", finish=True) + "\n"
                        break
                    yield stream_response(msg) + "\n"
            finally:
                logger.info(f"Cleaning up queue for chat_id: {chat.id}")

        # Return the streaming response
        return StreamingResponse(event_stream(), media_type="application/json")
    else:
        logger.info("Not streaming")
        return getResponseObject("Only streaming requests are supported at this time.")


