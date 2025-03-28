import logging

from pydantic import ConfigDict
from pydantic_settings import BaseSettings  # Updated import
from datetime import datetime, timezone, timedelta

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