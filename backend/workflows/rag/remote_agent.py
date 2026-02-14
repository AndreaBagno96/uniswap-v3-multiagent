"""
Remote Agent Connections for A2A Protocol.
Wraps A2AClient for communicating with sub-agents via A2A protocol.
"""

from typing import Callable
import httpx

from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
import logging

logger = logging.getLogger(__name__)

TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """A class to hold the connections to the remote agents."""

    def __init__(
        self,
        agent_card: AgentCard,
        agent_url: str,
        http_client: httpx.AsyncClient
    ):
        """
        Initialize remote agent connection.
        
        Args:
            agent_card: The agent's card with capabilities
            agent_url: The A2A RPC endpoint URL
            http_client: Shared httpx async client
        """
        self._httpx_client = http_client
        self.agent_client = A2AClient(self._httpx_client, agent_card, url=agent_url)
        self.card = agent_card
        self.pending_tasks: set = set()
        logger.info(f"RemoteAgentConnections initialized for {agent_card.name} at {agent_url}")

    def get_agent(self) -> AgentCard:
        """Get the agent card."""
        return self.card

    async def send_message(
        self,
        message_request: SendMessageRequest
    ) -> SendMessageResponse:
        """
        Send a message to the remote agent.
        
        Args:
            message_request: A2A message request
            
        Returns:
            A2A response containing Task
        """
        logger.info(f"Sending A2A message to {self.card.name}")
        return await self.agent_client.send_message(message_request)
