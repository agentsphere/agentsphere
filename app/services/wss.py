import asyncio
import json
import os

from fastapi import Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from app.models.models import Chat
from app.services.auth import check_executioner, check_executioner_uuid_for_user, get_uuid

from app.config import logger
from app.services.auth import fake_executioner_clientId

# A structure to store user -> websocket mapping
connected_receivers: dict[str, WebSocket] = {}


async def add_connection(websocket: WebSocket, token: str = Query(...)):
    """Handles WebSocket connections from Receivers."""
    check_token = check_executioner(token)
    uuid = get_uuid(token=token)
    if not check_token or not uuid:
        websocket.close(code=1008)
        return  # Connection closed
    await websocket.accept()

    logger.info("Receiver connected wiht uuid %s", uuid)

    connected_receivers[uuid] = websocket

    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.warning("Receiver disconnected: %s", uuid)
        if uuid in connected_receivers:
            del connected_receivers[uuid]
    except asyncio.CancelledError as e:
        logger.error("WebSocket connection cancelled: %s", e)
    except RuntimeError as e:
        logger.error("Runtime error in WebSocket connection: %s", e)


async def execute_shell(chat: Chat, command: str):
    """Executes a shell command and returns the output."""
    try:
        logger.info("Executing shell command: %s", command)
        await chat.set_message(f"Executing shell command: {command} \n\n")
        ws = connected_receivers.get(chat.user.id)
        if ws is None or not isinstance(ws, WebSocket):
            logger.warning("No valid WebSocket found for uuid %s", chat.user.id)
            return json.dumps({"status_code":404, "content":{"error": "No receiver found for the provided token. No Command execution possible. Do not try again"}})

        await ws.send_text("COMMAND")
        cmd = command
        if cmd:
            logger.info("sending command %s", cmd)
            await ws.send_text(f"{cmd}")

            try:
                response = await ws.receive_text()
                logger.info("Client response: %s", response)
                return response
            except (WebSocketDisconnect, RuntimeError) as recv_error:
                logger.error("Error receiving response from client: %s", recv_error)
                return json.dumps({"status_code":500, "content":{"error": "No acknowledgment from client"}})
        else:
            pass  # Add appropriate handling here if needed
    except (OSError, ValueError) as e:
        logger.error("Error executing shell command: %s", e)
        return f"Error executing command: {e}"

async def send_execution_file(request_raw):
    """
    Sends an executable file to the receiver with parameters.
    """
    try:
        logger.info("Start sendandexecute request: %s", request_raw)
        if request_raw.uuid is None:
            request_raw.uuid = fake_executioner_clientId[request_raw.user.id][0]
        check_executioner_uuid_for_user(user=request_raw.user.id, uuid=request_raw.uuid)

        # Validate receiver
        ws = connected_receivers.get(request_raw.uuid)
        if ws is None or not isinstance(ws, WebSocket):
            logger.warning("No valid WebSocket found for uuid %s", request_raw.uuid)
            return JSONResponse(status_code=404, content={"error": "No receiver found for the provided token"})

        if request_raw.tool.type == "file":
            # Validate file existence
            if not os.path.isfile(request_raw.file):
                logger.error("File not found: %s", request_raw.file)
                return JSONResponse(status_code=400, content={"error": f"File not found: {request_raw.file}"})

            file_name = os.path.basename(request_raw.file)
            logger.info("Sending filename: %s", file_name)
            await ws.send_text("FILE")
            await ws.send_text(file_name)

            # Send file content in chunks
            try:
                with open(request_raw.file, "rb") as f:
                    while chunk := f.read(1024):  # Read in 1KB chunks
                        await ws.send_bytes(chunk)
            except (OSError, IOError) as file_error:
                logger.error("Error reading file %s: %s", request_raw.file, file_error)
                return JSONResponse(status_code=500, content={"error": "Error reading file"})

            # Send EOF signal
            await ws.send_bytes(b"EOF")
            logger.info("EOF signal sent")

        # Wait for acknowledgment from the client
        try:
            response = await ws.receive_text()
            logger.info("Client response: %s", response)
            return response
        except (WebSocketDisconnect, RuntimeError) as recv_error:
            logger.error("Error receiving response from client: %s", recv_error)
    except (OSError, ValueError, KeyError) as e:
        logger.error("Unexpected error in sendandexecute: %s", e)
        raise e
