
# Use an in-memory MongoDB mock
import mongomock
from pydantic import ValidationError
from app.config import logger
from app.models.models import Tool

client = mongomock.MongoClient()
db = client["tooldb"]
collection = db["tool_collection"]

shell=Tool(name= "bash sh", description="Execute bash command and returns the output, use this whenever you want to use a cli", type="command", parameters=[
        {"type": "str", "name":"command","description": "Command to Execute"}
    ])

collection.insert_one(shell.model_dump(by_alias=True))

logger.info(f"Inserted document: {collection.find_one({'name': 'bash sh'})}")


def find_tool_by_name(name: str, projection: dict = None) -> Tool:
    return Tool.model_validate(collection.find_one({"name": name }, projection=projection))

def find_tools_by_name(names: list[str], projection: dict = None) -> list[Tool]:
    #valid projection {"name":1, "description":1, "parameters": 1}
    toolsRaw = collection.find({"name": {"$in": names}}, projection=projection)
    
    tools = []
    for tool in toolsRaw:
        try:
            logger.debug(f"tool {tool}")
            validated_tool = Tool(**tool)
            tools.append(validated_tool)
        except ValidationError as e:
            logger.error(f"Validation error for tool {tool['_id']}: {e}")
    return tools

