"""
Backend Orchestrator API routers.
"""

import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent / "common_ai"))

from fastapi import APIRouter, HTTPException
from common_ai.mappings.schemas import OrchestratorRequest, OrchestratorResponse
from common_ai.gpt_family import init_models, MicroserviceModels
from common_ai.common_utils.utils import load_prompts, load_config
from workflows.rag.orchestrator import OrchestratorGraph
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize orchestrator (singleton)
orchestrator_graph = None


def get_orchestrator():
    """Get or create orchestrator graph instance."""
    global orchestrator_graph
    if orchestrator_graph is None:
        # Load config and prompts
        config_path = Path(__file__).parent.parent / "config.json"
        config = load_config(str(config_path))
        prompts_path = Path(__file__).parent.parent / "workflows" / "rag" / "config" / "tasks.yml"
        prompts = load_prompts(str(prompts_path))
        system_prompt = prompts.get("orchestrator_agent", {}).get("system", "")
        
        # Initialize LLM
        models = init_models(MicroserviceModels.BACKEND)
        llm = models[MicroserviceModels.BACKEND.value[0]]  # Get first model from service
        
        # Build graph
        orchestrator_graph = OrchestratorGraph(
            llm=llm,
            config=config,
            system_prompt=system_prompt
        ).graph
        
        logger.info("Orchestrator initialized")
    
    return orchestrator_graph


@router.post("/v1/orchestrator/invoke", response_model=OrchestratorResponse)
async def invoke_orchestrator(request: OrchestratorRequest):
    """
    Invoke orchestrator to coordinate sub-agents.
    
    Args:
        request: OrchestratorRequest with query and pool_address
        
    Returns:
        OrchestratorResponse with synthesized analysis
    """
    try:
        graph = get_orchestrator()
        
        input_state = {
            "query": request.query,
            "pool_address": request.pool_address
        }
        
        # Configure LangSmith tracing
        config = {}
        
        result = await graph.ainvoke(input_state, config=config)
        
        logger.info(f"Graph result keys: {result.keys()}")
        logger.info(f"Graph result: {result}")
        
        return OrchestratorResponse(
            answer=result.get("answer", "No answer generated"),
            metadata=result.get("metadata", {}),
            risk_score=result.get("risk_score", 0.0)
        )
    except Exception as e:
        logger.error(f"Orchestrator invocation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "backend-orchestrator"}
