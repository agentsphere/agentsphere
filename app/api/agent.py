import asyncio

import json
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.config import TZINFO, logger
from app.models.models import Message, User, Chat
from app.services.auth import get_user, validate_token
from app.services.helpers import generate_hash
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
        "models":[
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


def get_response_object(message: str, finish: bool = False):
    return json.dumps({
        "model": "superman",
        "created_at": f"{datetime.now(TZINFO)}",
        "message": {
            "role": "assistant",
            "content": message
        },
        "done": finish,
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
    logger.info("Incoming request: %s", request)

    chat_id = generate_hash(user.id + request.messages[0].content)
    chat = None
    if len(request.messages) == 1:
        chat = Chat(id=chat_id, user=user)
        chats[chat_id] = chat
    else:
        chat = chats[chat_id]
    logger.info("Incoming chat: %s", chat.user.id)

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
                    msg = await chat.get_queue_msg()
                    if msg == "[DONE]":
                        logger.info("Streaming completed for chat_id: %s", chat.id)
                        yield get_response_object("", finish=True) + "\n"
                        break
                    yield stream_response(msg) + "\n"
            finally:
                logger.info("Cleaning up queue for chat_id: %s", chat.id)

        # Return the streaming response
        return StreamingResponse(event_stream(), media_type="application/json")
    else:
        logger.info("Not streaming")
        return get_response_object("Only streaming requests are supported at this time.")
