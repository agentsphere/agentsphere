from fastapi import Query, WebSocket, APIRouter
from app.services.wss import add_connection
from app.config import logger

router = APIRouter()

@router.websocket("/api/v1/wss")
async def receiver_handler(websocket: WebSocket, token: str = Query(...)):
    """Handles WebSocket connections from Receivers."""
    logger.debug("Receiver connected with token %s", token)
    return await add_connection(websocket, token)
