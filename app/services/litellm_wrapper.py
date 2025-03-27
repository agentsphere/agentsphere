


import asyncio
import json
from typing import Dict

import litellm
from pydantic import BaseModel, ValidationError
from app.services.knowledge import getKnowledge
from app.services.queue import add_to_queue
from app.config import logger, settings
from app.models.models import Chat, Message, ResponseToolCall, Roles
from app.services.wss import executeShell




async def litellm_call(
    messages: list[dict[str, any]],
    chat: Chat,
    request: str ="",
    oneShot: bool = False,
    model: str = None,
    response_format: BaseModel = None,
):  
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
                raise ValueError(f"Invalid response format: {content}")
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

            logger.info(f"LLM ResponseRAW: {response}")

            # Parse the response content
            content = response.choices[0].message.content
            logger.info(f"LLM Response Content: {content}")

            try:
                parsed_resp = ResponseToolCall.model_validate(json.loads(content))
                logger.info(f"Parsed Response: {parsed_resp}")

                # Process tool calls
                for tool_call in parsed_resp.tool_calls:
                    tool = tool_call.tool
                    params = tool_call.params

                    # Add tool call notice to chat history
                    tool_message = f"🔧 Toolcall: `{tool}` with params: {params} \n\n"
                    #await chat.set_message(f"🔧 Toolcall: `{tool}` with params: {params}")

                    # Execute the tool
                    try:
                        if tool == "getKnowledge":
                            await chat.set_message(f"🔧 Superman: `{tool}`: {params.get("query", None)}  \n\n")
                            res = await getKnowledge(chat=chat, query=params.get("query", None))
                        elif tool == "shell":
                            res = await executeShell(chat, params.get("command", ""))
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
                        Message(role=Roles.USER, content=f"Given the provided Information by the assistant please give a final answer and set done to True. Request {request}").model_dump()
                    )


                # Check if the task is done
                if parsed_resp.done:
                    await chat.set_message(f"Final Message: {parsed_resp.message} \n\n")
                    return parsed_resp
            except Exception as e:
                logger.error(f"Error parsing LLM response: {e}")
                messages.append(
                        Message(role=Roles.ASSISTANT, content="Your output fomrat is not correct. have got validation error in output").model_dump()
                    )
                
                messages.append(
                        Message(role=Roles.USER, content=f"Please remember the original request. It's probably in the beginning.").model_dump()
                    )

            