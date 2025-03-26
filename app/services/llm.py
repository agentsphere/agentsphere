import asyncio
from enum import Enum
import json
import os
from typing import Annotated, Any, Dict, Optional
import httpx
import litellm
from pydantic import BaseModel, Field, conint
import time  # Add this import at the top of the file

import logging

from app.models.models import User
from app.services.queue import add_to_queue
from app.services.wss import send_execution_file
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)
TOKEN= os.getenv("TOKEN")
TOOL_EXECUTION_URL=os.getenv("TOOL_EXECUTION_URL")

MODEL="ollama_chat/qwen2.5-coder:32b"
#MODEL="gpt-4o-mini"
class DifficultyLevel(str, Enum):
    """Enum representing different levels of difficulty."""
    EASY = "easy"
    MEDIUM = "medium"
    COMPLEX = "complex"

class CategoryResponse(BaseModel):
    """
    Represents the response model for a category classification.
    """

    lvl: DifficultyLevel = Field(description="The difficulty level of the category.")
    certainty: Annotated[int, Field(ge=0, le=10, description="A confidence score between 0 and 10 indicating the certainty of the classification. 0 = really uncertain, 10 = really certain. If the value is below 6, another Agent will check.")]

class Message(BaseModel):
    role: str
    content: str

class Roles(str, Enum):
    SYSTEM = "system"
    USER = "user"

async def categorizeRequest(chat_id: str, request: str):
    """
    Categorizes a Request using LLM
    """
    logger.info(f"Categorize Request {request}")

    # Start timing
    start_time = time.time()

    # Line to measure
    await asyncio.create_task(add_to_queue(chat_id, f"Let me check how complex your request is... \n\n"))
    # End timing
    end_time = time.time()

    # Log the duration
    logger.info(f"Time taken for add_to_queue: {end_time - start_time:.6f} seconds")

    model = MODEL
    response = await litellm.acompletion(
        model=model,
        response_format=CategoryResponse,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"Categorize response, according to format: {CategoryResponse.__doc__}").model_dump(),
            Message(role=Roles.USER.value, content=f'''Categorize following request, easy: just gathering information, even multiple sources, text generation, able to answer right away after information gathering. medium: requires special background but can be done by one, more than just gathering information. complex: Team is required, multiple roles are involved.  if you are uncertain a seconds Agent will check to confirm your category:
                    {request}
            ''').model_dump()
        ],
    )
    logger.debug(f"respone {response}")

    content = response.choices[0].message.content
    logger.debug(f"content {content}")
    c = CategoryResponse.model_validate(json.loads(content))
    logger.debug(f"c {c}")
    await asyncio.create_task(add_to_queue(chat_id, f"Category: {c.lvl} \n\n "))
    return c

class SolveTask(BaseModel):
    tool_calls: list[str] = Field(description="List of Tool calls in the format tool(param1, param2)")
    done: bool = Field(description="True if the task is done, False if not.")
    message: str = Field(description="Message to the user")


async def execute_tool(user, toolname: str, params: Dict[str, Any]):
    """
    Calls the tool execution API with the given parameters.
    """
    return send_execution_file(ExecutionRequest(user=User(id=user.id, username=user.username), toolname="bash sh", params=params))

    

async def answerRequest(user, chat_id: str,request: str):
    """
    Categorizes a Request using LLM
    """

    logger.info(f"Answer Request {request}")
    await asyncio.create_task(add_to_queue(chat_id, f"Gathering information ... \n\n"))

    model=MODEL
    messages=[
                Message(role=Roles.SYSTEM.value, content=f"Answer Request").model_dump(),
                Message(role=Roles.USER.value, content=f'''Answer Request to the best of your knowledge
                        {request}

                        you can use shell(command) to execute bash/shell commands to gather the needed information, use cli tools, call APIs
                        Follow the syntax to call shell(command) strictly: example: shell(ls -l), shell(gcloud init), shell(echo "content" >> file)
                        if you gather the needed information set done=true and provide a message to the user.
                ''').model_dump()
            ]
    while True:

        response = await litellm.acompletion(
            model=model,
            response_format=SolveTask,
            messages=messages,

        )
        content = response.choices[0].message.content
        logger.info(f"content {content}") # expecting tool call here
        # await asyncio.create_task(add_to_queue(chat_id, f"Superman: Content {content} \n\n"))
        parsedResp = SolveTask.model_validate(json.loads(content))
        logger.info(f"parsedResp {parsedResp}") # expecting tool call here
        if parsedResp.tool_calls:
            for tool_call in parsedResp.tool_calls:

                tool, params = tool_call.split("(", 1)
                params = params[:-1]
                await asyncio.create_task(add_to_queue(chat_id, f"Superman: Toolcall {params} \n\n"))
                
                res = await execute_tool(user, tool, params={"command":params})
                # Log the message content before appending it to the messages list
                message_content = f"Following tool execution has been executed with: Tool {tool} executed with command {params} response {res}"
                logger.info(f"Appending message to messages list: {message_content}")

                # Append the message to the messages list
                messages.append(Message(role=Roles.USER.value, content=message_content).model_dump())
             
        if parsedResp.done:
            await asyncio.create_task(add_to_queue(chat_id, f"Superman: {parsedResp.message} \n\n"))
            break

    return parsedResp.message



class Agent(BaseModel):
    """
    Represents an agent with a specific role, background, skill set, and available tools.
    """

    role: str = Field(description="The primary role or job function of the agent.")
    background: str = Field(description="A brief background of the agent, including experience and expertise.")
    skills: str = Field(description="A list of key skills that the agent possesses.")
    tools: str = Field(description="A list of tools or technologies that the agent is proficient in.")


class AgentWorking(BaseModel):
    """
    Represents an agent's working state, including tools used and the final answer generated.
    """

    toolsToCall: str = Field(description="A list of tools or services the agent needs to call or interact with. In the Format [tool1(parameters), tool2(params)]")
    finalAnswer: str = Field(description="The final response or conclusion provided by the agent after processing.")


class Task(BaseModel):
    """
    Represents a single task with rollback instructions, a description, and a test.
    """

    rollback: str = Field(description="Instructions to revert the task if needed.")
    description: str = Field(description="A detailed explanation of what the task entails.")
    test: str = Field(description="A test or validation method to ensure the task is completed correctly.")
    tool_queries: list[str] = Field(description="A list of tool quereies which might be needed to solve the task. prefer command lines or API calls over UI/Browser tools. Like ['clone git repo', 'list files', 'list directories', 'git commit']")
    context: str = Field(description="Context Information like repo urls, documentation, company programming guidelines")

class Tasks(BaseModel):
    """
    Represents a collection of tasks.
    """

    tasks: list[Task] = Field(description="A list of individual tasks to be executed.")


class ToolSuggestionRequest(BaseModel):
    """Represents a request for tool suggestions based on a query and parameters."""
    #user: Optional[User] = None
    #token: str
    queries: list[str]




class ExecutionRequest(BaseModel):
    """Represents a request to execute a tool with specific parameters."""
    user: Optional[User] = None
    toolname: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


async def solveSubTask(user, agent:Agent, chat_id:str, task: Task):
   #load_tools
    logger.info(f"task {task}")

    await asyncio.create_task(add_to_queue(chat_id, f"{agent.role}: Solving subtask {task.description} \n\n"))
    with httpx.Client() as client:
        data = ToolSuggestionRequest(queries=task.tool_queries)
        url = 'http://127.0.0.1:8000/tools/suggestions'  # Example URL that echoes the posted data
        logger.info(f"Sending execution request: {data.model_dump_json()}")

        responseTools = client.post(url, data=data.model_dump_json(),headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})  # ✅ Correct async call)  # ✅ Correct async call
    logger.info(f"responseTools {responseTools}")

    messages=[
                Message(role=Roles.SYSTEM.value, content=f"You are: {agent.model_dump()}").model_dump(),
                Message(role=Roles.USER.value, content=f'''Shell is available 
                        shell("command") # execute bash/shell commands to create edit files, use cli tools, call APIs
                        whenever you want use the shell use "shell('command')" in the tool calls. you can execute multiple shell commands. Just use multiple entries in the tool_calls list.
                        As long as the task is not done you can continue to execute tools. If you are done set done=true and provide a message to the user.
                        Context Informtion: {task.context}
                        Based on who you are, your background skills and tools, solve the current task:
                        {task.description}
                ''').model_dump()
            ]
    
    while True:

        content = await litellm.acompletion(
            model=MODEL, 
            response_format=SolveTask,
            messages=messages,
        )

        response = content.choices[0].message.content
        logger.info(f"content {response}") # expecting tool call here
        parsedResp = SolveTask.model_validate(json.loads(response))
        
        if parsedResp.tool_calls:
            for tool_call in parsedResp.tool_calls:

                tool, params = tool_call.split("(", 1)
                params = params[:-1]
                await asyncio.create_task(add_to_queue(chat_id, f"{agent.role}: Toolcall {params} \n\n"))
                
                res = await execute_tool(user, tool, params={"command":params})
                messages.append(Message(role=Roles.SYSTEM.value, content=f"Tool {tool} executed with params {params} res {res}").model_dump())
        if parsedResp.done:
            await asyncio.create_task(add_to_queue(chat_id, f"{agent.role}: Subtask finished {parsedResp.message} \n\n"))
            break


    """verify = await litellm.acompletion(
        model=MODEL, 
        response_format=SolveTask,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are: {agent.model_dump()}").model_dump(),
            Message(role=Roles.USER.value, content=f'''Tools available 
                    shell("command") # execute bash/shell commands to create edit files, use cli tools, call APIs

                    Context Informtion: {task.context}
                    Based on who you are, your background skills and tools, test if the current task was solved:
                    {task.description}

                    How to test: {task.test}

                    If how to test doesn't provide any meaningful information on how to test if the task was done you you don't find any way to test return with done=true (same as if you have tested succesfully)
            ''').model_dump()
        ],
    )
    verify_content = verify.choices[0].message.content
    logger.info(f"content {verify}") 
    await asyncio.create_task(add_to_queue(chat_id, f"{agent.role}: Test {verify_content} \n\n"))"""
    return content

 

async def solveMediumRequest(user, chat_id: str, request: str):
    """Solves a Request Medium complexity"""

    logger.info(f"solveMediumRequest {request}")
    model="ollama_chat/qwen2.5-coder:32b"

    await asyncio.create_task(add_to_queue(chat_id, f"Finding best candidate to solve your medium complex request ... \n\n"))

    response = await litellm.acompletion(
        model=model,
        response_format=Agent,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are a Manager").model_dump(),
            Message(role=Roles.USER.value, content=f'''Based on the following request, which schould be of medium complexity, which means a single agent can solve it with the appropriate background, skills and tools. Determine which role, skill, background and tool might be needed. Request:
                    {request}
            ''').model_dump()
        ],
    )
    logger.debug(f"respone {response}")

    content = response.choices[0].message.content

    logger.debug(f"content {content}")
    c = Agent.model_validate(json.loads(content))
    logger.info(f"Agent {c}")
    await asyncio.create_task(add_to_queue(chat_id, f"Starting Agent with role {c.role} with background '{c.background}' ... \n\n"))


    # Gather information

    
    requestImproved = await litellm.acompletion(
        model=model,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are: {c.model_dump()}").model_dump(),
            Message(role=Roles.USER.value, content=f'''
                    Be conscise and clear in your following request.
                    Based on who you are, your background skills and tools. Analyse the request and make it more concrete add information which might be necessary so that an intern could solve the request. Add information like best practices to follow when using tools and solving tasks to fulfull the request. Request:
                    Don't provide too much information, just the necessary information to solve the request.
                    {request}
            ''').model_dump()
        ],
    )
    requestImprovedTxt= requestImproved.choices[0].message.content
    await asyncio.create_task(add_to_queue(chat_id, f"{c.role}: I have refined your original request for further processing: '{requestImprovedTxt}' ... \n\n"))


    await asyncio.create_task(add_to_queue(chat_id, f"{c.role}: Breaking down your request into executable subtasks ... \n\n"))
   
    response = await litellm.acompletion(
        model=model,
        response_format=Tasks,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are: {c.model_dump()}").model_dump(),
            Message(role=Roles.USER.value, content=f'''Based on who you are, your background skills and tools. Analyse the request and break it down into multiple executable tasks, including tasks to test if the request is fullfilled, including steps to rollback to be able to revert if something goes wrong. Always consider Best practices for the considered tool and workflow you use. Request:
                    {requestImprovedTxt}
            ''').model_dump()
        ],
    )
    currentTasks= response.choices[0].message.content

    response = await litellm.acompletion(
        model=model,
        response_format=Tasks,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are: {c.model_dump()}").model_dump(),
            Message(role=Roles.USER.value, content=f'''Context: 
                    Original Request: {requestImprovedTxt}
                    
                    currentTasks: {currentTasks}
                    
                    Based on who you are, your background skills and tools. Analyse the currentTasks if they are executcable steps to solve the given original Request. Improve the given tasks. If the rollback is not needed leave it blank, make the tool queries concise and favour bash, sh, cli calls and mentiond the bash, sh, cli within the tool queries whenever used. Always consider Best practices for the considered tool and workflow you use (i.e. if your all dealing with code use git repo, never push to main use PRs and so on). Request:
                    {request}
            ''').model_dump()
        ],
    )


    logger.debug(f"solve reponse {response}")
    content = response.choices[0].message.content
    logger.info(f"Tasks {content}")

    tasks = Tasks.model_validate(json.loads(content))
    taskString = "\n\n".join([f"* {task.description}" for task in tasks.tasks]) + "\n\n ... "
    await asyncio.create_task(add_to_queue(chat_id, f"{c.role}: Tasks: \n\n {taskString}"))

    # Creating jira Subtasks, toDO

    for task in tasks.tasks:
        await solveSubTask(user, agent=c,chat_id=chat_id, task=task)
      
    return content

class Queries(BaseModel):
    queries: Optional[list[str]] = Field(default = None, description="A list of query strings to be processed.")


def getQueriesForDocument(doc):
    response = litellm.completion(
        model=MODEL,
        response_format=Queries,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are a research query specialist").model_dump(),
            Message(role=Roles.USER.value, content=f'''Given the following Documentation: 
                
                    {doc}
                    
                    ________________________________________

                    Return a list of short search queries users and ai agents might use to search for the provided information in the documentation.
                    Each search query should contain 8-15 words
            ''').model_dump()
        ],
    ) 
    logger.debug(f"solve reponse {response}")
    content = response.choices[0].message.content
    logger.info(f" {content}")

    queries = Queries.model_validate(json.loads(content))
    return queries


async def process_request(user, chat_id: str, request: str):
    """
    Processes a request from a client.
    """
    
    logger.info(f"Processing request {request} for client_id {chat_id}")
    category = await categorizeRequest(chat_id, request)

    if category:
        if category.lvl == DifficultyLevel.EASY:
            await answerRequest(user, chat_id, request)
        elif category.lvl == DifficultyLevel.MEDIUM or category.lvl == DifficultyLevel.COMPLEX:
            await solveMediumRequest(user, chat_id,request)
    await asyncio.create_task(add_to_queue(chat_id, "[DONE]"))
    return "fin"
    