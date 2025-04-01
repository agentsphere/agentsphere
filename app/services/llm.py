import asyncio
import hashlib
import json
import os
from typing import Annotated, Any, Dict, Optional
import httpx
import litellm
from pydantic import BaseModel, Field, conint
import time  # Add this import at the top of the file

from app.config import logger, settings

from app.models.models import Agent, ResultType
from app.models.models import Task
from app.models.models import Tasks
from app.models.models import DifficultyLevel
from app.models.repo import Repo
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
                        You are working on a request which is below but first some context information
                        _______________________________________________________
                        Tools:
                        Shell commands are available via the command field.
                        Just list them in the list like ("gcloud instances list"). 
                        Don't use file or git related commands in the command list.
                       
                        
                        use queries in get_knowledge to retrieve information which you need to sovle the task. get_knowledge works like google search and returns summarized useful information.
                        If you are uncertain about the explicit shell commands, for shell commands which only should get information (like gcloud run services list --platform managed) you can always try them right away, there is no harm in that. For shell commands which change the system (like gcloud run deploy) you should be more careful and use get_knowledge first to get the information if you are uncertain about the command.

                        As long as the task is not done you can continue to execute tools. If you are done set done=true and provide a message to the user.
                        _______________________________________________________

                        if finsished set done=true, provide your work result to solve the task (might be code, documentation, summary, conecpt, etc.) in the text_result field.
                        If you are asked to do something like listing resources after calling a shell command, you have to call it using shell command, do not just tell the user how to do it, finish the task (if you are asked to create a git repo create it, if you are asked to provide user specific information call the specific api via a cli, if there is a cli available for that tool it is installed and already setup), please provide the result in the work_result field, and unless specific asked for you don't have to explain the process, just give the answer asked for.
                        If you are not sure about the work result, set done=true, to the best of your knowledge provide the current answer status of tasked solved in work_result and provide a message to the user and ask for feedback.

                        if you are done provide short a status message with concise information to the user what has been done and the detailed work result in text_result.
                        
                        your are not working in a repo, so always leave repo_update blank.
                        _______________________________________________________
                        
                        Based on who you are, your background skills and tools, solve the current task:
                        {request}
''')).model_dump()
        ]
    )

def add_task_results_recursively(task, tasks, messages, chat):
    if not task.dependsOn:
        return

    for dep_id in task.dependsOn:
        dep_task = next((t for t in tasks.tasks if t.unique_id == dep_id), None)
        if dep_task is None:
            logger.warning(f"Dependency {dep_id} not found in tasks")
            continue
        else:
            logger.info(f"Dependency {dep_id} found in tasks")

        # First, recurse into dependencies of this dependency
        add_task_results_recursively(dep_task, tasks, messages, chat)

        # Then, add result message for this dependency if it's a text result
        if dep_task.result_type == ResultType.TEXT:
            result = taskResults.get(chat.id, {}).get(dep_id, None)
            if result is not None:
                messages.append(Message(
                    role=Roles.ASSISTANT.value,
                    content=f"Task Dependency:{dep_id} was solved with result: {result}"
                ).model_dump())
            else:
                logger.warning(f"Dependency {dep_id} not yet solved")
                messages.append(Message(
                    role=Roles.ASSISTANT.value,
                    content=f"Task Dependency:{dep_id} not yet solved, you can still try to solve yours"
                ).model_dump())


async def solveSubTask(agent:Agent, chat: Chat, task: Task, repo: Repo, tasks: Tasks=None):
    logger.info(f"task {task}")

    await chat.set_message(f"{agent.role}: Solving subtask {task.description} \n\n")

    messages=[
                Message(role=Roles.SYSTEM.value, content=f"You are {agent.role} with background {agent.background} and skill {agent.skills}" ).model_dump(),
                Message(role=Roles.USER.value, content=textwrap.dedent(f'''
                        You are working on task: {task.unique_id} - {task.unique_name}

                        ───────────────────────────────────────────────────────────────────────────────
                        🔹 **Environment & Tools Overview**
                        - Your are getting called over and over again with the new Feedback from tools you use. Until you set done=true.
                        - You have access to a Git repository. Use the `updateFile` field to update or create files.
                        - To delete a file, set its content to `"DELETE"`.
                        - Shell commands are available via the `command` field. Specify them like:
                        - `("gcloud instances list")`
                        - ❗ Avoid using file or git-related commands here.
                        - To retrieve information, use `get_knowledge` like a search engine. It returns summarized and relevant data.
                        • `get_knowledge` returns helpful summarized info—you don’t run it to do things, you run it to learn how.
	                    •  Use it before running any command you’re unsure about, especially ones that might modify state.#
                        ❗ Key Difference:
                		•	get_knowledge = “How do I…?” ➜ Use when you need to learn or confirm how a command works.
                        •	command = “Do this.” ➜ Use when you’re ready to execute something (like gcloud, aws, ...)

                        - ⚠️ You may only call **one tool (`command`, `get_knowledge`, or `update_repo`) at a time**.

                        ───────────────────────────────────────────────────────────────────────────────
                        📁 **Repository Snapshot**
                        You are working inside a Git repo. Here is the current content up to this point:
                        {{REPO_LOAD_FILES}}

                        ───────────────────────────────────────────────────────────────────────────────
                        🎯 **Task Instructions**
                        - **Description:** {task.description}
                        - **Context:** {task.context}
                        - **Result Type:** {task.result_type}

                        📌 Based on the result_type:
                        - If `repo`: Use the `update_repo` field to modify files. The key is the file path, and the value is the **full new content** of the file (not just diffs).
                        - If `text`: Use the `text_result` field to return markdown text output as final output.

                        🔄 Continue using tools (`commands`, `get_knowledge`, `update_repo`) until the task is complete.

                        ✅ When done:
                        - Set `done=true`
                        - Provide a brief and clear summary of what was accomplished in the `message` field.
                        - If `result_type=text`: Use the `text_result` field to return markdown text output as final output (it should include all needed information to answer the task).


                        🚫 Do not provide instructions to the user—*complete the task as the agent*.
                        If a command is required (e.g., listing resources), run it—*do not just describe it*.

                        ───────────────────────────────────────────────────────────────────────────────
                        ⚠️ **Important Execution Rules**
                        - Only **one tool call** (`command`, `get_knowledge`, or `update_repo`) is allowed at a time.
                        - Always **await the result** of that tool call before proceeding or setting `done=true`.

                        🧠 Your role: **{agent.role}** — Solve the task efficiently, accurately, and with minimal explanation unless explicitly requested.  
                ''')).model_dump()
            ]
    add_task_results_recursively(task, tasks, messages, chat)
    
    res =  await litellm_call(
        response_format = ResponseToolCall,
        chat = chat,
        request=task.description,
        messages = messages,
        repo = repo,
        task=task,
        callables = {"REPO_LOAD_FILES": repo.load_files}
    )
    if chat.id not in taskResults:
        taskResults[chat.id] = {}
    if task.result_type == ResultType.TEXT:
        taskResults[chat.id][task.unique_id] = res.text_result
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
            Message(role=Roles.USER.value, content=f'''
            Based on the following request, which schould be of medium complexity, which means a single agent can solve it with the appropriate background, skills and tools. Determine which role, skill, background and tool might be needed. Request:
                    {request}
            ''').model_dump()
    ])

    logger.info(f"Agent {agent}")

    await chat.set_message(f"Starting Agent with role {agent.role} with background '{agent.background}' ... \n\n")
    """
    messages=[
                Message(role=Roles.SYSTEM.value, content=f"You are {agent.role} with background {agent.background} and skill {agent.skills}" ).model_dump(),
                Message(role=Roles.USER.value, content=f'''
                        You are working on a user request but first some context information.
                        The User Request should be medium complexity, which usually means it needs to be broken down into smaller tasks before you can tackle it. But misclassified tasks can happen and it might be easy and you can answer it right away after calling some shell commands or gathering information. 
                        _______________________________________________________
                        Tools:
                        Shell is available via the tool_calls_str.
                        shell(command=git clone) # execute shell commands to create edit files, use cli tools, call APIs
                        whenever you want use the shell use "shell(command=cd clonedDir)" in the tool calls. you can execute multiple shell commands. Just use multiple entries in the tool_calls list.
                        
                        use getKnowledge(query=what is/how to ...) within the tool_calls_str to gather information via websearch, its like a google search which aggregates information.
                        If you are uncertain about the explicit shell commands, for shell commands which only should get information (like cat, ls, gcloud run services list --platform managed) you can always try them right away, there is no harm in that. For shell commands which change the system (like git push, gcloud run deploy) you should be more careful and use getKnowledge to get the information if you are uncertain about the command.

                        You can continue to execute tools. 
                        If the request is easy return done=true, message=a short message to the user with what you have done, and work_result= the answer to the query.
                        if the request is medium complex and needs multiple subtasks just immediately return done=true, message="MEDIUM", and leave work_result blank (work_result="").
                        _______________________________________________________
                        
                        request: 
                        {request}
                ''').model_dump()
            ]
    
    res =  await litellm_call(
        response_format = ResponseToolCall,
        chat = chat,
        request=request,
        messages = messages,
    )
    if res.work_result != "":
        logger.info(f"Agent {agent.role} finished the task with work_result {res.work_result}")
        #await chat.set_message(f"{agent.role}: {res.work_result} \n\n")
        return "fin"
    """
    await chat.set_message(f"{agent.role}: Breaking down your request into subtasks and research steps ... \n\n")
 
    tasks = await litellm_call(
        chat=chat,
        oneShot=True,
        response_format=Tasks,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are {agent.role} with background {agent.background} and skill {agent.skills}").model_dump(),
            Message(role=Roles.USER.value, content=f'''Based on who you are, your background skills and tools. Analyse the request and break it down into multiple subtasks. Just include steps which are necessary to solve the request. Not more. No extra steps, no "nice-to-have". The task result_type is either "text" or "repo". Choose text when it's research and text generation only repo if the task is generating code. Always consider Best practices for the considered tool and workflow you use. If there is a git repo url mentioned return it in repo_url (in modern git ssh format like: git@github.com:agentsphere/agentServer.git ) otherwise leave repo_url blank and return a repo_name fitting for the current request. Request:
                    {request}
            ''').model_dump()
        ],
    )
    #tasks= Tasks(tasks=[Task(unique_id="DE-1",unique_name="Task",description=request,context="",dependsOn=[])])
    await chat.set_message(f"{agent.role} reviewer: Reviewing the task list ... \n\n")


    tasksReviewed = await litellm_call(
        chat=chat,
        oneShot=True,
        response_format=Tasks,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are {agent.role} with background {agent.background} and skill {agent.skills}").model_dump(),
            Message(role=Roles.USER.value, content=f'''
                    The following request is the User request with hopefully some more answers to clarification questions:
                     
                    Original Request: {request}

                    ________________________________________
                    The preivous LLM Agent generated a draft of tasks, and optionally a url to a repo
                    currentTasks: {tasks.model_dump()}

                    ________________________________________
                    Rewivew the output provided by the previous Agent. Does it make sense, try to follow the line of thought for the steps is there something missing? Are the depencies clear. is the task result type correct? is the repo url ( if mentioned in the original request) in the modern git ssh format like: git@github.com:agentsphere/agentServer.git ). Don't answer my questions just improve the generated Draft.
        ''').model_dump()
        ],
    )
    tasks=tasksReviewed
    taskString = "\n\n".join([f"* {task.description}" for task in tasks.tasks]) + "\n\n ... "

    await chat.set_message(f"{agent.role}: Tasks: \n\n {taskString}")
    repo = None
    repoCreated = False

    if (any(task.result_type == ResultType.REPO for task in tasks.tasks)):
        if tasks.repo_url != "":
            await chat.set_message(f"Repo URL: {tasks.repo_url}")
            repo = Repo(url = tasks.repo_url)
        else:
            repoCreated = True
            repo = Repo(name = tasks.repo_name)

    # Creating jira Subtasks, toDO

    for task in tasks.tasks:
        result = await solveSubTask(agent=agent,chat=chat, task=task, repo=repo, tasks=tasks)
    
    if repoCreated:
        await chat.set_message(f"""Work Repo can be downloaded using: 
                                `curl http://localhost:8000/repos/{repo.uuid}/{repo.name} -o {repo.name}.zip`
                                or this link [Download](http://localhost:8000/repos/{repo.uuid}/{repo.name}) """)
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




async def get_clarification_questions(chat: Chat, request: str):
    """
    Generates clarification questions for a given request to gather more context.
    """
    logger.info(f"get_clarification_questions {request}")
    
    response = await litellm.acompletion(
        model=MODEL,
        messages=[
            Message(
                role=Roles.SYSTEM.value,
                content="You are an expert assistant specializing in refining ambiguous or incomplete user requests by asking relevant clarification questions."
            ).model_dump(),
            Message(
                role=Roles.USER.value,
                content=f"""A user submitted the following request:

\"\"\"{request}\"\"\"

Your task is to generate a list of specific, concise clarification questions which are getting forwarded to the user that would help you better understand the user's intent and provide a more accurate response.

Guidelines:
- Focus on missing details or potential ambiguities.
- Do not restate the original request.
- Each question should be direct and no longer than one sentence.
- Avoid yes/no questions when more context is needed.

List the questions addressed to the user:
"""
            ).model_dump()
        ],
    )

    logger.debug(f"clarification response {response}")
    content = response.choices[0].message.content

    await chat.set_message(content)

async def get_clarification_questions(chat: Chat, request: str,  info: str):
    """
    Generates clarification questions for a given request.
    """
    logger.info(f"get_clarification_questions {request}")
    response = await litellm.acompletion(
        model=MODEL,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are a research query specialist").model_dump(),
            Message(role=Roles.USER.value, content=f'''Given the following request: 
                
                    {request}
                    
                    ________________________________________
                    Your senior technical agent took a look at the request and provided the following additional information:
                    {info}
                    
                    ________________________________________

                    Generate a list of clarification questions to ask the user to get more information about the request.
                    Each question should be short and concise.
            ''').model_dump()
        ],
    ) 
    logger.debug(f"solve reponse {response}")
    content = response.choices[0].message.content

    await chat.set_message(content)


async def gatherFirstInfos(chat: Chat, request: str):
    """
    Generates clarification questions for a given request.
    """
    logger.info(f"gatherFirstInfos {request}")
    response = await litellm_call(
        chat=chat,
        response_format=ResponseToolCall,
        messages=[
            Message(role=Roles.SYSTEM.value, content=textwrap.dedent("""
                        You are a senior technical agent tasked with understanding and preparing for complex software infrastructure tasks.

                        🔹 **Your Role:**  
                        You are a skilled DevOps/System Engineer with deep experience in cloud platforms (e.g., GCP, AWS), deployment workflows, infrastructure-as-code, and CI/CD systems. You are methodical and cautious—never taking action without understanding the impact first.

                        🎯 **Current Objective:**  
                        Your task is to **gather all the necessary information** to begin solving the user's request. You are in the **information-gathering phase**, not the execution phase.

                        Use your skills to:
                        - Understand the task fully
                        - Identify what is already known (from repo or outputs)
                        - Find out what’s missing
                        - Use tools to fill in the gaps""")).model_dump(),
            Message(role=Roles.USER.value, content=textwrap.dedent(f'''
                        🧭 You are starting work on a new request: **{request}**

                        ───────────────────────────────────────────────────────────────────────────────
                        🔹 **Your Objective (First Step)**
                        Your current goal is to **understand the task and gather any needed information**.
                        You are allowed to:
                        - Run **non-destructive `command`s** to inspect the system (e.g., `gcloud run services list`)
                        - Use **`get_knowledge`** to look up unknowns or confirm how things work

                        ❗ Do **not** make code changes (`update_repo`) or run modifying commands yet.

                        ───────────────────────────────────────────────────────────────────────────────
                        🛠 **Environment & Tools Overview**
                        - You are called repeatedly with feedback based on tool outputs—continue until you set `done=true`.
                        - You have access to:
                            • `get_knowledge` – for research and learning
                            • `command` – for read-only inspection of the environment

                        ⚠️ Use only one tool at a time. Always await the result before taking further action.

                        ❗ Tool Usage Guidelines:
                        - `get_knowledge` ➜ **To learn** – e.g., “How do I deploy a Cloud Run service?”
                        - `command` ➜ **To inspect** – e.g., `gcloud run services list`, `kubectl get pods`, etc.
                            - ✅ Use commands that gather info or list current state
                            - ❌ Do not run commands that modify or deploy anything (yet)

                        ───────────────────────────────────────────────────────────────────────────────
                        
                        - If `text`: Provide Markdown output via `text_result` at the end

                        ✅ For now:
                        - Investigate the task
                        - Use `command` to gather facts from the system
                        - Use `get_knowledge` to look up anything unfamiliar
                        - Do not yet make code changes or run modifying commands

                        - If you are done set done=true, provide detailed information for further processing with your findings in the text_result field. Leave message empty.
            ''')).model_dump()
        ],
    ) 
    logger.debug(f"solve reponse {response}")
    return response.text_result


async def process_request(chat: Chat, messages: list[Message]):
    """
    Processes a request from a client.
    """
    firstMessage = len(messages)==1

    request = "\n\n".join([f"{msg.role}:{msg.content}" for msg in messages])
    if firstMessage:
        category = await categorizeRequest(chat, request)
        chat.category = category.lvl

    
    logger.info(f"Processing request {request} for chat_id {chat.id}")

    if chat.category:
        if chat.category == DifficultyLevel.EASY:
            await answerRequest(chat, request)
        elif chat.category == DifficultyLevel.MEDIUM or chat.category == DifficultyLevel.COMPLEX:
            if firstMessage:
                info = await gatherFirstInfos(chat, request)
                await get_clarification_questions(chat, request,info)
            else:
                await solveMediumRequest(chat,request)
    await chat.set_message("[DONE]")
    return "fin"
    