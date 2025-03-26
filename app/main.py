from fastapi import FastAPI
from app.api import routers
from app.config import settings, logger
from app.services.example_service import get_welcome_message

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title=settings.PROJECT_NAME)


# Include API routes
[app.include_router(router) for router in routers]
logger.info("API routes included")

@app.get("/")
def read_root():
    # Call the example service
    message = get_welcome_message()
    return {"message": message}
