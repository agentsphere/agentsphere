from typing import List, Dict, Any
from pymilvus import Collection, MilvusClient
from app.services.vectordb.vector_db import VectorDBInterface
from app.config import logger,settings

class MilvusVectorDB(VectorDBInterface):
    
    def __init__(self, collection_name: str):
        """Initialize the Milvus client and collection."""
        logger.info(f"Initializing MilvusVectorDB with collection: {collection_name}")
        self.client = MilvusClient(settings.MILVUSDBFILE)
        self.collection_name = collection_name
        if self.client.has_collection(collection_name=collection_name):
            logger.info("Dropping existing collection:knowledge")
            self.client.drop_collection(collection_name=collection_name)

        if not self.client.has_collection(collection_name=collection_name):
            logger.info("creating new collection: knowledge")
            self.client.create_collection(
                collection_name=collection_name,
                auto_id=True,
                dimension=1024,
            )
            logger.info(f"Collection '{collection_name}' created successfully.")

    def query(self, vector: list[list[float]], query_params: Dict[str, Any] = None) -> list[list[Dict[str, any]]]:
        """
        Query the Milvus vector database using a vector and optional additional query parameters.
        """
        logger.info(f"Querying Milvus with vector: {vector[:10]}... and query_params: {query_params}")
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                data=vector,
                limit=40,
                output_fields=["query", "doc_id","id"],
            )
            if results is None:
                logger.warning("No results found in Milvus")
                return []
            logger.info(f"Query returned {len(results)} results")
            # Process and return results
            return results[0]

        except Exception as e:
            logger.error(f"Error querying Milvus: {e}")
            raise

    def insert(self, documents: list[dict]) -> None:
        """
        Insert vectors and their associated metadata into the Milvus collection.

        Args:
            vectors (List[List[float]]): The list of vectors to insert.
            metadata (List[Dict[str, Any]]): The list of metadata dictionaries corresponding to each vector.

        Raises:
            Exception: If the insertion fails.
        """
        logger.info(f"Inserting {len(documents)} vectors into collection '{self.collection_name}'")
        try:
            # Insert data into the collection
            self.client.insert(
                collection_name=self.collection_name,
                data=documents)
                
            logger.info(f"Successfully inserted {len(documents)} vectors into collection '{self.collection_name}'")
        except Exception as e:
            logger.error(f"Error inserting vectors into Milvus: {e}")
            raise

    def find_one(self, query, collection = None):
        raise NotImplementedError

    def find(self, query, collection = None):
        raise NotImplementedError

    def insert_many(self, documents, collection = None):
        raise NotImplementedError

    def delete(self, document, collection = None):
        raise NotImplementedError

    def delete_many(self, documents, collection = None):
        raise NotImplementedError


