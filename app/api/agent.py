import asyncio
import hashlib

import requests

from fastapi import HTTPException, Header, Depends, status
from datetime import datetime
import os
from typing import Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import logging
from app.config import settings, tzinfo, logger
import json

from app.models.models import Message, User, Chat
from app.services.queue import add_to_queue
from pydantic import BaseModel
from app.services.llm import process_request

TOKEN = os.getenv("TOKEN")


def introspect_token(token: str) -> dict:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token introspection failed"
        )
    ctoken = token.split(" ", 1)[1] if token.startswith("Bearer ") else token
    introspection_url = settings.INTROSPECTION_URL

    client_id = settings.CLIENT
    client_secret = settings.CLIENT_SECRET

    logger.debug(f"id {client_id} sec {client_secret}")
    response = requests.post(
        introspection_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"token": ctoken, "client_id": client_id, "client_secret": client_secret}
    )
    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token introspection failed"
        )


def get_user_headers(
    user_id: Optional[str] = Header(None, alias="X-OpenWebUI-User-Id"),
    user_role: Optional[str] = Header(None, alias="X-OpenWebUI-User-Role"),
    user_name: Optional[str] = Header(None, alias="X-OpenWebUI-User-Name"),
    user_email: Optional[str] = Header(None, alias="X-OpenWebUI-User-Email"),
    token: Optional[str] = Header(None, alias="Authorization")
):
    return {
        "id": user_id,
        "role": user_role,
        "username": user_name,
        "mail": user_email,
        "token": token
    }


def validate_token(token_header: dict = Depends(get_user_headers)):
    logger.debug(f"token_header {token_header}")
    introspect_token(token_header.get("token", None))
    return


logger = logging.getLogger(__name__)


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


def generate_hash(doc: str) -> str:
    """
    Generate a unique hash based on the document content and URL.
    """
    hash_input = doc.encode('utf-8')
    return hashlib.md5(hash_input).hexdigest()


chats = {}


def get_user(user_headers: dict = Depends(get_user_headers)):
    """
    Dependency function to get or create a chat instance.
    """
    introspect_token(user_headers.get("token", None))
    return User(**user_headers)
    logger.info(f"get chat req {req}")
    id = generate_hash(user.id + req.messages[0]["content"])
    if len(req.messages) == 1:
        c = Chat(id=id, user=user)
        chats[id] = c
        return c
    else:
        return chats[id]


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
        "created_at": f"{datetime.now(tzinfo)}",
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
    add_to_queue(chat_id, data.data)
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
        "created_at": f"{datetime.now(tzinfo)}",
        "message": {
            "role": role,
            "content": f"{content}",
            "images": None
        },
        "done": finish
    }

    return json.dumps(sse_data)


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


