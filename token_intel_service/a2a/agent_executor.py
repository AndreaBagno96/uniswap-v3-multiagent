"""
Token Intelligence A2A Agent Executor.
Enables agent-to-agent communication using the A2A SDK.
"""

import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common_ai"))

from a2a.server.apps import A2AStarletteApplication
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.request_handlers import DefaultRequestHandler
from a2a import AgentCard
from agent.token_intel_agent import TokenIntelligenceAgent
from common_ai.mappings.schemas import AgentRequest
import logging

logger = logging.getLogger(__name__)


class TokenIntelAgentExecutor:
    """Wrapper for A2A protocol support."""
    
    def __init__(self):
        """Initialize executor with agent."""
        self.agent = TokenIntelligenceAgent()
    
    async def execute(self, request: AgentRequest) -> dict:
        """
        Execute token intelligence analysis.
        
        Args:
            request: AgentRequest with user_question and pool_address
            
        Returns:
            Dict with answer and metadata
        """
        result = await self.agent.ainvoke(
            user_question=request.user_question,
            pool_address=request.pool_address,
            trace_id=request.trace_id
        )
        return result


def build_a2a_app():
    """
    Build A2A Starlette application.
    
    Returns:
        Configured A2A application
    """
    logger.info("Building A2A application for Token Intelligence Service")
    
    # Define agent card
    agent_card = AgentCard(
        name="Token Intelligence Agent",
        description="Analyzes token security and sentiment using DexScreener, GoPlus, and web search",
        capabilities=[
            "token-resolution",
            "contract-security-analysis",
            "sentiment-analysis",
            "risk-classification"
        ],
        metadata={
            "version": "1.0.0",
            "data_sources": ["DexScreener", "GoPlus", "Tavily"]
        }
    )
    
    # Create request handler with in-memory task store
    handler = DefaultRequestHandler(
        agent_executor=TokenIntelAgentExecutor(),
        task_store=InMemoryTaskStore()
    )
    
    # Build A2A server
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler
    )
    
    app = server.build(rpc_url='/a2a/v1/token-intel')
    logger.info("A2A application built successfully")
    
    return app


# For mounting in main FastAPI app
a2a_app = build_a2a_app()
