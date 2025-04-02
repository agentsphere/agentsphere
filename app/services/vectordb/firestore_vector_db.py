from google.cloud import firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from app.services.vectordb.vector_db import VectorDBInterface
from app.config import logger, settings

class FirestoreVectorDB(VectorDBInterface):
    def __init__(self, collection_name: str):
        """Initialize Firestore client and collection."""
        logger.info(f"Initializing FirestoreVectorDB with collection: {collection_name}")

        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(settings.GOOGLE_APPLICATION_CREDENTIALS)
        self.db = firestore.Client(project="psyched-option-454007-u6", database=settings.FIRESTOREDB, credentials=creds)
        self.collection = self.db.collection(collection_name)

    def query(self, vector: list[list[float]], query_params: dict[str, any] = None) -> list[list[dict[str, any]]]:
        """
        Query the Firestore vector database using a vector and optional additional query parameters.

        Args:
            vector (List[float]): The vector to query the database with.
            query_params (Dict[str, Any], optional): Additional query parameters.

        Returns:
            List[Dict[str, Any]]: A list of results, where each result is represented as a dictionary.
        """
        logger.debug(f"Querying Firestore with vector: {vector[:10]}... and query_params: {query_params}")
        try:
            results = []
            for v in vector:
                vector_query = self.collection.find_nearest(
                    vector_field="vector",
                    query_vector=Vector(v),
                    distance_measure=DistanceMeasure.EUCLIDEAN,
                    limit=10,
                )
                results.append(vector_query)
            return results
        except Exception as e:
            logger.error(f"Error querying Firestore: {e}")
            raise

    def insert(self, documents: list[dict]) -> None:
        """
        Insert documents with vector embeddings into the Firestore collection.

        Args:
            documents (list[dict]): A list of documents to insert. Each document must include a vector field.

        Raises:
            Exception: If the insertion fails.
        """
        logger.debug(f"Inserting {len(documents)} documents into collection '{self.collection.id}'")
        try:
            for doc in documents:
                if "embedding_field" not in doc or not isinstance(doc["embedding_field"], Vector):
                    if "vector" in doc:
                        doc["embedding_field"] = Vector(doc.pop("vector"))
                    else:
                        raise ValueError("Each document must include an 'embedding_field' of type Vector.")
                self.collection.add(doc)
            logger.info(f"Successfully inserted {len(documents)} documents into collection '{self.collection.id}'")
        except Exception as e:
            logger.error(f"Error inserting documents into Firestore: {e}")
            raise

    def find_one(self, query, collection=None):
        """
        Find a single document matching the query.

        Args:
            query (dict): Query parameters to match.
            collection (str, optional): Specific collection to query. Defaults to the initialized collection.

        Returns:
            dict: The first document matching the query, or None if no match is found.
        """
        logger.debug(f"Finding one document with query: {query}")
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            docs = collection_ref.where(*query).limit(1).stream()
            for doc in docs:
                return {"id": doc.id, "data": doc.to_dict()}
            return None
        except Exception as e:
            logger.error(f"Error finding one document: {e}")
            raise

    def find(self, query, collection=None):
        """
        Find all documents matching the query.

        Args:
            query (dict): Query parameters to match.
            collection (str, optional): Specific collection to query. Defaults to the initialized collection.

        Returns:
            list[dict]: A list of documents matching the query.
        """
        logger.debug(f"Finding documents with query: {query}")
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            docs = collection_ref.where(*query).stream()
            return [{"id": doc.id, "data": doc.to_dict()} for doc in docs]
        except Exception as e:
            logger.error(f"Error finding documents: {e}")
            raise

    def insert_many(self, documents, collection=None):
        """
        Insert multiple documents into the Firestore collection.

        Args:
            documents (list[dict]): A list of documents to insert.
            collection (str, optional): Specific collection to insert into. Defaults to the initialized collection.
        """
        logger.debug(f"Inserting {len(documents)} documents into collection '{collection or self.collection.id}'")
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            batch = self.db.batch()
            for doc in documents:
                doc_ref = collection_ref.document()
                batch.set(doc_ref, doc)
            batch.commit()
            logger.info(f"Successfully inserted {len(documents)} documents")
        except Exception as e:
            logger.error(f"Error inserting documents: {e}")
            raise

    def delete(self, document, collection=None):
        """
        Delete a single document from the Firestore collection.

        Args:
            document (str): The document ID to delete.
            collection (str, optional): Specific collection to delete from. Defaults to the initialized collection.
        """
        logger.debug(f"Deleting document with ID: {document}")
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            collection_ref.document(document).delete()
            logger.info(f"Successfully deleted document with ID: {document}")
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            raise

    def delete_many(self, documents, collection=None):
        """
        Delete multiple documents from the Firestore collection.

        Args:
            documents (list[str]): A list of document IDs to delete.
            collection (str, optional): Specific collection to delete from. Defaults to the initialized collection.
        """
        logger.debug(f"Deleting {len(documents)} documents")
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            batch = self.db.batch()
            for doc_id in documents:
                doc_ref = collection_ref.document(doc_id)
                batch.delete(doc_ref)
            batch.commit()
            logger.info(f"Successfully deleted {len(documents)} documents")
        except Exception as e:
            logger.error(f"Error deleting documents: {e}")
            raise

    