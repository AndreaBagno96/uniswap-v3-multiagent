"""
State definitions for Pool Risk RAG workflow.
"""

from typing import TypedDict, Optional, Dict, Any, List, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class InputState(BaseModel):
    """Input state schema for pool risk analysis."""
    user_question: str
    pool_address: Optional[str] = None
    trace_id: Optional[str] = None


class OutputState(BaseModel):
    """Output state schema for pool risk analysis."""
    answer: str
    metadata: Optional[Dict[str, Any]] = None


class AnalysisPlan(BaseModel):
    """Structured output for the planning step."""
    reasoning: str = Field(description="Explanation of why these tools are needed based on the user's question")
    tools_to_call: List[str] = Field(description="List of tool names to execute. Available: analyze_concentration_risk, analyze_liquidity_depth, analyze_market_risk, analyze_behavioral_risk, calculate_composite_risk_score")
    needs_comprehensive: bool = Field(default=False, description="If True, run all risk tools and calculate composite score")


class OverallState(TypedDict):
    """Overall state maintained throughout the graph execution."""
    # Input
    user_question: str
    pool_address: Optional[str]
    trace_id: Optional[str]
    
    # Planning step (new)
    plan: Optional[str]  # Agent's reasoning for tool selection
    tools_to_call: Optional[List[str]]  # Which tools the agent decided to use
    
    # Message history for tool calling
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Intermediate processing
    enhanced_query: Optional[str]
    extracted_entities: Optional[Dict[str, Any]]
    tool_results: Optional[List[Dict[str, Any]]]
    synthesized_answer: Optional[str]
    exit_flag: bool
    
    # Output
    answer: str
    metadata: Optional[Dict[str, Any]]
