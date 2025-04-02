from abc import ABC, abstractmethod
from typing import List, Dict, Any

from app.services.object_store.ObjectStoreInterface import ObjectStoreInterface

class VectorDBInterface(ObjectStoreInterface, ABC):
    @abstractmethod
    def query(self, vector: list[list[float]], query_params: Dict[str, Any] = None) -> list[list[dict[str, any]]]:
        """
        Query the vector database using a vector and optional additional query parameters.

        Args:
            vector (List[float]): The vector to query the database with.
            query_params (Dict[str, Any], optional): Additional query parameters.

        Returns:
            List[Dict[str, Any]]: A list of results, where each result is represented as a dictionary.
        """
        pass

    @abstractmethod
    def insert(self, documents: list[dict]) -> None:
        pass
