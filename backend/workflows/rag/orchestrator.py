"""
Orchestrator StateGraph - coordinates Pool Risk and Token Intelligence agents.
Uses A2A protocol for agent-to-agent communication.
"""

import httpx
from langgraph.graph import StateGraph, START, END
from .state import InputState, OutputState, OverallState
from .nodes import OrchestratorNodes


class OrchestratorGraph:
    """StateGraph for orchestrating sub-agents via A2A protocol."""
    
    def __init__(
        self,
        llm,
        config,
        system_prompt
    ):
        """
        Initialize the orchestrator graph.
        
        Args:
            llm: Language model
            config: Configuration dict
            system_prompt: System prompt string
        """
        # Create shared httpx client for A2A
        self.a2a_http_client = httpx.AsyncClient(timeout=config.get("orchestration", {}).get("timeout", 120))
        
        # Extract remote agent addresses from config
        remote_agent_addresses = config.get("remote_agent_addresses", {})
        
        self.nodes = OrchestratorNodes(
            llm=llm,
            config=config,
            system_prompt=system_prompt,
            a2a_http_client=self.a2a_http_client,
            remote_agent_addresses=remote_agent_addresses
        )
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the StateGraph workflow."""
        builder = StateGraph(
            OverallState,
            input=InputState,
            output=OutputState
        )
        
        # Add nodes
        builder.add_node("discover_agents", self.nodes.discover_agents)
        builder.add_node("analyze_query", self.nodes.analyze_query)
        builder.add_node("invoke_pool_risk", self.nodes.invoke_pool_risk)
        builder.add_node("invoke_token_intel", self.nodes.invoke_token_intel)
        builder.add_node("synthesize_results", self.nodes.synthesize_results)
        builder.add_node("finalize_output", self.nodes.finalize_output)
        
        # Define flow - start with agent discovery
        builder.add_edge(START, "discover_agents")
        builder.add_edge("discover_agents", "analyze_query")
        
        # Conditional routing based on decision
        def route_to_agents(state: OverallState) -> str:
            decision = state.get("routing_decision", "both")
            if decision == "pool_risk":
                return "invoke_pool_risk_only"
            elif decision == "token_intel":
                return "invoke_token_intel_only"
            else:
                return "invoke_both"
        
        builder.add_conditional_edges(
            "analyze_query",
            route_to_agents,
            {
                "invoke_pool_risk_only": "invoke_pool_risk",
                "invoke_token_intel_only": "invoke_token_intel",
                "invoke_both": "invoke_pool_risk"  # Start with pool risk, then token intel
            }
        )
        
        # Pool risk only path
        builder.add_edge("invoke_pool_risk", "check_token_intel_needed")
        
        # Check if token intel is also needed
        def check_token_intel_needed(state: OverallState) -> str:
            decision = state.get("routing_decision", "both")
            if decision == "both":
                return "invoke_token_intel"
            return "synthesize_results"
        
        builder.add_node("check_token_intel_needed", lambda s: s)
        builder.add_conditional_edges(
            "check_token_intel_needed",
            check_token_intel_needed,
            {
                "invoke_token_intel": "invoke_token_intel",
                "synthesize_results": "synthesize_results"
            }
        )
        
        # All paths converge to synthesis
        builder.add_edge("invoke_token_intel", "synthesize_results")
        builder.add_edge("synthesize_results", "finalize_output")
        builder.add_edge("finalize_output", END)
        
        return builder.compile()
