"""
Token Intelligence Agent - wraps LangGraph workflow with MCP tool calling.

Features:
- Dynamic tool selection based on user question (Plan-and-Execute pattern)
- MCP protocol for tool calling via HTTP transport
- Graceful fallback if MCP server unavailable
- Tool caching at startup for performance
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List

# Setup path to access common_ai
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common_ai"))

from dotenv import load_dotenv
import logging
from langchain_core.tools import BaseTool
from common_ai.gpt_family import init_models, MicroserviceModels
from common_ai.common_utils.utils import load_prompts, load_config
from workflows.rag.token_intel import TokenIntelligenceGraph
from workflows.rag.plan_execute import PlanExecuteGraph

load_dotenv()
logger = logging.getLogger(__name__)


class TokenIntelligenceAgent:
    """
    Token intelligence agent using LangGraph workflow with MCP tools.
    
    The agent dynamically selects which analysis tools to run based on
    the user's question, using the MCP protocol for tool discovery and execution.
    Falls back to static analysis if MCP server is unavailable.
    """
    
    def __init__(self):
        """Initialize the agent with config, tools, and LangGraph workflow."""
        logger.info("Initializing Token Intelligence Agent...")
        
        # Load configuration
        config_path = Path(__file__).parent.parent / "config.json"
        self.config = load_config(str(config_path))
        logger.info("Configuration loaded")
        
        # Load prompts
        config_dir = Path(__file__).parent.parent / "workflows" / "rag" / "config"
        prompts_file = config_dir / "tasks.yml"
        self.prompts = load_prompts(str(prompts_file))
        logger.info("Prompts loaded")
        
        # Initialize LLM
        models = init_models(MicroserviceModels.TOKEN_INTEL_SERVICE)
        self.llm = models[MicroserviceModels.TOKEN_INTEL_SERVICE.value[0]]
        logger.info("Language model initialized")
        
        # MCP tool state
        self.mcp_tools: List[BaseTool] = []
        self.mcp_available: bool = False
        self.mcp_client = None
        
        # Initialize MCP tools (check availability at startup)
        self._init_mcp_tools_sync()
        
        # Get prompts
        self.system_prompt = self.prompts.get("prompts", {}).get("token_intelligence_agent", {}).get("system", "")
        planning_prompt = self.prompts.get("prompts", {}).get("planning_agent", {}).get(
            "system",
            "You are an expert cryptocurrency analyst. Analyze the user's question and decide which token intelligence tools are needed."
        )
        self.planning_prompt = planning_prompt
        
        # Build appropriate graph based on MCP availability
        if self.mcp_available:
            logger.info("MCP server available, will load tools on first request")
            # Will be built on first request when tools are loaded
            self.graph = None
        else:
            logger.info("Building fallback static graph (MCP unavailable)")
            self.graph = TokenIntelligenceGraph(
                llm=self.llm,
                config=self.config,
                system_prompt=self.system_prompt
            ).graph
        
        logger.info("Token Intelligence Agent initialized")
    
    def _init_mcp_tools_sync(self) -> None:
        """
        Check MCP server availability synchronously.
        Uses httpx to check if MCP server is reachable.
        """
        import httpx
        
        mcp_url = os.getenv("TOKEN_INTEL_MCP_URL", "http://localhost:8004/mcp")
        
        try:
            # Try to reach the MCP endpoint
            response = httpx.post(
                mcp_url,
                json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
                timeout=5.0,
                headers={"Content-Type": "application/json"}
            )
            # Any response (even error) means server is up
            self.mcp_available = True
            self._mcp_url = mcp_url
            logger.info(f"MCP server available at {mcp_url}, tools will be loaded on first request")
            
        except httpx.ConnectError:
            logger.warning(f"MCP server not reachable at {mcp_url}")
            self.mcp_available = False
            self.mcp_tools = []
        except Exception as e:
            # If we get any other exception but connection worked, MCP is available
            if "Connection" not in str(type(e).__name__):
                self.mcp_available = True
                self._mcp_url = mcp_url
                logger.info(f"MCP server available at {mcp_url} (probe returned: {type(e).__name__})")
            else:
                logger.warning(f"Failed to check MCP server: {e}")
                self.mcp_available = False
                self.mcp_tools = []
    
    async def _init_mcp_tools(self) -> None:
        """
        Initialize MCP client and cache tools.
        Fails gracefully if MCP server is unavailable.
        """
        mcp_url = os.getenv("TOKEN_INTEL_MCP_URL", "http://localhost:8004/mcp")
        
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            
            logger.info(f"Connecting to MCP server at {mcp_url}...")
            
            self.mcp_client = MultiServerMCPClient({
                "token_intel": {
                    "url": mcp_url,
                    "transport": "http",
                }
            })
            
            # Load and cache tools
            self.mcp_tools = await self.mcp_client.get_tools()
            
            if self.mcp_tools:
                self.mcp_available = True
                tool_names = [t.name for t in self.mcp_tools]
                logger.info(f"MCP tools cached successfully: {tool_names}")
            else:
                logger.warning("MCP server returned no tools")
                self.mcp_available = False
                
        except ImportError:
            logger.warning("langchain-mcp-adapters not installed, MCP unavailable")
            self.mcp_available = False
            self.mcp_tools = []
            
        except Exception as e:
            logger.warning(f"MCP initialization failed (server may be down): {e}")
            self.mcp_available = False
            self.mcp_tools = []
    
    async def refresh_mcp_tools(self) -> bool:
        """
        Refresh MCP tools (useful if server was restarted).
        
        Returns:
            True if tools were refreshed successfully
        """
        await self._init_mcp_tools()
        return self.mcp_available
    
    @property
    def is_mcp_available(self) -> bool:
        """Check if MCP tools are available."""
        return self.mcp_available
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return [t.name for t in self.mcp_tools] if self.mcp_tools else []
    
    async def ainvoke(self, user_question: str, pool_address: str = None, trace_id: str = None) -> Dict[str, Any]:
        """
        Process a user question through the LangGraph workflow.
        
        Args:
            user_question: User's question
            pool_address: Optional pool/pair address
            trace_id: Optional trace ID for LangSmith
            
        Returns:
            Dict with answer and metadata
        """
        logger.info(f"Invoking agent for pool: {pool_address}")
        logger.info(f"Question: {user_question}")
        
        # Lazy load MCP tools on first request if server was available at startup
        if self.mcp_available and not self.mcp_tools:
            logger.info("Lazy loading MCP tools on first request...")
            await self._init_mcp_tools()
            
            # If tools loaded successfully, build the Plan-Execute graph
            if self.mcp_tools:
                self.graph = PlanExecuteGraph(
                    llm=self.llm,
                    mcp_tools=self.mcp_tools,
                    config=self.config,
                    system_prompt=self.system_prompt,
                    planning_prompt=self.planning_prompt
                ).graph
                logger.info("Built Plan-Execute graph with MCP tools")
        
        # If still no graph (MCP failed), build fallback
        if self.graph is None:
            logger.info("Building fallback static graph")
            self.graph = TokenIntelligenceGraph(
                llm=self.llm,
                config=self.config,
                system_prompt=self.system_prompt
            ).graph
        
        logger.info(f"MCP available: {self.mcp_available}, Tools loaded: {len(self.mcp_tools)}")
        
        input_state = {
            "user_question": user_question,
            "pool_address": pool_address,
            "exit_flag": False,
            "messages": []  # For MCP tool calling
        }
        
        # Configure LangSmith tracing
        config = {
            "run_name": "token-intel-agent",
            "metadata": {
                "pool_address": pool_address,
                "trace_id": trace_id,
                "mcp_enabled": self.mcp_available
            }
        }
        if trace_id:
            config["run_name"] = f"token-intel-{trace_id}"
        
        try:
            result = await self.graph.ainvoke(input_state, config=config)
            
            # Add MCP status to metadata
            metadata = result.get("metadata", {})
            metadata["mcp_available"] = self.mcp_available
            
            return {
                "answer": result.get("answer", "No answer generated"),
                "metadata": metadata
            }
        except Exception as e:
            logger.error(f"Token intelligence analysis failed: {e}")
            return {
                "answer": f"Analysis failed: {str(e)}",
                "metadata": {"error": str(e), "mcp_available": self.mcp_available}
            }
