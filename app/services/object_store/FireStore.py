from app.config import logger, settings
from app.services.object_store.ObjectStoreInterface import ObjectStoreInterface
from google.cloud import firestore


class FirestoreDB(ObjectStoreInterface):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(FirestoreDB, cls).__new__(cls)
        return cls._instance

    def __init__(self, collection: str = None):
        """Initialize Firestore client."""
        if not hasattr(self, "_initialized"):
            logger.info("Initializing FirestoreDB")
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(settings.GOOGLE_APPLICATION_CREDENTIALS)
            self.db = firestore.Client(
                project=settings.GCLOUD_PROJECT_ID, database=settings.FIRESTOREDB, credentials=creds
            )
            self.collection = collection
            self._initialized = True

    def find_one(self, query: dict, collection: str = None) -> dict:
        """Find a single document in the Firestore collection."""
        logger.debug(f"Finding one document in collection '{collection}' with query: {query}")
        collection = collection or self.collection
        try:
            docs = self.db.collection(collection).where(
                list(query.keys())[0], "==", list(query.values())[0]
            ).limit(1).stream()
            for doc in docs:
                logger.info(f"Document found in collection '{collection}': {doc.id}")
                return {"id": doc.id, **doc.to_dict()}
            logger.info(f"No document found in collection '{collection}' with query: {query}")
            return None
        except Exception as e:
            logger.error(f"Error finding document in collection '{collection}': {e}")
            raise

    def find(self, query: dict, collection: str = None) -> list[dict]:
        """Find multiple documents in the Firestore collection."""
        logger.debug(f"Finding documents in collection '{collection}' with query: {query}")
        collection = collection or self.collection
        try:
            docs = self.db.collection(collection).where(
                list(query.keys())[0], "==", list(query.values())[0]
            ).stream()
            results = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            logger.info(f"Found {len(results)} documents in collection '{collection}'")
            return results
        except Exception as e:
            logger.error(f"Error finding documents in collection '{collection}': {e}")
            raise

    def insert(self, document: dict, collection: str = None) -> dict:
        """Insert a single document into the Firestore collection."""
        logger.debug(f"Inserting document into collection '{collection}': {document}")
        collection = collection or self.collection
        try:
            doc_ref = self.db.collection(collection).add(document)
            logger.info(f"Document inserted into collection '{collection}' with ID: {doc_ref[1].id}")
            return {"success": True, "document_id": doc_ref[1].id}
        except Exception as e:
            logger.error(f"Error inserting document into collection '{collection}': {e}")
            raise

    def insert_many(self, documents: list[dict], collection: str = None) -> list[dict]:
        """Insert multiple documents into the Firestore collection."""
        logger.debug(f"Inserting multiple documents into collection '{collection}': {documents}")
        collection = collection or self.collection
        inserted_ids = []
        try:
            for document in documents:
                doc_ref = self.db.collection(collection).add(document)
                inserted_ids.append(doc_ref[1].id)
            logger.info(f"Inserted {len(inserted_ids)} documents into collection '{collection}'")
            return {"success": True, "inserted_ids": inserted_ids}
        except Exception as e:
            logger.error(f"Error inserting multiple documents into collection '{collection}': {e}")
            raise

    def delete(self, document: dict, collection: str = None) -> dict:
        """Delete a single document from the Firestore collection."""
        logger.debug(f"Deleting document from collection '{collection}' with ID: {document['id']}")
        collection = collection or self.collection
        try:
            doc_ref = self.db.collection(collection).document(document["id"])
            doc_ref.delete()
            logger.info(f"Document with ID '{document['id']}' deleted from collection '{collection}'")
            return {"success": True, "deleted_count": 1, "document_id": document["id"]}
        except Exception as e:
            logger.error(f"Error deleting document from collection '{collection}': {e}")
            raise

    def delete_many(self, documents: list[dict], collection: str = None) -> dict:
        """Delete multiple documents from the Firestore collection."""
        logger.debug(f"Deleting multiple documents from collection '{collection}': {documents}")
        collection = collection or self.collection
        deleted_ids = []
        try:
            for doc in documents:
                doc_ref = self.db.collection(collection).document(doc["id"])
                doc_ref.delete()
                deleted_ids.append(doc["id"])
            logger.info(f"Deleted {len(deleted_ids)} documents from collection '{collection}'")
            return {"success": True, "deleted_count": len(deleted_ids), "deleted_ids": deleted_ids}
        except Exception as e:
            logger.error(f"Error deleting multiple documents from collection '{collection}': {e}")
            raise


class FireStoreCollection:
    def __init__(self, collection: str):
        """Initialize FireStoreCollection with a specific collection name."""
        self.db = FirestoreDB()  # Use the singleton FirestoreDB instance
        self.collection = collection

    def find_one(self, query: dict) -> dict:
        """Find a single document in the specified Firestore collection."""
        return self.db.find_one(query, collection=self.collection)

    def find(self, query: dict) -> list[dict]:
        """Find multiple documents in the specified Firestore collection."""
        return self.db.find(query, collection=self.collection)

    def insert(self, document: dict) -> dict:
        """Insert a single document into the specified Firestore collection."""
        return self.db.insert(document, collection=self.collection)

    def insert_many(self, documents: list[dict]) -> list[dict]:
        """Insert multiple documents into the specified Firestore collection."""
        return self.db.insert_many(documents, collection=self.collection)

    def delete(self, document: dict) -> dict:
        """Delete a single document from the specified Firestore collection."""
        return self.db.delete(document, collection=self.collection)

    def delete_many(self, documents: list[dict]) -> dict:
        """Delete multiple documents from the specified Firestore collection."""
        return self.db.delete_many(documents, collection=self.collection)