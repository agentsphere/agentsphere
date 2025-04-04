import json
from textwrap import dedent
from typing import Optional
import litellm
from pydantic import BaseModel, Field

from app.config import logger, settings

from app.models.models import Agent, ClarificationQuestion, ClarificationQuestions, ResultType
from app.models.models import Task
from app.models.models import Tasks
from app.models.models import DifficultyLevel
from app.models.repo import Repo
from app.models.models import Chat, Roles
from app.services.llm_wrapper import llm_call_wrapper, llm_tool_call


TOKEN=settings.TOKEN
MODEL=settings.LLM_MODEL

class CategoryResponse(BaseModel):
    """
    Represents the response model for a category classification.
    """
    lvl: DifficultyLevel = Field(description="The difficulty level of the category.")
    

class Message(BaseModel):
    role: str
    content: str

taskResults = {}


async def categorize_request(chat: Chat):
    """
    Categorizes a Request using LLM
    """
    logger.info("Categorize Request %s", chat.original_request)
    await chat.set_message("Let me check how complex your request is... \n\n")

    c = await llm_call_wrapper(
        response_format=CategoryResponse,
        messages = [
            Message(
                role=Roles.SYSTEM.value,
                content=f"Your task is to categorize the following user request based on complexity, using this format: {CategoryResponse.__doc__}").model_dump(),
            Message(
                role=Roles.USER.value,
                content=dedent(f'''
                    Please categorize the following request into one of three levels of complexity:

                    - **Easy**: Tasks that involve straightforward information gathering (even from multiple sources) or simple text generation. 
                        The response can be given immediately after collecting the necessary information.
                    - **Medium**: Tasks that require specialized background knowledge or expertise, but can be completed by a single person.
                    - **Complex**: Tasks that require coordination among multiple individuals or roles, typically needing a team effort.

                    If you are uncertain about the appropriate category, a second agent will review your classification.

                    Request:
                    {chat.original_request}
                    ''')).model_dump()
    ])

    logger.debug("c %s", c)
    await chat.set_message(f"Category: {c.lvl} \n\n ")
    return c


async def answer_request(chat: Chat):
    """
    Categorizes a Request using LLM
    """

    logger.info("Answer Request %s", chat.original_request)
    await chat.set_message("Gathering information ... \n\n")

    return await llm_tool_call(
        chat=chat,
        request=chat.original_request,
        messages = [
            Message(role=Roles.SYSTEM.value, content="Answer Request").model_dump(),
            Message(role=Roles.USER.value, content=
                dedent(f'''
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
                    {chat.original_request}
                ''')).model_dump()
        ]
    )

def add_task_results_recursively(task, messages, chat: Chat):
    if not task.dependsOn:
        return

    for dep_id in task.dependsOn:
        dep_task = next((t for t in chat.tasks.tasks if t.unique_id == dep_id), None)
        if dep_task is None:
            logger.warning("Dependency %s not found in tasks", dep_id)
            continue
        logger.info("Dependency %s found in tasks", dep_id)

        # First, recurse into dependencies of this dependency
        add_task_results_recursively(dep_task, messages, chat)

        # Then, add result message for this dependency if it's a text result
        if dep_task.result_type == ResultType.TEXT:
            result = taskResults.get(chat.id, {}).get(dep_id, None)
            if result is not None:
                messages.append(Message(
                    role=Roles.ASSISTANT.value,
                    content=f"Task Dependency:{dep_id} was solved with result: {result}"
                ).model_dump())
            else:
                logger.warning("Dependency %s not yet solved", dep_id)
                messages.append(Message(
                    role=Roles.ASSISTANT.value,
                    content=f"Task Dependency:{dep_id} not yet solved, you can still try to solve yours"
                ).model_dump())


async def solve_tasks(agent:Agent, chat: Chat, repo: Repo):
    for task in chat.tasks.tasks:
        logger.info("task %s", task)
        await chat.set_message(f"{agent.role}: Solving subtask {task.description} \n\n")

        messages=[
            Message(role=Roles.SYSTEM.value, content=dedent(f"""
                You are {agent.role} with background {agent.background} and skills {agent.skills}
                the overall project description is: {chat.project_description}
                """)).model_dump(),
            Message(role=Roles.USER.value, content=dedent(f'''
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
        add_task_results_recursively(task, messages, chat)

        res =  await llm_tool_call(
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


async def solve_medium_request(chat: Chat):
    """Solves a Request Medium complexity"""

    logger.info("solve_medium_request %s", chat.project_description)
    await chat.set_message("Finding best candidate to solve your request ... \n\n")


    agent = await llm_call_wrapper(
        response_format=Agent,
        messages = [
            Message(role=Roles.SYSTEM.value, content="You are a Manager").model_dump(),
            Message(role=Roles.USER.value, content=dedent(f'''
                Based on the following request, which schould be of medium complexity, which means a single agent can solve it with the appropriate background, skills and tools. 
                Determine which role, skill, background and tool might be needed. Request:
                    {chat.project_description}
            ''')).model_dump()
    ])

    logger.info("Agent %s", agent)

    await chat.set_message(f"Starting Agent with role {agent.role} with background '{agent.background}' ... \n\n")

    await chat.set_message(f"{agent.role}: Breaking down project into taks and research steps ... \n\n")

    tasks = await llm_call_wrapper(
        response_format=Tasks,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are {agent.role} with background {agent.background} and skill {agent.skills}").model_dump(),
            Message(role=Roles.USER.value, content=dedent(f'''Based on who you are, your background skills and tools. Analyse the request and break it down into multiple subtasks.
                    Just include steps which are necessary to solve the request. Not more. No extra steps, no "nice-to-have". The task result_type is either "text" or "repo". 
                    Choose text when it's research and text generation only repo if the task is generating code. Always consider Best practices for the considered tool and workflow you use. 
                    If there is a git repo url mentioned return it in repo_url (in modern git ssh format like: git@github.com:agentsphere/agentServer.git ) otherwise leave repo_url blank and return a repo_name fitting for the current request. Request:
                    {chat.project_description}
            ''')).model_dump()
        ],
    )
    #tasks= Tasks(tasks=[Task(unique_id="DE-1",unique_name="Task",description=request,context="",dependsOn=[])])
    await chat.set_message(f"{agent.role} reviewer: Reviewing the task list ... \n\n")


    tasks_reviewed = await llm_call_wrapper(
        response_format=Tasks,
        messages=[
            Message(role=Roles.SYSTEM.value, content=f"You are {agent.role} with background {agent.background} and skill {agent.skills}").model_dump(),
            Message(role=Roles.USER.value, content=dedent(f'''
                    The following request is the User request with hopefully some more answers to clarification questions:
                     
                    Original Request: {chat.project_description}

                    ________________________________________
                    The preivous LLM Agent generated a draft of tasks, and optionally a url to a repo
                    currentTasks: {tasks.model_dump()}

                    ________________________________________
                    Review the output provided by the previous Agent. Does it make sense, try to follow the line of thought for the steps is there something missing? Add it.
                    Are the task dependencies clear. is the task result type correct? is the repo url ( if mentioned in the original request) in the modern git ssh format like: git@github.com:agentsphere/agentServer.git ). 
                    Don't answer my questions just improve the generated Draft.
        ''')).model_dump()
        ],
    )
    tasks=tasks_reviewed
    task_string = "\n\n".join([f"* {task.description}" for task in tasks.tasks]) + "\n\n ... "

    await chat.set_message(f"{agent.role}: Tasks: \n\n {task_string}")
    repo = None
    repo_created = False

    if any(task.result_type == ResultType.REPO for task in tasks.tasks):
        if tasks.repo_url != "":
            await chat.set_message(f"Repo URL: {tasks.repo_url}")
            repo = Repo(url = tasks.repo_url)
        else:
            repo_created = True
            repo = Repo(name = tasks.repo_name)

    # Creating jira Subtasks, toDO
    chat.tasks = tasks

    await solve_tasks(agent=agent,chat=chat, repo=repo)

    if repo_created:
        await chat.set_message(dedent(f"""Work Repo can be downloaded using:
                                `curl http://localhost:8000/repos/{repo.uuid}/{repo.name} -o {repo.name}.zip`
                                or this link [Download](http://localhost:8000/repos/{repo.uuid}/{repo.name}) """))
    return "fin"

class Queries(BaseModel):
    queries: Optional[list[str]] = Field(default = None, description="A list of query strings to be processed.")


def get_queries_for_document(doc, query):
    logger.info("getQueriesForDocument %s %s", doc[:100], query)
    response = litellm.completion(
        model=MODEL,
        response_format=Queries,
        messages=[
            Message(role=Roles.SYSTEM.value, content="You are a research query specialist").model_dump(),
            Message(role=Roles.USER.value, content=dedent(f'''Given the following Documentation:
                
                    {doc}
                    
                    ________________________________________

                    Return a list of short search queries users and ai agents might use to search for the provided information in the documentation.
                    Each search query should contain 8-15 words
                    If the following query can be used to find relevant information in the documentation, add it to your list of queries. 
                    But please only add the query if the answer is not the page. The Documentation is maybe just a subpage and a different page might be better suited to answer the query:
                    {query}
            ''')).model_dump()
        ],
    )
    logger.debug("solve reponse %s", response)
    content = response.choices[0].message.content

    queries = Queries.model_validate(json.loads(content))
    return queries


async def get_clarification_questions(chat: Chat):
    """
    Generates clarification questions for a given request to gather more context.
    """
    logger.info("%s", chat.original_request)

    response = await llm_call_wrapper(response_format=ClarificationQuestions,messages=[
            Message(
                role=Roles.SYSTEM.value,
                content="You are an expert assistant specializing in refining ambiguous or incomplete user requests by asking relevant clarification questions."
            ).model_dump(),
            Message(
                role=Roles.USER.value,
                content=dedent(f"""A user submitted the following request:

                    \"\"\"{chat.original_request}\"\"\"

                    Your coworker took a look at the request and provided some information about the task.
                    \"\"\"{chat.info}\"\"\"

                    Your task is to generate a list of specific, concise clarification questions addressed to the user that would help you better understand the user's request.

                    Guidelines:
                    - Focus on missing details or potential ambiguities.
                    - Do not restate the original request.
                    - Each question should be direct and no longer than one sentence.
                    - Avoid yes/no questions when more context is needed.

                    List the questions addressed to the user:
                    """
            )).model_dump()
        ],
    )
    logger.debug("response: %s", response)
    open_questions = "\n".join(
        [f"{q.number}: {q.question}" for q in response.questions]
    )

    await chat.set_message(open_questions)
    return response.questions


async def gather_first_infos(chat: Chat):
    """
    Generates clarification questions for a given request.
    """
    logger.info("gatherFirstInfos %s", chat.original_request)
    response = await llm_tool_call(
        chat=chat,
        messages=[
            Message(role=Roles.SYSTEM.value, content=dedent("""
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
            Message(role=Roles.USER.value, content=dedent(f'''
                        🧭 You are starting work on a new request: **{chat.original_request}**

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

                        - If you are done set done=true, provide detailed information for further processing with your findings in the text_result field. 
                        - Following Agents only can see the text provided in text_result, so be verbose here and add any findings you have. Leave message empty.
            ''')).model_dump()
        ],
    )
    logger.debug("solve reponse %s", response)
    return response.text_result




async def merge_questions_with_response(questions: list[ClarificationQuestion], user_response: str):
    """
    Merges the clarification questions with the response from the LLM.
    """
    logger.info("Merging questions with response")
    if any(q.status == "open" for q in questions):
        open_questions = "\n".join(
            [f"{q.number}: {q.question}" for q in questions if q.status == "open"]
        )
        return await llm_call_wrapper(response_format=ClarificationQuestions, messages=[
                Message(role=Roles.SYSTEM.value, content="You are an expert assistant").model_dump(),
                Message(role=Roles.USER.value, content=dedent(f'''
                    For a given set of clarification questions and a user response, extract the relevant information from the user response and add it to the corresponding clarification question object. 
                    
                    clarification questions are:
                    {open_questions}

                    user response is:
                    {user_response}

                    Try to extract the information from the user response and add it to the corresponding clarification question object.
                    Not all questions might be answered, so just add the information you can find in the user response to the corresponding clarification question object.
                    If the user response does not contain any information for a clarification question, just return the original clarification question object without any changes.
                    If the user response contains information for a clarification question, add it to the corresponding clarification question object and set the status to "answered".                                          
                ''')).model_dump()
            ],
        )
    return questions

async def get_project_description(chat: Chat):
    """
    Generates a project description for a given request.
    """
    logger.info("getProjectDescription %s", chat.original_request)
    questions = "\n".join(
        [f"{q.number}: {q.question} \n {q.answer} \n" for q in chat.clarification_questions if q.status == "answered"]
    )
    return await llm_call_wrapper(
        messages=[
            Message(
                role=Roles.SYSTEM.value,
                content=dedent("""
                    You are a senior technical writer and project analyst tasked with synthesizing all gathered information into a detailed, structured project specification.

                    🔹 **Your Role:**
                    You are a skilled **Technical Project Analyst** with experience in software architecture, DevOps practices, and technical writing. Your expertise is in converting informal and technical inputs into clear, actionable project specifications that guide engineering work.

                    🎯 **Current Objective:**
                    Use the gathered context—including the original user request and clarified details—to draft a complete **Project Specification** that will be handed off to the implementation team.

                    Include the following in your output:
                    - ✅ A short summary of the original request
                    - ✅ A bullet list of clarified requirements and expectations
                    - ✅ Any assumptions you've had to make
                    - ✅ Key risks, dependencies, or open questions
                    - ✅ Final detailed project description and scope

                    🔎 **How You Work:**
                    - Focus on **clarity, completeness, and structure**.
                    - Use your architectural background to fill in any small gaps using best practices.
                    - Be explicit about open questions or assumptions—flag anything that needs verification.
                    - Output everything in a Markdown section titled `text_result`.

                    ‼️ Do not take further actions beyond creating this summary. This is a handoff point.
                """)
            ).model_dump(),
            Message(
                role=Roles.USER.value,
                content=dedent(f"""
                    A user submitted the following request:

                    \"\"\"{chat.original_request}\"\"\"

                    Here is the additional context provided by a senior technical analyst:
                    \"\"\"{chat.info}\"\"\"

                    Here is the list of clarification questions and their answers:
                    \"\"\"{questions}\"\"\"

                    Use this information to generate a full but concise project specification that covers everything needed to begin implementation work. Include any links from the original request.
                """)
            ).model_dump()
                    ],
    )


async def process_request(chat: Chat, messages: list[Message]):
    """
    Processes a request from a client.
    """
    logger.info("Processing request %s for chat_id %s", messages[0].content[:80], chat.id)
    first_message = len(messages)==1

    #request = "\n\n".join([f"{msg.role}:{msg.content}" for msg in messages])
    if first_message:
        chat.original_request = messages[0].content
        category = await categorize_request(chat)
        chat.category = category.lvl


    if chat.category:
        if chat.category == DifficultyLevel.EASY:
            await answer_request(chat)
        else:
            if first_message:
                chat.info = await gather_first_infos(chat)
                chat.clarification_questions = await get_clarification_questions(chat)

            if any(q.status == "open" for q in chat.clarification_questions):
                chat.clarification_questions = merge_questions_with_response(chat.clarification_questions, messages[-1].content)
                if any(q.status == "open" for q in chat.clarification_questions):
                    open_questions = "\n".join(
                        [f"{q.number}: {q.question}" for q in chat.clarification_questions if q.status == "open"]
                    )
                    await chat.set_message(f"Please answer the following open questions to clarify your request: {open_questions} \n\n")
            else:
                chat.project_description = await get_project_description(chat)
                await chat.set_message(f"Revised Task Description: {chat.project_description} \n\n")
                await solve_medium_request(chat)
    await chat.set_message("[DONE]")
    return "fin"
