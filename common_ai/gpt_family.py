"""
Centralized model initialization for all microservices.
Uses OpenAI ChatGPT models with standardized configurations.
"""

import os
from enum import Enum
from typing import Dict
from langchain_openai import ChatOpenAI


class MicroserviceModels(Enum):
    """Enum defining which models each microservice uses."""
    BACKEND = ["gpt-4o-mini", "gpt-4o"]
    POOL_RISK_SERVICE = ["gpt-4o-mini"]
    TOKEN_INTEL_SERVICE = ["gpt-4o-mini"]


def _make_gpt(model_name: str, **kwargs) -> ChatOpenAI:
    """
    Create a ChatOpenAI instance with standardized configuration.
    
    Args:
        model_name: Model identifier
        **kwargs: Additional parameters for ChatOpenAI
        
    Returns:
        Configured ChatOpenAI instance
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        **kwargs
    )


# Model builders with pre-configured settings
MODEL_BUILDERS = {
    "gpt-4o-mini": lambda: _make_gpt("gpt-4o-mini", temperature=0.0),
    "gpt-4o": lambda: _make_gpt("gpt-4o", temperature=0.0),
}


def init_models(service_name: MicroserviceModels) -> Dict[str, ChatOpenAI]:
    """
    Initialize all models for a specific microservice.
    
    Args:
        service_name: MicroserviceModels enum member
        
    Returns:
        Dictionary mapping model names to ChatOpenAI instances
        
    Example:
        >>> models = init_models(MicroserviceModels.POOL_RISK_SERVICE)
        >>> llm = models["gpt-4o-mini"]
    """
    model_keys = service_name.value
    return {key: MODEL_BUILDERS[key]() for key in model_keys}
