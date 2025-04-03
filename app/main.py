"""
This module defines the main FastAPI application for the project.
It includes:
- Middleware to log incoming HTTP request headers.
- Inclusion of API routes from the `app.api.routers` module.
- A root endpoint (`/`) that returns a welcome message from the example service.
Modules and Libraries:
- `fastapi`: Used to create the FastAPI application and define routes.
- `dotenv`: Loads environment variables from a `.env` file.
- `app.api.routers`: Contains the API route definitions.
- `app.config`: Provides application settings and logger configuration.
- `app.services.example_service`: Contains the `get_welcome_message` function.
Functions:
- `log_request_headers(request: Request, call_next)`: Middleware to log HTTP request headers.
- `read_root()`: Root endpoint that returns a welcome message.
Attributes:
- `app`: The FastAPI application instance.
"""

from fastapi import FastAPI, Request
from dotenv import load_dotenv
from app.api import routers
from app.config import settings, logger


load_dotenv()

app = FastAPI(title=settings.PROJECT_NAME)

@app.middleware("http")
async def log_request_headers(request: Request, call_next):
    """
    Middleware function to log the headers of incoming HTTP requests.

    This function logs the HTTP method, request URL path, and all headers of the incoming request.
    It then passes the request to the next middleware or endpoint handler in the chain.

    Args:
        request (Request): The incoming HTTP request object.
        call_next (Callable): A function to call the next middleware or endpoint handler.

    Returns:
        Response: The HTTP response returned by the next middleware or endpoint handler.
    """
    headers = dict(request.headers.items())
    logger.info("Incoming %s request to %s with headers: %s", request.method, request.url.path, headers)
    response = await call_next(request)
    return response


# Include API routes
for router in routers:
    app.include_router(router)
logger.info("API routes included")


@app.get("/")
def read_root():
    """
    Handles the root endpoint of the application.

    Returns:
        dict: A dictionary containing a message with a key "message".
    """
    return {"message": "message"}
