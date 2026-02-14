"""
Pool Risk Service - FastAPI + A2A Entry Point
Main application for pool risk analysis microservice.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn
import logging
import os

# Import routers
from routers.routers import router, initialize_agent

# Import A2A app
from a2a_server.agent_executor import a2a_app

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Pool Risk Service",
    description="Uniswap V3 liquidity pool risk analysis microservice with MCP tool calling",
    version="2.0.0"
)

# CORS configuration
cors_origins = os.getenv("CORS_ORIGINS", "*")
if cors_origins:
    origins = cors_origins.split(",") if cors_origins != "*" else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include routers
app.include_router(router)

# Mount A2A application at /a2a path
app.mount("/a2a", a2a_app)


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup, including MCP tools."""
    logger.info("Pool Risk Service starting up...")
    logger.info(f"CORS origins: {cors_origins}")
    logger.info("A2A endpoint mounted at /a2a")
    
    # Pre-initialize agent to cache MCP tools at startup
    logger.info("Pre-initializing agent and caching MCP tools...")
    initialize_agent()
    logger.info("Agent initialization complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown."""
    logger.info("Pool Risk Service shutting down...")


if __name__ == "__main__":
    port = int(os.getenv("POOL_RISK_PORT", "8001"))
    logger.info(f"Starting Pool Risk Service on port {port}")
    
    uvicorn.run(
        "pool_risk_app:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT", "production") == "development"
    )
