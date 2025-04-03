"""
This module defines the configuration and setup for the AgentSphere application.

It includes:
- The `Settings` class, which manages application configuration using Pydantic's `BaseSettings`.
- Initialization of various database clients and services based on the configuration.
- Logger setup for consistent logging throughout the application.
- Factory methods for creating instances of text embedders and vector database clients.

The configuration is designed to be flexible, supporting multiple environments (e.g., development, staging, production)
and various backend services (e.g., MongoDB, Firestore, Milvus).

Attributes:
    settings (Settings): Singleton instance of the application settings.
    logger (logging.Logger): Configured logger for the application.
    knowledge_collection, tool_collection, config_collection, repo_collection, flow_collection,
    web_search_cache_collection, get_knowledge_cache_collection: Initialized database clients for specific collections.
    embedder (TextEmbedderInterface): Initialized text embedder based on configuration.
    query_collection: Initialized vector database client for query collection.
"""
import logging
from datetime import timezone, timedelta

from pydantic import ConfigDict
from pydantic_settings import BaseSettings  # Updated import

from app.services.embedder import TextEmbedderInterface

TZ_OFFSET = -8  # Offset in hours
TZINFO = timezone(timedelta(hours=TZ_OFFSET))

class Settings(BaseSettings):
    """
    Settings configuration class for the AgentSphere application.
    This class defines various configuration parameters used throughout the application.
    It leverages `BaseSettings` from Pydantic to allow environment variable overrides
    and provides default values for development, staging, and production environments.
    Attributes:
        PROJECT_NAME (str): The name of the project. Default is "AgentSphere".
        ENVIRONMENT (str): The current environment ("dev", "staging", "prod"). Default is "dev".
        DEBUG (bool): Flag to enable or disable debug mode. Default is True.
        MILVUSDBFILE (str): Path to the Milvus database file. Default is "milv.db".
        CLIENT_SECRET (str): Secret key for client authentication.
        CLIENT (str): Client identifier.
        TOKEN (str): Authentication token.
        INTROSPECTION_URL (str): URL for token introspection.
        LLM_MODEL (str): Path or identifier for the large language model. Default is "ollama_chat/qwen2.5-coder:32b".
        ANTHROPIC_API_KEY (str): API key for Anthropic integration.
        SERPER_API_KEY (str): API key for Serper integration.
        FIREWORKS_AI_API_KEY (str): API key for Fireworks AI integration.
        BASE_REPO_PATH (str): Base directory path for repositories. Default is "./repos".
        GOOGLE_APPLICATION_CREDENTIALS (str): Path to the Google Cloud service account JSON file.
        FIRESTOREDB (str): Firestore database name. Default is "test".
        MONGO_DB_USER (str): MongoDB username.
        MONGO_DB_PASSWORD (str): MongoDB password.
        MONGO_DB_URI (str): URI for connecting to the MongoDB instance.
        MONGO_DB_NAME (str): Name of the MongoDB database. Default is "agentsphere".
        OBJECT_STORE (str): Type of object store to use ("mongo", "mongomock", "firestore"). Default is "firestore".
        MONGOMOCK_DB_NAME (str): Name of the MongoMock database. Default is "test".
        COLLECTION_NAME_KNOWLEDGE (str): Name of the knowledge collection. Default is "knowledge".
        COLLECTION_NAME_QUERIES (str): Name of the queries collection. Default is "queries".
        COLLECTION_NAME_TOOLS (str): Name of the tools collection. Default is "tools".
        COLLECTION_NAME_CONFIG (str): Name of the configuration collection. Default is "config".
        COLLECTION_NAME_FLOWS (str): Name of the flows collection. Default is "flows".
        COLLECTION_NAME_REPOS (str): Name of the repositories collection. Default is "repos".
        COLLECTION_NAME_WEB_SEARCH_CACHE (str): Name of the web search cache collection. Default is "googleSearchCache".
        COLLECTION_NAME_GET_KNOWLEDGE_CACHE (str): Name of the get knowledge cache collection. Default is "getKnowledgeCache".
        EMBEDDER (str): Embedder type to use ("vertex_ai", "ollama"). Default is "ollama".
        EMBEDDING_MODEL (str): Embedding model identifier. Default is "mxbai-embed-large".
        EMBEDDING_DIMENSIONALITY (int): Dimensionality of the embedding vectors. Default is 1024.
        VECTOR_DB (str): Type of vector database to use ("milvus_local", "firestore"). Default is "firestore".
        DOC_LIMIT (int): Maximum number of documents to process. Default is 20000.
        PAGE_LIMIT (int): Maximum number of pages to process. Default is 200000.
        WEBSEARCH_URL (str): URL for web search API. Default is "https://google.serper.dev/search".
        BLACKLIST_SEARCH (list[str]): List of blacklisted search terms.
        GCLOUD_PROJECT_ID (str): Google Cloud project ID. Default is "psyched-option-454007-u6".
        AUTH_SECRET (str): Secret key for authentication. Default is "notSecret".
        model_config (ConfigDict): Configuration for loading environment variables from a `.env` file.
    """

    PROJECT_NAME: str = "AgentSphere"
    ENVIRONMENT: str = "dev"  # dev, staging, prod
    DEBUG: bool = True
    MILVUSDBFILE: str = "milv.db"
    CLIENT_SECRET: str = ""
    CLIENT: str =""
    TOKEN: str =""
    INTROSPECTION_URL: str = ""
    LLM_MODEL: str = "ollama_chat/qwen2.5-coder:32b"
    ANTHROPIC_API_KEY: str = ""
    SERPER_API_KEY: str = ""
    FIREWORKS_AI_API_KEY: str = ""
    BASE_REPO_PATH: str = "./repos"
    GOOGLE_APPLICATION_CREDENTIALS: str = "./gcloud-key.json" #path/to/my-service-account.json
    FIRESTOREDB: str = "test"
    MONGO_DB_USER: str = ""
    MONGO_DB_PASSWORD: str = ""
    MONGO_DB_URI: str = "mongodb+srv://{MONGO_DB_USER}:{MONGO_DB_PASSWORD}>@agentsphere.3b9wx.mongodb.net/?retryWrites=true&w=majority&appName=agentsphere"
    MONGO_DB_NAME: str = "agentsphere"
    OBJECT_STORE: str = "firestore"  # mongo, mongomock, firestore
    MONGOMOCK_DB_NAME: str = "test"
    COLLECTION_NAME_KNOWLEDGE: str = "knowledge"
    COLLECTION_NAME_QUERIES: str = "queries"
    COLLECTION_NAME_TOOLS: str = "tools"
    COLLECTION_NAME_CONFIG: str = "config"
    COLLECTION_NAME_FLOWS: str = "flows"
    COLLECTION_NAME_REPOS: str = "repos"
    COLLECTION_NAME_WEB_SEARCH_CACHE: str = "googleSearchCache"
    COLLECTION_NAME_GET_KNOWLEDGE_CACHE: str = "getKnowledgeCache"
    EMBEDDER: str = "ollama"  # vertex_ai, ollama
    EMBEDDING_MODEL: str = "mxbai-embed-large"
    EMBEDDING_DIMENSIONALITY: int = 1024
    VECTOR_DB: str = "firestore"  # milvus_local, firestore
    DOC_LIMIT: int = 20000
    PAGE_LIMIT: int = 200000
    WEBSEARCH_URL: str = "https://google.serper.dev/search"
    BLACKLIST_SEARCH: list[str] = []
    GCLOUD_PROJECT_ID: str = "psyched-option-454007-u6"
    AUTH_SECRET: str = "notSecret"

    # Use ConfigDict instead of class-based Config
    model_config = ConfigDict(env_file=".env")


# Initialize settings
settings = Settings()

# Logger setup
def setup_logger():
    log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)-8s %(levelname)-8s %(name)s:%(filename)s:%(lineno)d %(funcName)s:%(message)s",
    )
    return logging.getLogger(settings.PROJECT_NAME)

# Initialize logger
logger = setup_logger()

def get_db_client(collection: str):
    """
    Get the singleton instance of the object store.
    """
    if settings.OBJECT_STORE == "mongomock":
        from app.services.object_store.mongo_local import MongoLocalStore
        return MongoLocalStore(collection=collection)
    if settings.OBJECT_STORE == "mongo":
        from app.services.object_store.mongo_store import MongoStore
        return MongoStore(collection=collection)
    if settings.OBJECT_STORE == "firestore":
        from app.services.object_store.fire_store import FireStoreCollection
        return FireStoreCollection(collection=collection)
    raise ValueError(f"Unsupported object store type: {settings.OBJECT_STORE}")

knowledge_collection = get_db_client(settings.COLLECTION_NAME_KNOWLEDGE)
tool_collection = get_db_client(settings.COLLECTION_NAME_TOOLS)
config_collection = get_db_client(settings.COLLECTION_NAME_CONFIG)
repo_collection = get_db_client(settings.COLLECTION_NAME_REPOS)
flow_collection = get_db_client(settings.COLLECTION_NAME_FLOWS)
web_search_cache_collection = get_db_client(settings.COLLECTION_NAME_WEB_SEARCH_CACHE)
get_knowledge_cache_collection = get_db_client(settings.COLLECTION_NAME_GET_KNOWLEDGE_CACHE)

def get_text_embedder() -> TextEmbedderInterface:
    """
    Factory method to get the appropriate text embedder based on configuration.
    """
    if settings.EMBEDDER == "vertex_ai":
        from app.services.embedder.vertex_ai_embedder import VertexAIEmbedder
        return VertexAIEmbedder()
    if settings.EMBEDDER == "ollama":
        from app.services.embedder.ollama_embedder import OllamaEmbedder
        return OllamaEmbedder()
    raise ValueError(f"Unsupported embedder type: {settings.EMBEDDER}")

embedder = get_text_embedder()

def get_vector_db_client(collection: str):
    """
    Get the singleton instance of the vector database.
    """
    if settings.VECTOR_DB == "milvus_local":
        logger.info("Using local Milvus vector database with collection: %s", collection)
        from app.services.vectordb.milvus_db import MilvusVectorDB
        return MilvusVectorDB(collection_name=collection)
    if settings.VECTOR_DB == "firestore":
        logger.info("Using local firestore vector database with collection: %s", collection)
        from app.services.vectordb.firestore_vector_db import FirestoreVectorDB
        return FirestoreVectorDB(collection_name=collection)
    raise ValueError(f"Unsupported vector database type: {settings.VECTOR_DB}")

query_collection = get_vector_db_client(settings.COLLECTION_NAME_QUERIES)
