import logging

from pydantic import ConfigDict
from pydantic_settings import BaseSettings  # Updated import
from datetime import datetime, timezone, timedelta

from app.services.embedder import TextEmbedderInterface

tz_offset = -8  # Offset in hours
tzinfo = timezone(timedelta(hours=tz_offset))

class Settings(BaseSettings):
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


    # Use ConfigDict instead of class-based Config
    model_config = ConfigDict(env_file=".env")


# Initialize settings
settings = Settings()

# Logger setup
def setup_logger():
    log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logger = logging.getLogger(settings.PROJECT_NAME)
    return logger

# Initialize logger
logger = setup_logger()

def get_db_client(collection: str):
    """
    Get the singleton instance of the object store.
    """
    if settings.OBJECT_STORE == "mongomock":
        from app.services.object_store.MongoLocalStore import MongoLocalStore
        return MongoLocalStore(collection=collection)
    elif settings.OBJECT_STORE == "mongo":
        from app.services.object_store.MongoStore import MongoStore
        return MongoStore(collection=collection)
    elif settings.OBJECT_STORE == "firestore":
        from app.services.object_store.FireStore import FireStoreCollection
        return FireStoreCollection(collection=collection)
    else:   
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
    elif settings.EMBEDDER == "ollama":
        from app.services.embedder.ollama_embedder import OllamaEmbedder
        return OllamaEmbedder()
    else:
        raise ValueError(f"Unsupported embedder type: {settings.EMBEDDER}")

embedder = get_text_embedder()

def get_vector_db_client(collection: str):
    """
    Get the singleton instance of the vector database.
    """
    if settings.VECTOR_DB == "milvus_local":
        logger.info(f"Using local Milvus vector database with collection: {collection}")
        from app.services.vectordb.milvus_db import MilvusVectorDB
        return MilvusVectorDB(collection_name=collection)
    elif settings.VECTOR_DB == "firestore":
        logger.info(f"Using local firestore vector database with collection: {collection}")
        from app.services.vectordb.firestore_vector_db import FirestoreVectorDB
        return FirestoreVectorDB(collection_name=collection)
    else:
        raise ValueError(f"Unsupported vector database type: {settings.VECTOR_DB}")
    
query_collection = get_vector_db_client(settings.COLLECTION_NAME_QUERIES)

