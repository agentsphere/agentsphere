from google.cloud import firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from google.oauth2 import service_account
from app.services.vectordb.vector_db import VectorDBInterface
from app.config import logger, settings, embedder

class FirestoreVectorDB(VectorDBInterface):
    def __init__(self, collection_name: str):
        """Initialize Firestore client and collection."""
        logger.info("Initializing FirestoreVectorDB with collection: %s", collection_name)


        creds = service_account.Credentials.from_service_account_file(settings.GOOGLE_APPLICATION_CREDENTIALS)
        self.db = firestore.Client(project="psyched-option-454007-u6", database=settings.FIRESTOREDB, credentials=creds)
        self.collection = self.db.collection(collection_name)

    def query(self, queries: list[list[float]], query_params: dict[str, any] = None) -> list[list[dict[str, any]]]:
        """
        Query the Firestore vector database using a vector and optional additional query parameters.

        Args:
            vector (List[float]): The vector to query the database with.
            query_params (Dict[str, Any], optional): Additional query parameters.

        Returns:
            List[Dict[str, Any]]: A list of results, where each result is represented as a dictionary.
        """
        logger.debug("Querying Firestore with vector: %s... and query_params: %s", vector[:10], query_params)
        try:
            results = []
            for v in queries:
                vector_query = self.collection.find_nearest(
                    vector_field="vector",
                    query_vector=Vector(v),
                    distance_measure=DistanceMeasure.EUCLIDEAN,
                    limit=10,
                ).stream()
                results.append(vector_query)
            return results
        except Exception as e:
            logger.error("Error querying Firestore: %s", e)
            raise

    def query_text(self, queries: list[str], query_params: dict[str, any] = None) -> list[list[dict[str, any]]]:
        """
        Query the Firestore vector database using a vector and optional additional query parameters.

        Args:
            queries (List[str]): The vector to query the database with.
            query_params (Dict[str, Any], optional): Additional query parameters.

        Returns:
            List[Dict[str, Any]]: A list of results, where each result is represented as a dictionary.
        """
        logger.debug("Querying Firestore with vector: %s... and query_params: %s", queries[:10], query_params)
        try:
            results = []
            for v in queries:
                logger.info("Querying Firestore with text: %s", v)



                docs = self.collection.find_nearest(
                    vector_field="embedding_field",
                    query_vector=Vector(embedder.embed_text(v)),
                    distance_measure=DistanceMeasure.DOT_PRODUCT,
                    distance_result_field="vector_distance",
                    limit=10,
                ).stream()
                #vector_query_list = list(vector_query)
                #logger.info("Query returned %d results", len(vector_query_list))
                #docs = vector_query.stream()
                docres= []
                for doc in docs:
                    if doc.exists:
                        di = doc.to_dict()
                        query= di.get("query")
                        doc_id = di.get("doc_id")
                        query_id= di.get("id")
                        docres.append({"distance": doc.get('vector_distance'),"entity": {"query": query, "doc_id": doc_id, "id": query_id}})
                        logger.info(f"{doc.id}, Distance: {doc.get('vector_distance')}")
                results.append(docres)
            return results
        except Exception as e:
            logger.error("Error querying Firestore: %s", e)
            raise

    def insert(self, document: dict, collection: str = None) -> None:
        """
        Insert documents with vector embeddings into the Firestore collection.

        Args:
            documents (list[dict]): A list of documents to insert. Each document must include a vector field.

        Raises:
            Exception: If the insertion fails.
        """
        logger.debug("Inserting %d documents into collection '%s'", len(document), self.collection.id)
        try:
            for doc in document:
                if "embedding_field" not in doc or not isinstance(doc["embedding_field"], Vector):
                    if "vector" in doc:
                        doc["embedding_field"] = Vector(doc.pop("vector"))
                    else:
                        raise ValueError("Each document must include an 'embedding_field' of type Vector.")
                self.collection.add(doc)
            logger.info("Successfully inserted %d documents into collection '%s'", len(document), self.collection.id)
        except Exception as e:
            logger.error("Error inserting documents into Firestore: %s", e)
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
        logger.debug("Finding one document with query: %s", query)
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            docs = collection_ref.where(*query).limit(1).stream()
            for doc in docs:
                return {"id": doc.id, "data": doc.to_dict()}
            return None
        except Exception as e:
            logger.error("Error finding one document: %s", e)
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
        logger.debug("Finding documents with query: %s", query)
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            docs = collection_ref.where(*query).stream()
            return [{"id": doc.id, "data": doc.to_dict()} for doc in docs]
        except Exception as e:
            logger.error("Error finding documents: %s", e)
            raise

    def insert_many(self, documents, collection=None):
        """
        Insert multiple documents into the Firestore collection.

        Args:
            documents (list[dict]): A list of documents to insert.
            collection (str, optional): Specific collection to insert into. Defaults to the initialized collection.
        """
        logger.debug("Inserting %d documents into collection '%s'", len(documents), collection or self.collection.id)
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            batch = self.db.batch()
            for doc in documents:
                doc_ref = collection_ref.document()
                batch.set(doc_ref, doc)
            batch.commit()
            logger.info("Successfully inserted %d documents", len(documents))
        except Exception as e:
            logger.error("Error inserting documents: %s", e)
            raise

    def delete(self, document, collection=None):
        """
        Delete a single document from the Firestore collection.

        Args:
            document (str): The document ID to delete.
            collection (str, optional): Specific collection to delete from. Defaults to the initialized collection.
        """
        logger.debug("Deleting document with ID: %s", document)
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            collection_ref.document(document).delete()
            logger.info("Successfully deleted document with ID: %s", document)
        except Exception as e:
            logger.error("Error deleting document: %s", e)
            raise

    def delete_many(self, documents, collection=None):
        """
        Delete multiple documents from the Firestore collection.

        Args:
            documents (list[str]): A list of document IDs to delete.
            collection (str, optional): Specific collection to delete from. Defaults to the initialized collection.
        """
        logger.debug("Deleting %d documents", len(documents))
        try:
            collection_ref = self.db.collection(collection) if collection else self.collection
            batch = self.db.batch()
            for doc_id in documents:
                doc_ref = collection_ref.document(doc_id)
                batch.delete(doc_ref)
            batch.commit()
            logger.info("Successfully deleted %d documents", len(documents))
        except Exception as e:
            logger.error("Error deleting documents: %s", e)
            raise
