import logging
import re
import asyncio

logger = logging.getLogger(__name__)

stream_queues = {}


async def add_to_queue(chat_id: str, msg: str):
    """
    Adds words from the message to the queue one by one with a delay of 0.1 seconds.
    """
    logger.info(f"Adding to queue: {msg} for chat_id: {chat_id}")
    logger.info(f"Current queues: {stream_queues}")

    # Check if the chat_id exists in the stream_queues
    if chat_id in stream_queues:
        # Split the message into words, spaces, and punctuation
        tokens = re.findall(r'\S+|\s+', msg)  # Matches non-whitespace sequences or whitespace sequences
        for token in tokens:
            # Add each token to the queue
            await stream_queues[chat_id].put(token)
            logger.debug(f"Added token to queue: {repr(token)}")  # Use repr to show spaces and special characters
            # Delay of 0.1 seconds
            await asyncio.sleep(0.03)

    return True


def add_queue_for_chat(chat_id: str, queue: asyncio.Queue = None):
    logger.info(f"Adding queue for chat_id: {chat_id} with queue: {queue}")
    if queue is None:
        queue = asyncio.Queue()
    stream_queues[chat_id] = queue

def remove_queue_for_chat(chat_id: str):
    logger.info(f"Removing queue for chat_id: {chat_id}")
    stream_queues.pop(chat_id, None)


