import asyncio
import json
import re
from textwrap import dedent
from collections import UserDict
import litellm
from pydantic import BaseModel, ValidationError
from app.models.repo import Repo
from app.services.helpers import generate_hash
from app.services.knowledge import get_knowledge
from app.models.models import Task
from app.config import logger, settings
from app.models.models import Chat, Message, ResponseToolCall, ResultType, Roles
from app.services.wss import execute_shell


class Check(BaseModel):
    """
    Model for checking the correctness of the response.
    """
    correct: bool = False
    commit_message: str = None
    feedback: str = None



async def llm_call_wrapper(retry_count=0, max_retrys=3, **kwargs):
    try:
        if not kwargs.get("model"):
            kwargs["model"] = settings.LLM_MODEL
        response = await litellm.acompletion(**kwargs)
        content = response.choices[0].message.content
        if kwargs.get("response_format"):
            return kwargs.get("response_format").model_validate(json.loads(content))
        return content
    except ValueError as e:
        logger.error("Error json decoder error response not valid json: %s", e)
        if retry_count > max_retrys:
            logger.error("Max retries reached. Returning None or raising.")
            raise e  # or return None
        messages = []
        messages.append(
                Message(role=Roles.ASSISTANT, content=f"The output json is not correct. Got validation error in output {str(e)}").model_dump()
            )
        messages.append(
                Message(role=Roles.USER, content=f"fix the following output to meet the requested output format: {content}").model_dump()
            )
        kwargs["messages"] = messages
        return await llm_call_wrapper(retry_count=retry_count + 1, **kwargs)
    except litellm.exceptions.BadRequestError as e:
        logger.error("Error in LLM call, sleep for 5 before retry: %s", e)
        await asyncio.sleep(5)
        if retry_count > max_retrys:
            logger.error("Max retries reached. Returning None or raising.")
            raise e  # or return None
        return await llm_call_wrapper(retry_count=retry_count + 1, **kwargs)

    except ValidationError as e:
        logger.error("Error parsing LLM response: %s", e)
        if retry_count > max_retrys:
            logger.error("Max retries reached. Returning None or raising.")
            raise e  # or return None
        messages = []
        messages.append(
                Message(role=Roles.ASSISTANT, content=f"The output format is not correct. Got validation error in output {str(e)}").model_dump()
            )
        messages.append(
                Message(role=Roles.USER, content=f"fix the following output to meet the requested output format: {content}").model_dump()
            )
        kwargs["messages"] = messages
        return await llm_call_wrapper(retry_count=retry_count + 1, **kwargs)
    except (KeyError, TypeError) as e:  # Replace with specific exceptions
        logger.error("Error parsing LLM response expecting (response.choices[0].message.content): error %s", e)
        logger.error("Error parsing LLM response: %s", response)
        logger.error("Error parsing LLM response, won't retry")
        raise ValueError(f"Invalid response format: {response}") from e


class DefaultPlaceholderDict(UserDict):
    def __missing__(self, key):
        return f'{{{key}}}'
    
# Matches {simple_key} but not {key.with.dot}
PLACEHOLDER_REGEX = re.compile(r'{(\w+)}')


class SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'  # leave unknown placeholder as-is

def update_messages(messages: list[dict[str, any]], callables: dict):
    if callables:
        evaluated_values = {key: func() for key, func in callables.items()}
        placeholder_dict = SafeDict(evaluated_values)

        for msg in messages:
            template = msg.get("content", "")
            # Only replace placeholders that match the keys
            def replacer(match):
                key = match.group(1)
                return str(placeholder_dict.get(key, match.group(0)))

            msg["content"] = PLACEHOLDER_REGEX.sub(replacer, template)


async def execute_tools(commands: list[str], messages: list[dict[str, any]], chat: Chat):
    for command in commands:
        if command.strip() == "":
            continue
        res = await execute_shell(chat, command)
        decoded_response = json.loads(res)

        try:
            terminal_output = decoded_response.get("content")  # Split into status code and the rest of the output
            status_code = decoded_response.get("status_code")  # Extract the numeric status code
        except (ValueError, IndexError) as e:
            logger.error("Failed to parse status code from response: %s. Error: %s", res, e)
            status_code = 0  # Default to an error status if parsing fails

        # Check if the status code is not 0
        if status_code != 0:
            logger.error("Command '%s' failed with status code %s and output: %s", command, status_code, terminal_output)
            messages.append(
                Message(
                    role=Roles.ASSISTANT,
                    content=f"Command failed: you might want to check with get_knowledge the syntax. Command '{command}' failed with status code {status_code}. Output: {terminal_output}"
                ).model_dump()
            )
        else:
            messages.append(
                Message(
                    role=Roles.ASSISTANT,
                    content=f"Command '{command}' success with status code {status_code}. Output: {terminal_output}"
                ).model_dump()
            )


async def llm_tool_call(
    messages: list[dict[str, any]],
    chat: Chat,
    request: str ="",
    model: str = None,
    callables: dict = None,
    repo: Repo = None,
    task: Task = None
):
    last_tool_call_hash = None
    if not model:
        model = settings.LLM_MODEL

    logger.info("LLM Call with messages: %s", messages)

    while True:
        update_messages(messages, callables)
        parsed_resp = await llm_call_wrapper(model=model,
            response_format=ResponseToolCall,
            messages=messages
        )

        current_hash = generate_hash("".join(parsed_resp.commands))
        if last_tool_call_hash is not None and current_hash == last_tool_call_hash and parsed_resp.done:
            logger.info("Duplicate tool call detected. Skipping execution. done %s", parsed_resp.done)
        else:
            commands = [command for command in parsed_resp.commands if command.strip() != ""]
            parsed_resp.done= False if commands else parsed_resp.done
            await execute_tools(commands=commands, messages=messages, chat=chat)

        queries = [query for query in parsed_resp.get_knowledge if query.strip() != ""]

        for query in queries:
            try:
                if chat:
                    await chat.set_message(f"🔧 `getKnowledge`: {query}  \n\n")
                message_content = f"{'\n\n'.join(await get_knowledge(chat=chat, query=query))}"

                if chat:
                    await chat.set_message(f"{message_content}  \n\n")

            except (KeyError, ValueError, RuntimeError) as e:  # Replace with specific exceptions
                message_content = f"❌ Tool `getKnowledge` execution failed for query {query}. Error: {str(e)}"
                logger.error("Error executing tool 'getKnowledge' with query %s: %s", query, e)

            # Log and append the result
            logger.info("Appending message to messages: %s", message_content)
            messages.append(
                Message(role=Roles.ASSISTANT, content=message_content).model_dump()
            )
        if repo is None and parsed_resp.repo_update:
            logger.warning("Repository is None but repo_update is provided. Please provide a valid repository.")
        elif repo is not None and parsed_resp.repo_update:
            # Update the repository with the provided updates
            logger.info("Updating repository with: %s", parsed_resp.repo_update)
            if chat:
                filenames = "\n".join(parsed_resp.repo_update.keys())
                await chat.set_message(f"🔧 `updating files`\n\n{filenames}")
            repo.update_files(parsed_resp.repo_update)
        messages.append(
            Message(role=Roles.USER, content=dedent("Given the provided Information by the assistant continue your work process")).model_dump()
        )
        # Check if the task is done
        if parsed_resp.done:
            await chat.set_message(f"{parsed_resp.message} \n\n")
            await chat.set_message(f"{parsed_resp.text_result} \n\n")


            if task is None:
                return parsed_resp

            # Define the mapping for result_type-specific content
            result_type_mapping = {
                ResultType.REPO: f"""Check following git diff if it solves the task. if diff is empty it probably is not solving the task. Diff:{repo.get_diff()}

                if it solves the task provide a commit_message for the changes.
                
                current Repo is: 
                {repo.load_files()}""",
                ResultType.TEXT: f"""Check the work result text if it answers/solves the request/task.
                Message:  {parsed_resp.message}
                
                Result:  {parsed_resp.text_result}""",
            }


            message_check = [Message(role=Roles.USER, content=f"""Given Following message and work result:
                            result_type = {task.result_type}

                            {result_type_mapping.get(task.result_type, "")}
                            
                            Please check if it's correctly solving or answering the original request. Just return correct == True or correct == False. If False, give a short feedback why it is not correct.

                            Origianal request: {request}
            
                            """).model_dump()]

            #double check
            logger.info("Double checking the response with messages: %s", message_check)

            check_response = await llm_call_wrapper(
                model=model,
                response_format=Check,
                messages=message_check,
            )
            if check_response.correct:
                repo.add_and_commit(check_response.commit_message)
                return parsed_resp
            messages.append(
                Message(role=Roles.USER, content=dedent(f"""
                    Your result does not seem to answer or solve my original question. 
                    Feedback {check_response.feedback} Please check again using your available tools""")).model_dump())
