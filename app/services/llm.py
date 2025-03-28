import asyncio
from enum import Enum
import json
import os
from typing import Annotated, Any, Dict, Optional
import httpx
import litellm
from pydantic import BaseModel, Field, conint
import time  # Add this import at the top of the file

from app.config import logger, settings

from app.services.knowledge import getKnowledge
from app.models.models import Chat, ExecutionRequest, ResponseToolCall, Roles
from app.models.models import Tool
from app.models.models import User
from app.services.litellm_wrapper import litellm_call
from app.services.queue import add_to_queue
from app.services.wss import send_execution_file
from dotenv import load_dotenv
import textwrap

TOKEN= os.getenv("TOKEN")
TOOL_EXECUTION_URL=os.getenv("TOOL_EXECUTION_URL")

MODEL=settings.LLM_MODEL
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

taskResults = {}


async def categorizeRequest(chat: Chat, request: str):
    """
    Categorizes a Request using LLM
    """
    logger.info(f"Categorize Request {request}")
    
    await chat.set_message("Let me check how complex your request is... \n\n")

    c = await litellm_call(
        chat=chat,
        oneShot=True,
        response_format=CategoryResponse,
        messages = [
            Message(role=Roles.SYSTEM.value, content=f"Categorize response, according to format: {CategoryResponse.__doc__}").model_dump(),
            Message(role=Roles.USER.value, content=f'''Categorize following request, easy: just gathering information, even multiple sources, text generation, able to answer right away after information gathering. medium: requires special background but can be done by one, more than just gathering information. complex: Team is required, multiple roles are involved.  if you are uncertain a seconds Agent will check to confirm your category:
                    {request}
            ''').model_dump()
    ])

    logger.debug(f"c {c}")
    await chat.set_message(f"Category: {c.lvl} \n\n ")
    return c



async def execute_tool(user, toolname: str, params: Dict[str, Any]):
    """
    Calls the tool execution API with the given parameters.
    """
    return await send_execution_file(ExecutionRequest(user=User(id=user.id, username=user.username), toolname="sh", params=params, tool=Tool(type="command")))

    

async def answerRequest(chat: Chat,request: str):
    """
    Categorizes a Request using LLM
    """

    logger.info(f"Answer Request {request}")
    await chat.set_message("Gathering information ... \n\n")

    res = await litellm_call(
        response_format=ResponseToolCall,
        chat=chat,
        request=request,
        messages = [
            Message(role=Roles.SYSTEM.value, content=f"Answer Request").model_dump(),
            Message(role=Roles.USER.value, content=
                    textwrap.dedent(f'''
            Answer Request to the best of your knowledge                             
            {request}

            use:"getKnowledge(query=what is/how to ...)" within the tool_calls_str to gather information via websearch, its like a google search which aggregates information.
            use "shell(command=gcloud/git/echo...")
            to execute bash/shell commands to gather the needed information, use cli tools, call APIs
            Follow the syntax to call shell strictly: example:
            "shell(command=ls -l)

            to not use other tools than getKnowledge and shell. You only have shell and getKnowledge available. Dont be afraid to supply an answer after gathering information.

            if you gathered the needed information set done=true and provide a message to the user.
''')).model_dump()
        ]
    )




class Agent(BaseModel):
    """
    Represents an agent with a specific role, background, skill set, and available tools.
    """

    role: str = Field(description="The primary role or job function of the agent.")
    background: str = Field(description="A brief background of the agent, including experience and expertise.")
    skills: str = Field(description="A list of key skills that the agent possesses.")


class Task(BaseModel):
    """
    Represents a single task with rollback instructions, a description, and a test.
    """
    unique_id: str = Field(description="A unique jira style id for the task.")
    unique_name: str = Field(description="A unique name for the task.")
    description: str = Field(description="A detailed explanation of what the task entails.")
    #test: str = Field(description="A test or validation method to ensure the task is completed correctly.")
    context: str = Field(description="Context Information like repo urls, documentation, company programming guidelines")
    dependsOn: Optional[list[str]] = Field(description="A list of tasks refernced by task unique_id that this task depends on.")

class Tasks(BaseModel):
    """
    Represents a collection of tasks.
    """

    tasks: list[Task] = Field(description="A list of individual tasks to be executed.")



async def solveSubTask(agent:Agent, chat: Chat, task: Task):
    logger.info(f"task {task}")

    await chat.set_message(f"{agent.role}: Solving subtask {task.description} \n\n")

    messages=[
                Message(role=Roles.SYSTEM.value, content=f"You are {agent.role} with background {agent.background} and skill {agent.skills}" ).model_dump(),
                Message(role=Roles.USER.value, content=f'''
                        You are working on: {task.unique_id} {task.unique_name}
                        _______________________________________________________
                        Tools:
                        Shell is available via the tool_calls_str.
                        shell(command=git clone) # execute bash/shell commands to create edit files, use cli tools, call APIs
                        whenever you want use the shell use "shell(command=cd clonedDir)" in the tool calls. you can execute multiple shell commands. Just use multiple entries in the tool_calls list.
                        
                        use getKnowledge(query=what is/how to ...) within the tool_calls to gather information via websearch, its like a google search which aggregates information.
                        As long as the task is not done you can continue to execute tools. If you are done set done=true and provide a message to the user.
                        
                        _______________________________________________________
                        
                        Based on who you are, your background skills and tools, solve the current task:
                        {task.description}

                        if finsished set done=true, provide your work result to solve the task (might be code, documentation, summary, conecpt, etc.) in the work_result field.

                        if you are done provide short a status message with concise information to the user what has been done and that the work result has been added to the work_result_db.
                ''').model_dump()
            ]
    if task.dependsOn:
        for dep in task.dependsOn:
            if chat.id in taskResults and dep in taskResults[chat.id]:
                logger.info(f"dep {dep} taskResults {taskResults[chat.id][dep]}")
                messages.append(Message(role=Roles.ASSISTANT.value,content= f"Task Dependency:{dep} was solved with comment: {taskResults[chat.id][dep]}").model_dump())
            else:
                logger.info(f"dep {dep} not yet solved")
                messages.append(Message(role=Roles.ASSISTANT.value,content= f"Task {dep} not yet solved, you can still try to solve yours").model_dump())

    res =  await litellm_call(
        response_format = ResponseToolCall,
        chat = chat,
        request=task.description,
        messages = messages,
    )
    if chat.id not in taskResults:
        taskResults[chat.id] = {}
    taskResults[chat.id][task.unique_id] = res.work_result
    return res

 

async def solveMediumRequest(chat: Chat, request: str):
    """Solves a Request Medium complexity"""

    logger.info(f"solveMediumRequest {request}")
    await chat.set_message("Finding best candidate to solve your request ... \n\n")

    agent = await litellm_call(
        chat=chat,
        response_format=Agent,
        oneShot=True,
        messages = [
            Message(role=Roles.SYSTEM.value, content=f"You are a Manager").model_dump(),
            Message(role=Roles.USER.value, content=f'''Based on the following request, which schould be of medium complexity, which means a single agent can solve it with the appropriate background, skills and tools. Determine which role, skill, background and tool might be needed. Request:
                    {request}
            ''').model_dump()
    ])

    logger.info(f"Agent {agent}")

    await chat.set_message(f"Starting Agent with role {agent.role} with background '{agent.background}' ... \n\n")
  
    #await chat.set_message(f"{agent.role}: Breaking down your request into subtasks and research steps ... \n\n")
 
    #tasks = await litellm_call(
    #    chat=chat,
    #    oneShot=True,
    #    response_format=Tasks,
    #    messages=[
    #        Message(role=Roles.SYSTEM.value, content=f"You are: {agent.model_dump()}").model_dump(),
    #        Message(role=Roles.USER.value, content=f'''Based on who you are, your background skills and tools. Analyse the request and break it #down into multiple subtasks and research steps including steps to gather information with google search queries. Just include steps which #are necessary to solve the request, gather the needed information. Not more. No extra steps, no "nice-to-have". Always consider Best #practices for the considered tool and workflow you use. Request:
    #                {request}
    #        ''').model_dump()
    #    ],
    #)
    tasks= Tasks(tasks=[Task(unique_id="DE-1",unique_name="Task",description=request,context="",dependsOn=[])])

    #tasksReviewed = await litellm_call(
    #    chat=chat,
    #    oneShot=True,
    #    response_format=Tasks,
    #    messages=[
    #        Message(role=Roles.SYSTEM.value, content=f"You are: {agent.model_dump()}").model_dump(),
    #        Message(role=Roles.USER.value, content=f'''Context: 
    #                Original Request: {request}
    #                
    #                currentTasks: {tasks.model_dump()}
    #                
    #                Based on who you are, your background skills and tools. Analyse the currentTasks if they are executcable steps to solve the given original Request. Improve the given tasks and steps. If the rollback is not needed, for example for research only steps leave it blank. Add shell statements to the task if you might want to execute a cli command on the users behalf. Always consider Best practices for the considered tool and workflow you use (i.e. if your all dealing with code use git repo, never push to main use PRs and so on). 
    #        ''').model_dump()
    #    ],
    #)

    #taskString = "\n\n".join([f"* {task.description}" for task in tasks.tasks]) + "\n\n ... "

    #await chat.set_message(f"{agent.role}: Tasks: \n\n {taskString}")

    # Creating jira Subtasks, toDO

    for task in tasks.tasks:
        result = await solveSubTask(agent=agent,chat=chat, task=task)
      
    return "fin"

class Queries(BaseModel):
    queries: Optional[list[str]] = Field(default = None, description="A list of query strings to be processed.")


def getQueriesForDocument(doc, query):  
    logger.info(f"getQueriesForDocument {doc[:100]} {query}")
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
                    If the following query can be used to find relevant information in the documentation, add it to your list of queries. 
                    But please only add the query if the answer is not the page. The Documentation is maybe just a subpage and a different page might be better suited to answer the query:
                    {query}
            ''').model_dump()
        ],
    ) 
    logger.debug(f"solve reponse {response}")
    content = response.choices[0].message.content

    queries = Queries.model_validate(json.loads(content))
    return queries


async def process_request(chat: Chat, request: str):
    """
    Processes a request from a client.
    """
    
    logger.info(f"Processing request {request} for chat_id {chat.id}")
    category = await categorizeRequest(chat, request)

    if category:
        if category.lvl == DifficultyLevel.EASY:
            await answerRequest(chat, request)
        elif category.lvl == DifficultyLevel.MEDIUM or category.lvl == DifficultyLevel.COMPLEX:
            await solveMediumRequest(chat,request)
    await chat.set_message("[DONE]")
    return "fin"
    