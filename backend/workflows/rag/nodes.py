"""
Node implementations for Orchestrator RAG workflow.
Uses A2A protocol for agent-to-agent communication.
"""

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import httpx
import asyncio
import logging
import json
from uuid import uuid4

from a2a.client import A2ACardResolver
from a2a.types import MessageSendParams, SendMessageRequest

from .remote_agent import RemoteAgentConnections
from .utils import format_agents_info

logger = logging.getLogger(__name__)


class OrchestratorNodes:
    """Node implementations for orchestrator graph using A2A protocol."""
    
    def __init__(
        self,
        llm: ChatOpenAI,
        config: Dict[str, Any],
        system_prompt: str,
        a2a_http_client: httpx.AsyncClient,
        remote_agent_addresses: Dict[str, str]
    ):
        """
        Initialize nodes with dependencies.
        
        Args:
            llm: Language model for routing and synthesis
            config: Configuration dictionary
            system_prompt: System prompt for the agent
            a2a_http_client: Shared httpx async client for A2A
            remote_agent_addresses: Dict mapping agent name to A2A base URL
        """
        self.llm = llm
        self.config = config
        self.system_prompt = system_prompt
        self.a2a_http_client = a2a_http_client
        self.remote_agent_addresses = remote_agent_addresses
        self.timeout = config.get("orchestration", {}).get("timeout", 120)
        
        # A2A connections - populated by discover_agents
        self.remote_agent_connections: Dict[str, RemoteAgentConnections] = {}
        self.cards: Dict[str, Any] = {}
    
    async def discover_agents(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Discover available agents by fetching their agent cards.
        Creates RemoteAgentConnections for each available agent.
        """
        logger.info(f"Discovering agents from: {list(self.remote_agent_addresses.keys())}")
        
        async def resolve_agent_card(agent_name: str, agent_url: str, client: httpx.AsyncClient):
            """Resolve a single agent's card."""
            try:
                # Use the full A2A URL as base (e.g., http://localhost:8001/a2a)
                # The agent card is at {base_url}/.well-known/agent.json
                resolver = A2ACardResolver(httpx_client=client, base_url=agent_url)
                card = await resolver.get_agent_card(relative_card_path=".well-known/agent.json")
                connection = RemoteAgentConnections(
                    agent_card=card,
                    agent_url=agent_url,
                    http_client=client
                )
                logger.info(f"Successfully resolved agent: {agent_name} ({card.name})")
                return agent_name.lower(), card, connection

            except Exception as e:
                logger.error(f"[A2A discover agents] - Failed to resolve agent '{agent_name}' at '{agent_url}': {e}")
                return None

        # Resolve all agents in parallel
        tasks = [
            resolve_agent_card(agent, address, self.a2a_http_client)
            for agent, address in self.remote_agent_addresses.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        
        # Store successful connections
        for result in results:
            if not result:
                continue
            agent_name, card, connection = result
            self.remote_agent_connections[agent_name] = connection
            self.cards[card.name] = card

        formatted_agents_info = format_agents_info(self.cards)
        logger.info(f"Discovered {len(self.remote_agent_connections)} agents")
        
        return {"agents_info": formatted_agents_info}
    
    def analyze_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze user query to determine routing."""
        user_question = state["query"]
        
        routing_prompt = f"""{self.system_prompt}

Analyze this query and determine which agents to invoke:
Query: {user_question}

Respond with JSON containing:
- "route": "pool_risk" | "token_intel" | "both"
- "reasoning": brief explanation

Examples:
- "What's the liquidity depth?" → {{"route": "pool_risk", "reasoning": "Query about liquidity metrics"}}
- "Is this token a scam?" → {{"route": "token_intel", "reasoning": "Query about token security"}}
- "Analyze this pool" → {{"route": "both", "reasoning": "Comprehensive analysis requested"}}
"""
        
        try:
            response = self.llm.invoke([HumanMessage(content=routing_prompt)])
            import json
            routing = json.loads(response.content.strip("```json").strip("```").strip())
            
            return {
                "routing_decision": routing.get("route", "both"),
                "routing_reasoning": routing.get("reasoning", "")
            }
        except Exception as e:
            logger.error(f"Routing analysis failed: {e}")
            # Default to both on error
            return {
                "routing_decision": "both",
                "routing_reasoning": "Error in routing, invoking all agents"
            }
    
    async def invoke_pool_risk(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke Pool Risk Agent via A2A protocol."""
        user_question = state["query"]
        pool_address = state.get("pool_address")
        
        # Check if agent was discovered
        if "pool_risk" not in self.remote_agent_connections:
            logger.error("Pool Risk agent not discovered")
            return {
                "pool_risk_result": {
                    "answer": "Pool Risk agent unavailable",
                    "metadata": {"error": "Agent not discovered"},
                    "risk_score": 0.0
                }
            }
        
        try:
            connection = self.remote_agent_connections["pool_risk"]
            
            # Build A2A message request with DataPart for structured data
            request = SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(
                    message={
                        "role": "user",
                        "parts": [{
                            "kind": "data",
                            "data": {
                                "user_question": user_question,
                                "pool_address": pool_address,
                                "trace_id": state.get("trace_id")
                            }
                        }],
                        "messageId": uuid4().hex,
                    }
                )
            )
            
            # Send via A2A
            response = await connection.send_message(request)
            result = self._extract_result_from_response(response)
            
            return {
                "pool_risk_result": {
                    "answer": result.get("answer", ""),
                    "metadata": result.get("metadata", {}),
                    "risk_score": result.get("risk_score", 0.0)
                }
            }
        except Exception as e:
            logger.error(f"Pool Risk Agent A2A invocation failed: {e}")
            return {
                "pool_risk_result": {
                    "answer": f"Pool risk analysis failed: {str(e)}",
                    "metadata": {"error": str(e)},
                    "risk_score": 0.0
                }
            }
    
    async def invoke_token_intel(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke Token Intelligence Agent via A2A protocol."""
        user_question = state["query"]
        pool_address = state.get("pool_address")
        
        # Check if agent was discovered
        if "token_intelligence" not in self.remote_agent_connections:
            logger.error("Token Intelligence agent not discovered")
            return {
                "token_intel_result": {
                    "answer": "Token Intelligence agent unavailable",
                    "metadata": {"error": "Agent not discovered"},
                    "risk_score": 0.0
                }
            }
        
        try:
            connection = self.remote_agent_connections["token_intelligence"]
            
            # Build A2A message request with DataPart for structured data
            request = SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(
                    message={
                        "role": "user",
                        "parts": [{
                            "kind": "data",
                            "data": {
                                "user_question": user_question,
                                "pool_address": pool_address,
                                "trace_id": state.get("trace_id")
                            }
                        }],
                        "messageId": uuid4().hex,
                    }
                )
            )
            
            # Send via A2A
            response = await connection.send_message(request)
            result = self._extract_result_from_response(response)
            
            return {
                "token_intel_result": {
                    "answer": result.get("answer", ""),
                    "metadata": result.get("metadata", {}),
                    "risk_score": result.get("risk_score", 0.0)
                }
            }
        except Exception as e:
            logger.error(f"Token Intelligence Agent A2A invocation failed: {e}")
            return {
                "token_intel_result": {
                    "answer": f"Token intelligence analysis failed: {str(e)}",
                    "metadata": {"error": str(e)},
                    "risk_score": 0.0
                }
            }
    
    def _extract_result_from_response(self, response) -> Dict[str, Any]:
        """
        Extract answer/metadata from A2A SendMessageResponse.
        
        Args:
            response: A2A SendMessageResponse containing Task or Message
            
        Returns:
            Dict with answer, metadata, risk_score
        """
        try:
            # Response contains result which is a Task or Message
            result = response.root.result if hasattr(response, 'root') else response.result
            
            # If result is a Task, get the message from status
            if hasattr(result, 'status') and hasattr(result.status, 'message'):
                message = result.status.message
            elif hasattr(result, 'parts'):
                message = result
            else:
                logger.warning(f"Unexpected A2A response structure: {type(result)}")
                return {"answer": str(result), "metadata": {}, "risk_score": 0.0}
            
            # Extract text from message parts
            if message and hasattr(message, 'parts'):
                for part in message.parts:
                    if hasattr(part, 'kind') and part.kind == 'text':
                        text = part.text
                        # Try to parse as JSON (agent may return structured response)
                        try:
                            parsed = json.loads(text)
                            return {
                                "answer": parsed.get("answer", text),
                                "metadata": parsed.get("metadata", {}),
                                "risk_score": parsed.get("risk_score", 0.0)
                            }
                        except json.JSONDecodeError:
                            return {"answer": text, "metadata": {}, "risk_score": 0.0}
            
            return {"answer": "", "metadata": {}, "risk_score": 0.0}
            
        except Exception as e:
            logger.error(f"Failed to extract result from A2A response: {e}")
            return {"answer": f"Error parsing response: {e}", "metadata": {}, "risk_score": 0.0}
    
    def synthesize_results(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize results from sub-agents."""
        user_question = state["query"]
        pool_risk = state.get("pool_risk_result", {})
        token_intel = state.get("token_intel_result", {})
        
        context = f"""
User Question: {user_question}

"""
        
        if pool_risk:
            context += f"Pool Risk Analysis:\n{pool_risk.get('answer', 'N/A')}\n\n"
        
        if token_intel:
            context += f"Token Intelligence Analysis:\n{token_intel.get('answer', 'N/A')}\n\n"
        
        synthesis_prompt = f"""{self.system_prompt}

Synthesize the following agent results into a coherent, actionable answer:

{context}

Provide a comprehensive answer that:
1. Directly addresses the user's question
2. Highlights critical risks
3. Provides clear recommendations
"""
        
        try:
            response = self.llm.invoke([HumanMessage(content=synthesis_prompt)])
            answer = response.content
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            answer = f"Failed to synthesize results: {e}"
        
        return {
            "final_answer": answer
        }
    
    def finalize_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare final output."""
        pool_risk = state.get("pool_risk_result", {})
        token_intel = state.get("token_intel_result", {})
        
        # Calculate composite risk score
        risk_scores = []
        if pool_risk.get("risk_score"):
            risk_scores.append(pool_risk["risk_score"])
        if token_intel.get("risk_score"):
            risk_scores.append(token_intel["risk_score"])
        
        composite_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0
        
        metadata = {
            "pool_risk": pool_risk.get("metadata", {}),
            "token_intel": token_intel.get("metadata", {}),
            "composite_risk_score": composite_risk
        }
        
        # Get the synthesized answer from state
        final_answer = state.get("final_answer", state.get("answer", "No answer generated"))
        
        return {
            "answer": final_answer,
            "metadata": metadata,
            "risk_score": composite_risk
        }
