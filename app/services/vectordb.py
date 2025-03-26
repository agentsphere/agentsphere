import os
from typing import Any
from pymilvus import MilvusClient
import ollama
import logging

logger=logging.getLogger(__name__)
from app.services.auth import get_current_user, get_user, validate_token
from app.models.models import *
from app.config import settings


def emb_text(text):
    response = ollama.embeddings(model="mxbai-embed-large", prompt=text)
    return response["embedding"]

client = MilvusClient(settings.MILVUSDBFILE)

from fastapi import Depends, HTTPException
from pydantic import BaseModel



if client.has_collection(collection_name="tool_collection"):
    logger.info("Dropping existing collection: tool_collection")
    client.drop_collection(collection_name="tool_collection")

logger.info("Creating new collection: tool_collection")
client.create_collection(
    collection_name="tool_collection",
    auto_id=True,
    dimension=1024,
)

toolQueries = [
    {"query": "lets setup a postgres", "tool": "bash sh"},
    {"query": "lets create a PR", "tool": "bash sh"},
    {"query": "insert into postgres", "tool": "bash sh"},
    {"query": "commit in repo", "tool": "bash sh"}
]

def addQuery(query):
    """Adds a query to the Milvus vector database with proper error handling."""
    try:
        if not query or not query.get("query") or not query.get("tool"):
            logger.warning("Invalid query data provided. Skipping insertion.")
            return

        logger.info(f"Generating embedding for query: {query.get('query')}")
        vector = emb_text(query.get("query"))

        logger.info(f"Inserting query into collection: {query.get('query')} -> {query.get('tool')}")
        client.insert(
            collection_name="tool_collection",
            data=[{"vector": vector, "text": query.get("query"), "tool": query.get("tool")}]
        )
        logger.info(f"Successfully added query: {query.get('query')} with tool: {query.get('tool')}")
    except Exception as e:
        logger.error(f"Error inserting query into Milvus: {e}")

[addQuery(t) for t in toolQueries]


async def add(request: ToolFindRequest, token: Any = Depends(validate_token)):
    """Handles request to add a query to the vector database."""
    logger.info(f"Received add request: {request}")
    
    try:
        addQuery(request)
        logger.info("Successfully processed add request.")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error processing add request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def find_toolname_by_query(queries: list[str]):
    
    """Handles request to search for a matching tool in the vector database."""
    logger.info(f"Received find request: {queries}")
    
    try:
        filtered = []
        logger.info("Starting vector search")
        
        res = client.search(
            collection_name="tool_collection",
            data=[emb_text(query) for query in queries],
            limit=2,
            output_fields=["text", "tool"],
        )
        for r in res:
            for tool in r:
                logger.debug(f"Search result: {tool}")
                if tool.get("distance") > 0.7:
                    filtered.append(tool.get("entity").get("tool"))
        
        logger.info(f"Search completed. Found tools: {filtered}")
        return list(set(filtered))
    except Exception as e:
        logger.error(f"Error during search: {e}")
        raise e