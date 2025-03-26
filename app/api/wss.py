import asyncio
import os
from fastapi import Depends, Query, WebSocket, WebSocketDisconnect, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict
from app.services.auth import check_executioner, check_executioner_uuid_for_user, get_current_user, get_uuid, validate_token
from app.services.wss import add_connection
from app.models.models import *
from app.config import logger

router = APIRouter()

@router.websocket("/api/v1/wss")
async def receiver_handler(websocket: WebSocket, token: str = Query(...)):
    """Handles WebSocket connections from Receivers."""
    logger.debug(f"Receiver connected with token {token}")
    return await add_connection(websocket, token)
