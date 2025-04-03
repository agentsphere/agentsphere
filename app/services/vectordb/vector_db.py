from abc import ABC, abstractmethod

from app.services.object_store.object_store import ObjectStoreInterface

class VectorDBInterface(ObjectStoreInterface, ABC):

    @abstractmethod
    def query(self, queries: list[list[float]], query_params: dict[str, any] = None) -> list[list[dict[str, any]]]:
        """
        Query the vector database using a vector and optional additional query parameters.
        """

    @abstractmethod
    def query_text(self, queries: list[str], query_params: dict[str, any] = None) -> list[list[dict[str, any]]]:
        """
        Query the vector database using a text query and optional additional query parameters.
        """
