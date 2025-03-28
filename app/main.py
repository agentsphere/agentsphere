from fastapi import FastAPI, Request
from app.api import routers
from app.config import settings, logger
from app.services.example_service import get_welcome_message

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title=settings.PROJECT_NAME)

@app.middleware("http")
async def log_request_headers(request: Request, call_next):
    headers = {k: v for k, v in request.headers.items()}
    logger.info(f"Incoming {request.method} request to {request.url.path} with headers: {headers}")
    response = await call_next(request)
    return response


# Include API routes
[app.include_router(router) for router in routers]
logger.info("API routes included")

@app.get("/")
def read_root():
    # Call the example service
    message = get_welcome_message()
    return {"message": message}
