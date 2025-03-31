


import asyncio
import hashlib
import json
from typing import Dict

import litellm
from pydantic import BaseModel, ValidationError
from app.services.knowledge import getKnowledge
from app.services.queue import add_to_queue
from app.config import logger, settings
from app.models.models import Chat, Message, ResponseToolCall, Roles
from app.services.wss import executeShell


class Check(BaseModel):
    """
    Model for checking the correctness of the response.
    """
    correct: bool = False


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
                currentHash = generate_hash("".join(parsed_resp.tool_calls_str))
                if last_tool_call_hash is not None and currentHash == last_tool_call_hash:
                    logger.info(f"Duplicate tool call detected. Skipping execution. don {parsed_resp.done}")
                else:
                    for tool_call in parsed_resp.tool_calls:                        
                        parsed_resp.done= False
                        tool = tool_call.tool
                        params = tool_call.params

                        # Add tool call notice to chat history
                        tool_message = f"🔧 Toolcall: `{tool}` with params: {params} \n\n"
                        #await chat.set_message(f"🔧 Toolcall: `{tool}` with params: {params}")
                        message_content = f"{tool_message}"

                        # Execute the tool
                        try:
                            if tool == "getKnowledge":
                                await chat.set_message(f"🔧 Superman: `{tool}`: {params.get("query", None)}  \n\n")
                                res = '\n\n'.join(await getKnowledge(chat=chat, query=params.get("query", None)))
                                message_content = f"{res}"
                            elif tool == "shell":
                                res = await executeShell(chat, params.get("command", ""))
                                message_content = f"shell execution '{params.get("command", "")}' with result {res}"
                            #else:
                            #    res = await execute_tool(user, tool, params=params)

                            # Prepare response message
                            message_content = f"{res}"
                        except Exception as e:
                            message_content = f"❌ Tool `{tool}` execution failed with params {params}. Error: {str(e)}"
                            logger.exception(f"Error executing tool '{tool}'")

                        # Log and append the result
                        logger.info(f"Appending message to messages: {message_content}")
                        messages.append(
                            Message(role=Roles.ASSISTANT, content=message_content).model_dump()
                        )
                        messages.append(
                            Message(role=Roles.USER, content=f"Given the provided Information by the assistant please give a final answer with message and work_result and set done to True. Request {request}").model_dump()
                        )


                # Check if the task is done
                if parsed_resp.done:
                    await chat.set_message(f"{parsed_resp.message} \n\n")
                    await chat.set_message(f"{parsed_resp.work_result} \n\n")

                    messageCheck = []

                    messageCheck.append(
                            Message(role=Roles.USER, content=f"""Given Following message and work result: 
                                    
                                    Message to User {parsed_resp.message} 
                                    
                                    
                                    work result: {parsed_resp.work_result}


                                    Please check if it's correctly solving or answering the original request. Just return correct == True or correct == False. No other text.
                                    {request}).model_dump()

                                    """).model_dump()
                        )
                    #double check
                    resCheck = await litellm.acompletion(
                        model=model,
                        response_format=Check,
                        messages=messageCheck,
                    )

                    logger.info(f"LLM ResponseRAW: {resCheck}")

                    # Parse the response content
                    contentC = resCheck.choices[0].message.content
                    logger.info(f"LLM Response Content: {contentC}")

                    parsed_respC = Check.model_validate(json.loads(content))
                    if parsed_respC:
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

            