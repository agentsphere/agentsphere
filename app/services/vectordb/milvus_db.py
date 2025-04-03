from pymilvus import MilvusClient
from app.services.vectordb.vector_db import VectorDBInterface
from app.config import logger,settings

class MilvusVectorDB(VectorDBInterface):

    def __init__(self, collection_name: str):
        """Initialize the Milvus client and collection."""
        logger.info("Initializing MilvusVectorDB with collection: %s", collection_name)
        self.client = MilvusClient(settings.MILVUSDBFILE)
        self.collection_name = collection_name
        if self.client.has_collection(collection_name=collection_name):
            logger.info("Dropping existing collection: knowledge")
            self.client.drop_collection(collection_name=collection_name)

        if not self.client.has_collection(collection_name=collection_name):
            logger.info("Creating new collection: knowledge")
            self.client.create_collection(
                collection_name=collection_name,
                auto_id=True,
                dimension=1024,
            )
            logger.info("Collection '%s' created successfully.", collection_name)

    def query(self, queries: list[list[float]], query_params: dict[str, any] = None) -> list[list[dict[str, any]]]:
        """
        Query the Milvus vector database using a vector and optional additional query parameters.
        """
        logger.info("Querying Milvus with vector: %s... and query_params: %s", queries[:10], query_params)
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                data=queries,
                limit=40,
                output_fields=["query", "doc_id", "id"],
            )
            if results is None:
                logger.warning("No results found in Milvus")
                return []
            logger.info("Query returned %d results", len(results))
            # Process and return results
            return results

        except Exception as e:
            logger.error("Error querying Milvus: %s", e)
            raise

    def insert(self, document: dict, collection: str = None) -> None:
        """
        Insert vectors and their associated metadata into the Milvus collection.

        Args:
            vectors (List[List[float]]): The list of vectors to insert.
            metadata (List[dict[str, any]]): The list of metadata dictionaries corresponding to each vector.

        Raises:
            Exception: If the insertion fails.
        """
        logger.info("Inserting %d vectors into collection '%s'", len(document), self.collection_name)
        try:
            # Insert data into the collection
            self.client.insert(
                collection_name=self.collection_name,
                data=document)

            logger.info("Successfully inserted %d vectors into collection '%s'", len(document), self.collection_name)
        except Exception as e:
            logger.error("Error inserting vectors into Milvus: %s", e)
            raise

    def find_one(self, query, collection=None):
        """
        Find a single document matching the query.
        """
        logger.info("Finding one document in collection '%s' with query: %s", self.collection_name, query)
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                data=[query],
                limit=1,
                output_fields=["query", "doc_id", "id"],
            )
            if results and len(results[0]) > 0:
                return results[0][0]
            logger.warning("No matching document found.")
            return None
        except Exception as e:
            logger.error("Error finding document: %s", e)
            raise

    def find(self, query, collection=None):
        """
        Find multiple documents matching the query.
        """
        logger.info("Finding documents in collection '%s' with query: %s", self.collection_name, query)
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                data=[query],
                limit=40,
                output_fields=["query", "doc_id", "id"],
            )
            if results:
                return results[0]
            logger.warning("No matching documents found.")
            return []
        except Exception as e:
            logger.error("Error finding documents: %s", e)
            raise

    def insert_many(self, documents, collection=None):
        """
        Insert multiple documents into the collection.
        """
        logger.info("Inserting %d documents into collection '%s'", len(documents), self.collection_name)
        try:
            self.client.insert(
                collection_name=self.collection_name,
                data=documents,
            )
            logger.info("Successfully inserted %d documents.", len(documents))
        except Exception as e:
            logger.error("Error inserting documents: %s", e)
            raise

    def delete(self, document, collection=None):
        """
        Delete a single document from the collection.
        """
        logger.info("Deleting document from collection '%s' with ID: %s", self.collection_name, document['id'])
        try:
            self.client.delete(
                collection_name=self.collection_name,
                expr=f"id == {document['id']}"
            )
            logger.info("Document deleted successfully.")
        except Exception as e:
            logger.error("Error deleting document: %s", e)
            raise

    def delete_many(self, documents, collection=None):
        """
        Delete multiple documents from the collection.
        """
        ids = [doc['id'] for doc in documents]
        logger.info("Deleting %d documents from collection '%s'", len(ids), self.collection_name)
        try:
            self.client.delete(
                collection_name=self.collection_name,
                expr=f"id in {ids}"
            )
            logger.info("Documents deleted successfully.")
        except Exception as e:
            logger.error("Error deleting documents: %s", e)
            raise

    def query_text(self, queries, query_params=None):
        """
        Query the database using a text vector.
        """
        logger.info("Querying text in collection '%s' with vector: %s...", self.collection_name, queries[:10])
        return self.query(queries, query_params)
