"""
Streaming response utilities for real-time agent updates.
"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class StreamingStatus(str, Enum):
    """Status indicators for streaming responses."""
    THINKING = "thinking"
    RESPONDING = "responding"
    COMPLETE = "complete"
    ERROR = "error"


class StreamingMessage(BaseModel):
    """Schema for streaming status updates."""
    status: StreamingStatus = Field(..., description="Current execution status")
    message: str = Field(..., description="Status message or partial response")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "thinking",
                "message": "Analyzing pool concentration risk...",
                "metadata": {"step": 1, "total_steps": 4}
            }
        }
