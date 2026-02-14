"""
Shared Pydantic models for request/response schemas across all services.
Ensures consistent data structures for inter-service communication.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class AgentRequest(BaseModel):
    """Request schema for agent invocation."""
    user_question: str = Field(..., description="User's query or question")
    pool_address: Optional[str] = Field(None, description="Uniswap V3 pool address to analyze")
    trace_id: Optional[str] = Field(None, description="Unique trace ID for observability")
    language: str = Field(default="en", description="Response language")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_question": "What is the concentration risk?",
                "pool_address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
                "trace_id": "abc-123-def",
                "language": "en"
            }
        }


class AgentResponse(BaseModel):
    """Response schema from agent invocation."""
    answer: str = Field(..., description="Agent's response to the query")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    references: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Supporting references")
    risk_score: Optional[int] = Field(None, description="Composite risk score (0-100)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "The pool has high concentration risk with a Gini coefficient of 0.99.",
                "metadata": {"agent": "pool_risk", "execution_time": 2.5},
                "references": [],
                "risk_score": 76
            }
        }


class OrchestratorRequest(BaseModel):
    """Request schema for orchestrator."""
    query: str = Field(..., description="User's query")
    pool_address: Optional[str] = Field(None, description="Pool address")
    language: str = Field(default="en", description="Response language")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "Analyze this pool for risks",
                "pool_address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
                "language": "en"
            }
        }


class OrchestratorResponse(BaseModel):
    """Response schema from orchestrator."""
    answer: str = Field(..., description="Synthesized answer from multiple agents")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Execution metadata including sub-agent results")
    risk_score: Optional[float] = Field(None, description="Composite risk score (0-100)")
