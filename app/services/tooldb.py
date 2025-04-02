from pydantic import ValidationError
from app.config import logger, tool_collection
from app.models.models import Tool


shell=Tool(name= "bash sh", description="Execute bash command and returns the output, use this whenever you want to use a cli", type="command", parameters=[
        {"type": "str", "name":"command","description": "Command to Execute"}
    ])

tool_collection.insert(shell.model_dump(by_alias=True))

logger.info(f"Inserted document: {tool_collection.find_one({'name': 'bash sh'})}")


def find_tool_by_name(name: str, projection: dict = None) -> Tool:
    return Tool.model_validate(tool_collection.find_one({"name": name }))

def find_tools_by_name(names: list[str], projection: dict = None) -> list[Tool]:
    #valid projection {"name":1, "description":1, "parameters": 1}
    toolsRaw = tool_collection.find({"name": {"$in": names}})
    
    tools = []
    for tool in toolsRaw:
        try:
            logger.debug(f"tool {tool}")
            validated_tool = Tool(**tool)
            tools.append(validated_tool)
        except ValidationError as e:
            logger.error(f"Validation error for tool {tool['_id']}: {e}")
    return tools

