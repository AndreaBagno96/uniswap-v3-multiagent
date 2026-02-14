"""
Token Intelligence Service API routers.
"""

import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common_ai"))

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from common_ai.mappings.schemas import AgentRequest, AgentResponse
from agent.token_intel_agent import TokenIntelligenceAgent
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize agent (singleton)
agent = None


def get_agent() -> TokenIntelligenceAgent:
    """Get or create agent instance (with MCP tools cached)."""
    global agent
    if agent is None:
        logger.info("Initializing Token Intelligence Agent singleton...")
        agent = TokenIntelligenceAgent()
        logger.info(f"Agent initialized. MCP available: {agent.is_mcp_available}")
    return agent


def initialize_agent() -> None:
    """Pre-initialize agent at startup (call from app lifespan)."""
    get_agent()


@router.post("/v1/invoke", response_model=AgentResponse)
async def invoke_agent(request: AgentRequest):
    """
    Invoke token intelligence analysis.
    
    Args:
        request: AgentRequest with user_question and pool_address
        
    Returns:
        AgentResponse with analysis results
    """
    try:
        logger.info(f"Received request for pool: {request.pool_address}")
        logger.info(f"Question: {request.user_question}")
        
        agent_instance = get_agent()
        result = await agent_instance.ainvoke(
            user_question=request.user_question,
            pool_address=request.pool_address,
            trace_id=request.trace_id
        )
        
        # Extract risk score from classifications
        risk_score = 0.0
        classifications = result.get("metadata", {}).get("classifications", {})
        if classifications:
            scores = [c.get("risk_score", 0) for c in classifications.values() if isinstance(c, dict)]
            risk_score = sum(scores) / len(scores) if scores else 0.0
        
        return AgentResponse(
            answer=result["answer"],
            metadata=result.get("metadata", {}),
            risk_score=risk_score
        )
    except Exception as e:
        logger.error(f"Token intelligence invocation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
def health_check() -> Dict[str, Any]:
    """
    Health check endpoint with MCP status.
    
    Returns:
        Health status information including MCP availability
    """
    agent_instance = get_agent()
    
    return {
        "status": "healthy",
        "service": "token-intelligence",
        "version": "1.0.0",
        "mcp": {
            "available": agent_instance.is_mcp_available,
            "tools": agent_instance.get_available_tools()
        }
    }


@router.get("/tools")
def list_tools() -> Dict[str, Any]:
    """
    List available analysis tools.
    
    Returns:
        List of tool names and MCP status
    """
    agent_instance = get_agent()
    
    return {
        "mcp_available": agent_instance.is_mcp_available,
        "tools": agent_instance.get_available_tools(),
        "fallback_mode": not agent_instance.is_mcp_available
    }


@router.post("/refresh-tools")
async def refresh_tools() -> Dict[str, Any]:
    """
    Refresh MCP tools (reconnect to MCP server).
    
    Returns:
        Updated tool status
    """
    agent_instance = get_agent()
    success = await agent_instance.refresh_mcp_tools()
    
    return {
        "success": success,
        "mcp_available": agent_instance.is_mcp_available,
        "tools": agent_instance.get_available_tools()
    }


@router.get("/")
def root() -> Dict[str, str]:
    """Root endpoint with service information."""
    agent_instance = get_agent()
    
    return {
        "service": "Token Intelligence Service",
        "description": "Token security and risk analysis with dynamic tool selection",
        "mcp_enabled": agent_instance.is_mcp_available,
        "endpoints": {
            "invoke": "POST /v1/invoke",
            "health": "GET /health",
            "tools": "GET /tools",
            "refresh_tools": "POST /refresh-tools"
        }
    }
