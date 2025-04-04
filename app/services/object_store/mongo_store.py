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
            logger.error("Error initializing MongoStore: %s", e)
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
                logger.info("No document found in collection '%s' with query: %s", collection, query)
            return result
        except Exception as e:
            logger.error("Error finding document in collection '%s': %s", collection, e)
            raise

    def find(self, query: dict, collection: str = None) -> list[dict]:
        logger.debug("Finding documents in collection '%s' with query: %s", collection, query)
        collection = collection or self.collection
        try:
            results = list(self.db[collection].find(query))
            for result in results:
                result["_id"] = str(result["_id"])
            logger.info("Found %d documents in collection '%s'", len(results), collection)
            return results
        except Exception as e:
            logger.error("Error finding documents in collection '%s': %s", collection, e)
            raise

    def insert(self, document: dict, collection: str = None) -> dict:
        logger.debug("Inserting document into collection '%s': %s", collection, document)
        collection = collection or self.collection
        try:
            result = self.db[collection].insert_one(document)
            logger.info("Document inserted into collection '%s' with ID: %s", collection, result.inserted_id)
            return {"success": True, "document_id": str(result.inserted_id)}
        except Exception as e:
            logger.error("Error inserting document into collection '%s': %s", collection, e)
            raise

    def insert_many(self, documents: list[dict], collection: str = None) -> dict:
        logger.debug("Inserting multiple documents into collection '%s': %s", collection, documents)
        collection = collection or self.collection
        try:
            result = self.db[collection].insert_many(documents)
            logger.info("Inserted %d documents into collection '%s'", len(result.inserted_ids), collection)
            return {"success": True, "inserted_ids": [str(id) for id in result.inserted_ids]}
        except Exception as e:
            logger.error("Error inserting multiple documents into collection '%s': %s", collection, e)
            raise

    def delete(self, document: dict, collection: str = None) -> dict:
        logger.debug("Deleting document from collection '%s' with ID: %s", collection, document["_id"])
        collection = collection or self.collection
        try:
            result = self.db[collection].delete_one({"_id": ObjectId(document["_id"])})
            if result.deleted_count > 0:
                logger.info("Document with ID '%s' deleted from collection '%s'", document["_id"], collection)
            else:
                logger.warning("No document found with ID '%s' in collection '%s'", document["_id"], collection)
            return {
                "success": result.deleted_count > 0,
                "deleted_count": result.deleted_count,
                "document_id": document["_id"],
            }
        except Exception as e:
            logger.error("Error deleting document from collection '%s': %s", collection, e)
            raise

    def delete_many(self, documents: list[dict], collection: str = None) -> dict:
        logger.debug("Deleting multiple documents from collection '%s': %s", collection, documents)
        collection = collection or self.collection
        try:
            ids = [ObjectId(doc["_id"]) for doc in documents]
            result = self.db[collection].delete_many({"_id": {"$in": ids}})
            logger.info("Deleted %d documents from collection '%s'", result.deleted_count, collection)
            return {
                "success": result.deleted_count > 0,
                "deleted_count": result.deleted_count,
                "deleted_ids": [str(_id) for _id in ids],
            }
        except Exception as e:
            logger.error("Error deleting multiple documents from collection '%s': %s", collection, e)
            raise
