"""
Backend Orchestrator - FastAPI application.
"""

import os
import sys
from pathlib import Path

# Add project root to path for common_ai and other shared modules
_current_dir = Path(__file__).parent
_project_root = _current_dir.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_current_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
from dotenv import load_dotenv

# Load environment variables from project root
env_path = _project_root / ".env"
load_dotenv(dotenv_path=env_path)

from routers import routers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Uniswap V3 Risk Analysis Orchestrator",
    description="Multi-agent orchestrator for comprehensive pool and token risk analysis",
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


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Backend Orchestrator starting up...")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Backend Orchestrator shutting down...")


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=5000,
        reload=False
    )
