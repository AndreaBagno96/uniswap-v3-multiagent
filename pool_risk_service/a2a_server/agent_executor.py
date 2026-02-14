"""
A2A Protocol Support for Pool Risk Service.
Enables agent-to-agent communication using the A2A SDK.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from a2a.server.apps import A2AStarletteApplication
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message
from a2a.types import AgentCard, AgentCapabilities, AgentSkill, DataPart
import logging
import json

from agent.pool_risk_agent import PoolRiskAgent

logger = logging.getLogger(__name__)


class PoolRiskAgentExecutor(AgentExecutor):
    """Handles incoming A2A message events and invokes the Pool Risk LangGraph agent."""

    def __init__(self):
        """Initialize the agent executor."""
        self.agent = PoolRiskAgent()
        logger.info("Pool Risk Agent Executor initialized")
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute agent request via A2A protocol.
        
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
            
            # Create AgentRequest for the agent
            from common_ai.mappings.schemas import AgentRequest
            agent_request = AgentRequest(
                user_question=user_question,
                pool_address=pool_address,
                trace_id=trace_id
            )
            
            # Invoke the agent
            result = await self.agent.invoke(agent_request)
            
            # AgentResponse is a Pydantic model, use model_dump() to serialize
            response_text = json.dumps({
                "answer": result.answer,
                "metadata": result.metadata or {},
                "risk_score": result.risk_score or 0
            })
            
            await event_queue.enqueue_event(new_agent_text_message(response_text))
            
        except Exception as e:
            logger.error(f"Pool Risk agent execution failed: {e}")
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
    logger.info("Building A2A application for Pool Risk Service")
    
    # Define agent card with A2A protocol v0.3 schema
    agent_card = AgentCard(
        name="Pool Risk Agent",
        description="Uniswap V3 liquidity pool risk analysis specialist",
        url="http://localhost:8001/a2a",
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
                id="concentration-risk-analysis",
                name="Concentration Risk Analysis",
                description="Analyze liquidity concentration risk in Uniswap V3 pools",
                tags=["risk", "liquidity", "uniswap"]
            ),
            AgentSkill(
                id="liquidity-depth-assessment",
                name="Liquidity Depth Assessment",
                description="Assess liquidity depth and slippage risk",
                tags=["liquidity", "depth", "slippage"]
            ),
            AgentSkill(
                id="market-risk-evaluation",
                name="Market Risk Evaluation",
                description="Evaluate market risk factors for the pool",
                tags=["market", "risk", "volatility"]
            ),
            AgentSkill(
                id="composite-risk-scoring",
                name="Composite Risk Scoring",
                description="Generate comprehensive risk scores",
                tags=["risk", "score", "analysis"]
            )
        ]
    )
    
    # Create request handler with in-memory task store
    handler = DefaultRequestHandler(
        agent_executor=PoolRiskAgentExecutor(),
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
