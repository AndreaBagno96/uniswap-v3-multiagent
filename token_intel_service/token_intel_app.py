"""
Token Intelligence Service - FastAPI application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from routers import routers

# Import A2A app
from a2a_server.agent_executor import a2a_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Token Intelligence Service",
    description="Microservice for token security and sentiment analysis",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(routers.router)

# Mount A2A application at /a2a path
app.mount("/a2a", a2a_app)


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Token Intelligence Service starting up...")
    logger.info("A2A endpoint mounted at /a2a")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Token Intelligence Service shutting down...")


if __name__ == "__main__":
    uvicorn.run(
        "token_intel_app:app",
        host="0.0.0.0",
        port=8003,
        reload=False
    )
