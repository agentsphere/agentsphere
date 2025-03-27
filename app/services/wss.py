import asyncio
import os
from fastapi import Depends, Query, WebSocket, WebSocketDisconnect, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict
from app.models.models import Chat
from app.services.auth import check_executioner, check_executioner_uuid_for_user, get_current_user, get_uuid, validate_token
from app.models.models import *
from app.config import logger
from app.services.auth import fake_executioner_clientId

# A structure to store user -> websocket mapping
connected_receivers: Dict[str, WebSocket] = {}

test_token = "mytoken"




async def add_connection(websocket: WebSocket, token: str = Query(...)):
    """Handles WebSocket connections from Receivers."""
    check_token = check_executioner(token)
    uuid = get_uuid(token=token)
    if not check_token or not uuid:
        websocket.close(code=1008) 
        return  # Connection closed
    await websocket.accept()
    
    logger.info(f"Receiver connected wiht uuid {uuid}")

    connected_receivers[uuid] = websocket

    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.warning(f"Receiver disconnected: {test_token}")
        if test_token in connected_receivers:
            del connected_receivers[test_token]


async def executeShell(chat: Chat, command: str):
    """Executes a shell command and returns the output."""
    try:
        logger.info(f"Executing shell command: {command}")
        ws = connected_receivers.get(chat.user.id)
        if ws is None or not isinstance(ws, WebSocket):
            logger.warning(f"No valid WebSocket found for uuid {chat.user.uuid}")
            return JSONResponse(status_code=404, content={"error": "No receiver found for the provided token"})

        await ws.send_text("COMMAND")
        cmd = command
        if cmd:
            logger.info(f"sending command {cmd}")
            await ws.send_text(f"{cmd}")
        else:
            logger.info("no command found")
    
        try:
            response = await ws.receive_text()
            logger.info(f"Client response: {response}")
            return response
        except Exception as recv_error:
            logger.error(f"Error receiving response from client: {recv_error}")
            return JSONResponse(status_code=500, content={"error": "No acknowledgment from client"})
    except Exception as e:
        logger.error(f"Error executing shell command: {e}")
        return f"Error executing command: {e}"

async def send_execution_file(requestRaw: ExecutionRequest):
    """
    Sends an executable file to the receiver with parameters.
    """
    try:
        logger.info(f"Start sendandexecute request: {requestRaw}")
        if requestRaw.uuid is None:
            requestRaw.uuid = fake_executioner_clientId[requestRaw.user.id][0]
        check_executioner_uuid_for_user(user=requestRaw.user.id, uuid=requestRaw.uuid)

        # Validate receiver
        ws = connected_receivers.get(requestRaw.uuid)
        if ws is None or not isinstance(ws, WebSocket):
            logger.warning(f"No valid WebSocket found for uuid {requestRaw.uuid}")
            return JSONResponse(status_code=404, content={"error": "No receiver found for the provided token"})

        if requestRaw.tool.type == "file":
            # Validate file existence
            if not os.path.isfile(requestRaw.file):
                logger.error(f"File not found: {requestRaw.file}")
                return JSONResponse(status_code=400, content={"error": f"File not found: {requestRaw.file}"})

            file_name = os.path.basename(requestRaw.file)
            logger.info(f"Sending filename: {file_name}")
            await ws.send_text("FILE")
            await ws.send_text(file_name)

            # Send file content in chunks
            try:
                with open(requestRaw.file, "rb") as f:
                    while chunk := f.read(1024):  # Read in 1KB chunks
                        await ws.send_bytes(chunk)
            except Exception as file_error:
                logger.error(f"Error reading file {requestRaw.file}: {file_error}")
                return JSONResponse(status_code=500, content={"error": "Error reading file"})

            # Send EOF signal
            await ws.send_bytes(b"EOF")
            logger.info("EOF signal sent")
        elif requestRaw.tool.type == "command":
            await ws.send_text("COMMAND")
            cmd = requestRaw.params.get("command", None)
            if cmd:
                logger.info(f"sending command {cmd}")
                await ws.send_text(f"{cmd}")
            else:
                logger.info("no command found")
        
        # Wait for acknowledgment from the client
        try:
            response = await ws.receive_text()
            logger.info(f"Client response: {response}")
            return response
        except Exception as recv_error:
            logger.error(f"Error receiving response from client: {recv_error}")
            return JSONResponse(status_code=500, content={"error": "No acknowledgment from client"})

    except Exception as e:
        logger.error(f"Unexpected error in sendandexecute: {e}")
        raise e
