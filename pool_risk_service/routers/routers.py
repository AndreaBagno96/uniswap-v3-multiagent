"""
FastAPI routers for Pool Risk Service.
Defines REST API endpoints for pool risk analysis.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from contextlib import asynccontextmanager
import logging

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from common_ai.mappings.schemas import AgentRequest, AgentResponse
from agent.pool_risk_agent import PoolRiskAgent

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize agent (singleton pattern - cached at startup)
_agent: PoolRiskAgent = None


def get_agent() -> PoolRiskAgent:
    """Get or create the pool risk agent instance (with MCP tools cached)."""
    global _agent
    if _agent is None:
        logger.info("Initializing Pool Risk Agent singleton...")
        _agent = PoolRiskAgent()
        logger.info(f"Agent initialized. MCP available: {_agent.is_mcp_available}")
    return _agent


def initialize_agent() -> None:
    """Pre-initialize agent at startup (call from app lifespan)."""
    get_agent()


@router.post("/v1/invoke", response_model=AgentResponse)
async def invoke_agent(request: AgentRequest) -> AgentResponse:
    """
    Invoke pool risk agent with a query.
    
    Args:
        request: Agent request with user question and pool address
        
    Returns:
        Agent response with analysis results
        
    Raises:
        HTTPException: If analysis fails
    """
    try:
        logger.info(f"Received request for pool: {request.pool_address}")
        logger.info(f"Question: {request.user_question}")
        
        agent = get_agent()
        response = await agent.invoke(request)
        
        logger.info(f"Analysis completed successfully")
        return response
        
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Pool risk analysis failed: {str(e)}"
        )


@router.get("/health")
def health_check() -> Dict[str, Any]:
    """
    Health check endpoint with MCP status.
    
    Returns:
        Health status information including MCP availability
    """
    agent = get_agent()
    
    return {
        "status": "healthy",
        "service": "pool-risk",
        "version": "1.0.0",
        "mcp": {
            "available": agent.is_mcp_available,
            "tools": agent.get_available_tools()
        }
    }


@router.get("/tools")
def list_tools() -> Dict[str, Any]:
    """
    List available analysis tools.
    
    Returns:
        List of tool names and MCP status
    """
    agent = get_agent()
    
    return {
        "mcp_available": agent.is_mcp_available,
        "tools": agent.get_available_tools(),
        "fallback_mode": not agent.is_mcp_available
    }


@router.post("/refresh-tools")
async def refresh_tools() -> Dict[str, Any]:
    """
    Refresh MCP tools (reconnect to MCP server).
    
    Returns:
        Updated tool status
    """
    agent = get_agent()
    success = await agent.refresh_mcp_tools()
    
    return {
        "success": success,
        "mcp_available": agent.is_mcp_available,
        "tools": agent.get_available_tools()
    }


@router.get("/")
def root() -> Dict[str, str]:
    """Root endpoint with service information."""
    agent = get_agent()
    
    return {
        "service": "Pool Risk Service",
        "description": "Uniswap V3 liquidity pool risk analysis with dynamic tool selection",
        "mcp_enabled": agent.is_mcp_available,
        "endpoints": {
            "invoke": "POST /v1/invoke",
            "health": "GET /health",
            "tools": "GET /tools",
            "refresh_tools": "POST /refresh-tools"
        }
    }
