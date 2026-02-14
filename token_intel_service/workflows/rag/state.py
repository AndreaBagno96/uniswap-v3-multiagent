"""
State definitions for Token Intelligence RAG workflow.
"""

from typing import TypedDict, Optional, Dict, Any, List, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class InputState(BaseModel):
    """Input state schema for token intelligence analysis."""
    user_question: str
    pool_address: Optional[str] = None
    trace_id: Optional[str] = None


class OutputState(BaseModel):
    """Output state schema for token intelligence analysis."""
    answer: str
    metadata: Optional[Dict[str, Any]] = None


class AnalysisPlan(BaseModel):
    """Structured output for the planning step."""
    reasoning: str = Field(description="Explanation of why these tools are needed based on the user's question")
    tools_to_call: List[str] = Field(description="List of tool names to execute. Available: resolve_pool_tokens, check_token_security, search_token_sentiment, classify_token_risk")
    needs_comprehensive: bool = Field(default=False, description="If True, run all token intelligence tools for full analysis")


class OverallState(TypedDict):
    """Overall state maintained throughout the graph execution."""
    # Input
    user_question: str
    pool_address: Optional[str]
    trace_id: Optional[str]
    
    # Planning step (for Plan-and-Execute pattern)
    plan: Optional[str]  # Agent's reasoning for tool selection
    tools_to_call: Optional[List[str]]  # Which tools the agent decided to use
    
    # Message history for tool calling
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Intermediate processing
    enhanced_query: Optional[str]
    resolved_tokens: Optional[Dict[str, Any]]
    security_results: Optional[List[Dict[str, Any]]]
    sentiment_results: Optional[List[Dict[str, Any]]]
    classifications: Optional[Dict[str, str]]
    tool_results: Optional[List[Dict[str, Any]]]
    synthesized_answer: Optional[str]
    exit_flag: bool
    
    # Output
    answer: str
    metadata: Optional[Dict[str, Any]]
