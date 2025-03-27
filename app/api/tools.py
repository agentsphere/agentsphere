import json
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
import httpx
from pydantic import ValidationError
from typing import Any
import mongomock
from app.services.auth import add_executioner, add_executioner, get_first_uuid_for_user,validate_token
from app.services.tooldb import find_tool_by_name, find_tools_by_name
from app.services.vectordb import find_toolname_by_query
from app.models.models import *
from app.config import logger
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()


#uri = "mongodb+srv://sh:C4GTE2QWI9H9BpTW@agentsphere.3b9wx.mongodb.net/?retryWrites=true&w=majority&appName=agentsphere"

# Create a new client and connect to the server
#client = MongoClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
#try:
#    client.admin.command('ping')
#    print("Pinged your deployment. You successfully connected to MongoDB!")
#except Exception as e:
#    print(e)


TOKEN=os.getenv("TOKEN")
router = APIRouter(prefix="/api/v1/tools")

@router.post("/suggestions",response_model=ToolSuggestionResponse)
async def get_tool_suggestions(request: ToolSuggestionRequest, token: Any = Depends(validate_token)):
    logger.info("Processing /getToolSuggestions request")

    try:
        tools = find_tools_by_name(find_toolname_by_query(request.queries).tools, projection={"name":1, "description":1, "parameters": 1}) 
        return ToolSuggestionResponse(tools=tools)
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except httpx.HTTPStatusError as http_err:
        logger.error(f"HTTP error: {http_err}")
        raise HTTPException(status_code=500, detail="HTTP request failed")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_tool(request: ExecutionRequest, token: Any = Depends(validate_token)) -> ExecutionResponse:
    logger.info("Processing /get request")
    logger.debug(f"Request data: {request}")
    try:
        tool=find_tool_by_name(request.toolname)
        if not tool:
            return HTTPException(status_code=404, detail="Tool not found")
        request.tool = tool

        request.file = tool.file
        request.uuid = get_first_uuid_for_user(request.user.id) # Add default executor if empty, Secure environment,

        #toDO validate params
        async with httpx.AsyncClient() as client:
            url = 'http://127.0.0.1:8000/sendandexecute'  # Example URL that echoes the posted data
            logger.info(f"Sending execution request: {request.model_dump_json()}")

            response = await client.post(url, data=request.model_dump_json(),headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})  # ✅ Correct async call)  # ✅ Correct async call
            return ExecutionResponse(responseText=json.dumps(response.json(), indent=2))
    except httpx.HTTPStatusError as http_err:
        logger.error(f"HTTP error: {http_err}", exc_info=True)
        raise HTTPException(status_code=500, detail="HTTP request failed")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)  # Logs full stack trace
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/token", response_model=TokenResponse)
async def get_executioner_token(request: User,token = Depends(validate_token)):
    logger.info("Get Token for new Executioner")

    return TokenResponse(token=add_executioner(user_id=request.id, uuid=request.id))

@router.get("/client")
async def download_file(token = Depends(validate_token)):
    file_path = "dist/client"  # Adjust path as needed
   
    if not os.path.exists(file_path):
        
        return {"error": "File not found"}
    
    return FileResponse(file_path, media_type="application/octet-stream", filename="agentsphere")