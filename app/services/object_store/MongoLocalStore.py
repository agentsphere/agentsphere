from app.config import logger, settings
from app.services.object_store.MongoStore import MongoStore


import mongomock


class MongoLocalStore(MongoStore):
    def __init__(self, collection: str):
        logger.info(f"Getting db connection for collection {collection}")
        self.client = mongomock.MongoClient()
        self.db = self.client[settings.MONGOMOCK_DB_NAME]
        self.collection = collection