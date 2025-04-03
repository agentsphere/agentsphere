from bson.objectid import ObjectId
from pymongo import MongoClient

from app.config import logger, settings
from app.services.object_store.object_store import ObjectStoreInterface

class MongoStore(ObjectStoreInterface):
    def __init__(self, collection: str):
        try:
            logger.info("Initializing MongoStore")
            self.client = MongoClient(settings.MONGO_DB_URI.format(
                MONGO_DB_USER=settings.MONGO_DB_USER,
                MONGO_DB_PASSWORD=settings.MONGO_DB_PASSWORD
            ))
            self.db = self.client[settings.MONGO_DB_NAME]
            self.collection = collection

            logger.info("MongoStore initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing MongoStore: {e}")
            raise

    def find_one(self, query: dict, collection: str = None) -> dict:
        logger.debug("Finding one document in collection '%s' with query: %s", collection, query)
        collection = collection or self.collection
        try:
            result = self.db[collection].find_one(query)
            if result:
                result["_id"] = str(result["_id"])
                logger.info("Document found in collection '%s': %s", collection, result["_id"])
            else:
                logger.info(f"No document found in collection '{collection}' with query: {query}")
            return result
        except Exception as e:
            logger.error(f"Error finding document in collection '{collection}': {e}")
            raise

    def find(self, query: dict, collection: str = None) -> list[dict]:
        logger.debug(f"Finding documents in collection '{collection}' with query: {query}")
        collection = collection or self.collection
        try:
            results = list(self.db[collection].find(query))
            for result in results:
                result["_id"] = str(result["_id"])
            logger.info(f"Found {len(results)} documents in collection '{collection}'")
            return results
        except Exception as e:
            logger.error(f"Error finding documents in collection '{collection}': {e}")
            raise

    def insert(self, document: dict, collection: str = None) -> dict:
        logger.debug(f"Inserting document into collection '{collection}': {document}")
        collection = collection or self.collection
        try:
            result = self.db[collection].insert_one(document)
            logger.info(f"Document inserted into collection '{collection}' with ID: {result.inserted_id}")
            return {"success": True, "document_id": str(result.inserted_id)}
        except Exception as e:
            logger.error(f"Error inserting document into collection '{collection}': {e}")
            raise

    def insert_many(self, documents: list[dict], collection: str = None) -> dict:
        logger.debug(f"Inserting multiple documents into collection '{collection}': {documents}")
        collection = collection or self.collection
        try:
            result = self.db[collection].insert_many(documents)
            logger.info(f"Inserted {len(result.inserted_ids)} documents into collection '{collection}'")
            return {"success": True, "inserted_ids": [str(id) for id in result.inserted_ids]}
        except Exception as e:
            logger.error(f"Error inserting multiple documents into collection '{collection}': {e}")
            raise

    def delete(self, document: dict, collection: str = None) -> dict:
        logger.debug(f"Deleting document from collection '{collection}' with ID: {document['_id']}")
        collection = collection or self.collection
        try:
            result = self.db[collection].delete_one({"_id": ObjectId(document["_id"])})
            if result.deleted_count > 0:
                logger.info(f"Document with ID '{document['_id']}' deleted from collection '{collection}'")
            else:
                logger.warning(f"No document found with ID '{document['_id']}' in collection '{collection}'")
            return {
                "success": result.deleted_count > 0,
                "deleted_count": result.deleted_count,
                "document_id": document["_id"],
            }
        except Exception as e:
            logger.error(f"Error deleting document from collection '{collection}': {e}")
            raise

    def delete_many(self, documents: list[dict], collection: str = None) -> dict:
        logger.debug(f"Deleting multiple documents from collection '{collection}': {documents}")
        collection = collection or self.collection
        try:
            ids = [ObjectId(doc["_id"]) for doc in documents]
            result = self.db[collection].delete_many({"_id": {"$in": ids}})
            logger.info(f"Deleted {result.deleted_count} documents from collection '{collection}'")
            return {
                "success": result.deleted_count > 0,
                "deleted_count": result.deleted_count,
                "deleted_ids": [str(_id) for _id in ids],
            }
        except Exception as e:
            logger.error(f"Error deleting multiple documents from collection '{collection}': {e}")
            raise