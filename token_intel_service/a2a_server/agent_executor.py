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
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message
from a2a.types import AgentCard, AgentCapabilities, AgentSkill, DataPart
from agent.token_intel_agent import TokenIntelligenceAgent
import logging
import json

logger = logging.getLogger(__name__)


class TokenIntelAgentExecutor(AgentExecutor):
    """Handles incoming A2A message events and invokes the Token Intelligence LangGraph agent."""
    
    def __init__(self):
        """Initialize executor with agent."""
        self.agent = TokenIntelligenceAgent()
        logger.info("Token Intelligence Agent Executor initialized")
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute token intelligence analysis via A2A protocol.
        
        Args:
            context: RequestContext with message and metadata
            event_queue: EventQueue for sending responses
        """
        try:
            logger.info(f"A2A execute called with context: {context.context_id}")
            
            # Extract request from message parts
            part = context.message.parts[0].root  # type: ignore
            
            if isinstance(part, DataPart):
                # Structured data request
                request_data = part.data
                user_question = request_data.get("user_question", "")
                pool_address = request_data.get("pool_address")
                trace_id = request_data.get("trace_id")
            else:
                # Text request - extract from text part
                user_question = str(part.text) if hasattr(part, 'text') else str(part)
                pool_address = context.message.metadata.get("pool_address") if context.message.metadata else None
                trace_id = context.message.metadata.get("trace_id") if context.message.metadata else None
            
            logger.info(f"Processing request: question='{user_question[:50]}...', pool={pool_address}")
            
            # Invoke the agent
            result = await self.agent.ainvoke(
                user_question=user_question,
                pool_address=pool_address,
                trace_id=trace_id
            )
            
            # Send response as JSON text
            response_text = json.dumps({
                "answer": result.get("answer", ""),
                "metadata": result.get("metadata", {}),
                "risk_score": result.get("risk_score", 0)
            })
            
            await event_queue.enqueue_event(new_agent_text_message(response_text))
            
        except Exception as e:
            logger.error(f"Token Intelligence agent execution failed: {e}")
            error_response = json.dumps({
                "answer": f"Error: {str(e)}",
                "metadata": {"error": str(e)},
                "risk_score": 0
            })
            await event_queue.enqueue_event(new_agent_text_message(error_response))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel is not supported."""
        raise NotImplementedError("Cancel operation is not supported by this agent.")


def build_a2a_app():
    """
    Build A2A Starlette application.
    
    Returns:
        Configured A2A application
    """
    logger.info("Building A2A application for Token Intelligence Service")
    
    # Define agent card with A2A protocol v0.3 schema
    agent_card = AgentCard(
        name="Token Intelligence Agent",
        description="Analyzes token security and sentiment using DexScreener, GoPlus, and web search",
        url="http://localhost:8003/a2a",
        version="1.0.0",
        capabilities=AgentCapabilities(
            streaming=False,
            push_notifications=False,
            state_transition_history=False
        ),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id="token-resolution",
                name="Token Resolution",
                description="Resolve token addresses and metadata from pool",
                tags=["token", "resolution", "metadata"]
            ),
            AgentSkill(
                id="contract-security-analysis",
                name="Contract Security Analysis",
                description="Analyze token contract security using GoPlus",
                tags=["security", "contract", "audit"]
            ),
            AgentSkill(
                id="sentiment-analysis",
                name="Sentiment Analysis",
                description="Analyze market sentiment for tokens",
                tags=["sentiment", "market", "social"]
            ),
            AgentSkill(
                id="risk-classification",
                name="Risk Classification",
                description="Classify token risk level",
                tags=["risk", "classification", "score"]
            )
        ]
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
    
    # rpc_url is relative to mount point - since we mount at /a2a, use /
    app = server.build(rpc_url='/')
    logger.info("A2A application built successfully")
    
    return app


# For mounting in main FastAPI app
a2a_app = build_a2a_app()
