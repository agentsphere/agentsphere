import mongomock
from app.config import logger, settings
from app.services.object_store.mongo_store import MongoStore


class MongoLocalStore(MongoStore):
    def __init__(self, collection: str):
        super().__init__(collection)
        logger.info("Getting db connection for collection %s", collection)
        self.client = mongomock.MongoClient()
        self.db = self.client[settings.MONGOMOCK_DB_NAME]
        self.collection = collection
