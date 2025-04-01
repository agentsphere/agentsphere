


import asyncio
import hashlib
import json
from typing import Dict

import litellm
from pydantic import BaseModel, ValidationError
from app.models.repo import Repo
from app.services.knowledge import getKnowledge
from app.models.models import Task
from app.services.queue import add_to_queue
from app.config import logger, settings
from app.models.models import Chat, Message, ResponseToolCall, ResultType, Roles
from app.services.wss import executeShell


class Check(BaseModel):
    """
    Model for checking the correctness of the response.
    """
    correct: bool = False
    commit_message: str = None


def generate_hash(doc: str) -> str:
    """
    Generate a unique hash based on the document content and URL.
    """
    hash_input = doc.encode('utf-8')
    return hashlib.md5(hash_input).hexdigest()

async def litellm_call(
    messages: list[dict[str, any]],
    chat: Chat,
    request: str ="",
    oneShot: bool = False,
    model: str = None,
    callables: dict = None,
    repo: Repo = None,
    task: Task = None,
    response_format: BaseModel = None,
):  
    last_tool_call_hash = None
    if not model:
        model = settings.LLM_MODEL

    logger.info(f"LLM Call with messages: {messages}")
    if oneShot:
        logger.info("One-shot LLM call")
        response = await litellm.acompletion(
            model=model,
            response_format=response_format,
            messages=messages,
        )
        logger.info(f"LLM ResponseRAW: {response}")
        try:
            content = response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            raise ValueError(f"Invalid response format: {response}")
        logger.info(f"LLM Response Content: {content}")

        if response_format:
            try:
                return response_format.model_validate(json.loads(content))
            except ValidationError as e:
                logger.error(f"Error parsing LLM response: {e}")
                messages = []
                messages.append(
                        Message(role=Roles.ASSISTANT, content=f"The output format is not correct. Got validation error in output {str(e)}").model_dump()
                    )
                messages.append(
                        Message(role=Roles.USER, content=f"fix the following output to meet the requested output format: {content}").model_dump()
                    )
                return await litellm_call(messages=messages, chat=chat, request=request, oneShot=oneShot, model=model, response_format=response_format)
            except Exception as e:
                logger.error(f"Other error parsing LLM response: {e}")
                raise ValueError(f"Invalid response format: {content}")
        else:
            return content
    else:   

        if callables:
            evaluated_values = {key: func() for key, func in callables.items()}

            # Replace placeholders in the template using str.format
            for msg in messages:
                template = msg.get("content", "")
                msg["content"] = template.format(**evaluated_values)
            logger.info(f"LLM Call with updated messages: {messages}")
        while True:
            # Call the LLM
            response = await litellm.acompletion(
                model=model,
                response_format=ResponseToolCall,
                messages=messages,
            )
            #await asyncio.sleep(12)

            logger.info(f"LLM ResponseRAW: {response}")

            # Parse the response content
            content = response.choices[0].message.content
            logger.info(f"LLM Response Content: {content}")

            try:
                parsed_resp = ResponseToolCall.model_validate(json.loads(content))
                logger.info(f"Parsed Response: {parsed_resp}")

                # Process tool calls
                currentHash = generate_hash("".join(parsed_resp.commands))
                if last_tool_call_hash is not None and currentHash == last_tool_call_hash:
                    logger.info(f"Duplicate tool call detected. Skipping execution. don {parsed_resp.done}")
                else:
                    for command in parsed_resp.commands: 
                        if command.strip() == "":
                            continue                       
                        parsed_resp.done= False
                        res = await executeShell(chat, command)
                        try:
                            status_code, terminal_output = res.split(",", 1)  # Split into status code and the rest of the output
                            status_code = int(status_code.strip().split(" ")[-1])  # Extract the numeric status code
                        except (ValueError, IndexError) as e:
                            logger.error(f"Failed to parse status code from response: {res}. Error: {e}")
                            status_code = 0  # Default to an error status if parsing fails

                        # Check if the status code is not 0
                        if status_code != 0:
                            logger.error(f"Command '{command}' failed with status code {status_code} and output: {terminal_output}")
                            # ToDO: Maybe fix it right here?
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
                for query in parsed_resp.get_knowledge:
                    if query.strip() == "":
                        continue
                    try:
                        await chat.set_message(f"🔧 `getKnowledge`: {query}  \n\n")
                        res = '\n\n'.join(await getKnowledge(chat=chat, query=query))
                        message_content = f"{res}"
                    except Exception as e:
                        message_content = f"❌ Tool `getKnowledge` execution failed for query {query}. Error: {str(e)}"
                        logger.exception(f"Error executing tool 'getKnowledge' with query {query}: {e}")

                    # Log and append the result
                    logger.info(f"Appending message to messages: {message_content}")
                    messages.append(
                        Message(role=Roles.ASSISTANT, content=message_content).model_dump()
                    )
                if repo is None and parsed_resp.repo_update:
                    logger.warning(f"Repository is None but repo_update is provided. Please provide a valid repository.")
                elif repo is not None and parsed_resp.repo_update:
                    # Update the repository with the provided updates
                    logger.info(f"Updating repository with: {parsed_resp.repo_update}")
                    await chat.set_message(f"🔧 `updateRepo` \n\n")
                    repo.update_files(parsed_resp.repo_update)
                messages.append(
                    Message(role=Roles.USER, content=f"Given the provided Information by the assistant please give a final answer with message and work_result and set done to True. Request {request}").model_dump()
                )

 


                # Check if the task is done
                if parsed_resp.done:
                    await chat.set_message(f"{parsed_resp.message} \n\n")
                    await chat.set_message(f"{parsed_resp.text_result} \n\n")

                    messageCheck = []

                    if task is None:
                        return parsed_resp
                    
                    # Define the mapping for result_type-specific content
                    result_type_mapping = {
                        ResultType.REPO: f"""Check following git diff if it solves the task. if diff is empty it probably is not solving the task. Diff:{repo.get_diff()} 
        
                        if it solves the task provide a commit_message for the changes.""",
                        ResultType.TEXT: f"Check the work result text if it answers/solves the request/task. Message:  {parsed_resp.message} Result  {parsed_resp.text_result}",
                    }


                    messageCheck.append(
                            Message(role=Roles.USER, content=f"""Given Following message and work result: 
                                    result_type = {task.result_type}
                                    
                                    {result_type_mapping.get(task.result_type, "")} 
                                    
                                    Please check if it's correctly solving or answering the original request. Just return correct == True or correct == False. No other text.

                                    Origianal request: {request}
                    
                                    """).model_dump()
                        )
                    #double check
                    logger.info(f"Double checking the response with messages: {messageCheck}")
                    resCheck = await litellm.acompletion(
                        model=model,
                        response_format=Check,
                        messages=messageCheck,
                    )

                    logger.info(f"LLM ResponseRAW: {resCheck}")

                    # Parse the response content
                    contentC = resCheck.choices[0].message.content
                    logger.info(f"LLM Response Content: {contentC}")

                    parsed_respC = Check.model_validate(json.loads(contentC))
                    if parsed_respC:
                        repo.add_and_commit(parsed_respC.commit_message)
                        return parsed_resp
                    else:   
                        messages.append(
                            Message(role=Roles.USER, content="Your result does not seem to answer or solve my original question. Please double check using you available tools").model_dump()
                        )
            except Exception as e:
                logger.error(f"Error parsing LLM response: {e}")
                messages.append(
                        Message(role=Roles.ASSISTANT, content="Your output format is not correct. have got validation error in output").model_dump()
                    )
                
                messages.append(
                        Message(role=Roles.USER, content=f"Please remember the original request. It's probably in the beginning.").model_dump()
                    )

            