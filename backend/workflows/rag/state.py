"""
State definitions for the Orchestrator agent.
Defines the state that flows through the StateGraph.
"""

from typing import Any, Dict, Optional, TypedDict


class InputState(TypedDict):
    """Input state for the orchestrator."""
    query: str
    pool_address: Optional[str]


class OutputState(TypedDict):
    """Output state from the orchestrator."""
    answer: str
    metadata: Optional[Dict[str, Any]]
    risk_score: Optional[float]


class OverallState(TypedDict, total=False):
    """Overall state maintained throughout the graph execution."""
    # Input
    query: str
    pool_address: Optional[str]
    
    # Agent discovery (from discover_agents node)
    agents_info: str  # Formatted string of available agents and capabilities
    
    # Routing decision (from analyze_query node)
    routing_decision: str  # "pool_risk", "token_intel", "both"
    routing_reasoning: str
    
    # Sub-agent results (from invoke_pool_risk and invoke_token_intel nodes)
    pool_risk_result: Optional[Dict[str, Any]]
    token_intel_result: Optional[Dict[str, Any]]
    
    # Synthesis (from synthesize_results node)
    final_answer: str
    
    # Final output (from finalize_output node)
    answer: str
    metadata: Optional[Dict[str, Any]]
    risk_score: Optional[float]
