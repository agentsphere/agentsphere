from .agent import router as agent_router
from .wss import router as wss_router
from .repo import router as repo_router

routers = [agent_router, wss_router, repo_router]
