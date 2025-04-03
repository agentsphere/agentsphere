from abc import ABC, abstractmethod


class ObjectStoreInterface(ABC):
    @abstractmethod
    def find_one(self, query: dict, collection: str = None) -> dict:
        """Find a single document in the collection."""

    @abstractmethod
    def find(self, query: dict, collection: str = None) -> list[dict]:
        """Find multiple documents in the collection."""

    @abstractmethod
    def insert(self, document: dict, collection: str = None) -> dict:
        """Insert a single document into the collection."""

    @abstractmethod
    def insert_many(self, documents: list[dict], collection: str = None) -> list[dict]:
        """Insert multiple documents into the collection."""

    @abstractmethod
    def delete(self, document: dict, collection: str = None) -> dict:
        """Delete a single document from the collection."""

    @abstractmethod
    def delete_many(self, documents: list[dict], collection: str = None) -> dict:
        """Delete multiple documents from the collection."""
