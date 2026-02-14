"""
Pool Risk Agent - Main agent implementation.
Orchestrates LangGraph workflow for pool risk analysis with MCP tool calling.

Features:
- Dynamic tool selection based on user question (Plan-and-Execute pattern)
- MCP protocol for tool calling via HTTP transport
- Graceful fallback if MCP server unavailable
- Tool caching at startup for performance
"""

import os
import sys
import asyncio
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import logging

# Path setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from langchain_core.tools import BaseTool
from common_ai.gpt_family import init_models, MicroserviceModels
from common_ai.common_utils.utils import load_config, load_prompts
from common_ai.mappings.schemas import AgentRequest, AgentResponse
from utils import GraphPaginator, CacheManager
from workflows.rag.pool_risk import PoolRiskGraph
from workflows.rag.plan_execute import PlanExecuteGraph

load_dotenv()
logger = logging.getLogger(__name__)


class PoolRiskAgent:
    """
    Pool risk analysis agent using LangGraph workflow with MCP tools.
    
    The agent dynamically selects which analysis tools to run based on
    the user's question, using the MCP protocol for tool discovery and execution.
    Falls back to static analysis if MCP server is unavailable.
    """
    
    def __init__(self):
        """Initialize the pool risk agent with MCP tool caching."""
        logger.info("Initializing Pool Risk Agent...")
        
        # Load configuration
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        self.config = load_config(config_path)
        logger.info("Configuration loaded")
        
        # Load prompts
        prompts_path = os.path.join(
            os.path.dirname(__file__), 
            '..', 
            'workflows', 
            'rag', 
            'config', 
            'tasks.yml'
        )
        self.prompts = load_prompts(prompts_path)
        logger.info("Prompts loaded")
        
        # Initialize models
        models = init_models(MicroserviceModels.POOL_RISK_SERVICE)
        self.llm = models["gpt-4o-mini"]
        logger.info("Language model initialized")
        
        # Initialize The Graph utilities (for fallback)
        api_key = os.getenv("THE_GRAPH_API_KEY")
        if not api_key:
            logger.warning("THE_GRAPH_API_KEY not set, using fallback endpoint")
            endpoint = self.config["api"]["fallback_endpoint"]
        else:
            base_url = self.config["api"]["base_url"]
            subgraph_id = self.config["api"]["subgraph_id"]
            endpoint = f"{base_url}/{api_key}/subgraphs/id/{subgraph_id}"
        
        self.paginator = GraphPaginator(endpoint, self.config)
        self.cache = CacheManager(self.config)
        logger.info(f"GraphPaginator initialized with endpoint: {endpoint[:50]}...")
        
        # MCP tool state
        self.mcp_tools: List[BaseTool] = []
        self.mcp_available: bool = False
        self.mcp_client = None
        
        # Initialize MCP tools (cached at startup)
        self._init_mcp_tools_sync()
        
        # Get prompts
        system_prompt = self.prompts["prompts"]["pool_risk_agent"]["system"]
        planning_prompt = self.prompts["prompts"].get("planning_agent", {}).get(
            "system", 
            "You are an expert DeFi analyst. Analyze the user's question and decide which risk analysis tools are needed."
        )
        
        # Build appropriate graph based on MCP availability
        if self.mcp_available and self.mcp_tools:
            logger.info("Building Plan-Execute graph with MCP tools")
            self.graph_instance = PlanExecuteGraph(
                llm=self.llm,
                mcp_tools=self.mcp_tools,
                config=self.config,
                system_prompt=system_prompt,
                planning_prompt=planning_prompt
            )
        else:
            logger.info("Building fallback static graph (MCP unavailable)")
            self.graph_instance = PoolRiskGraph(
                llm=self.llm,
                paginator=self.paginator,
                cache=self.cache,
                config=self.config,
                system_prompt=system_prompt
            )
        
        logger.info("LangGraph workflow built successfully")
    
    def _init_mcp_tools_sync(self) -> None:
        """
        Initialize MCP tools synchronously.
        Uses httpx to check if MCP server is available.
        """
        import httpx
        
        mcp_url = os.getenv("POOL_RISK_MCP_URL", "http://localhost:8002/mcp")
        
        try:
            # Try to reach the MCP endpoint directly
            # FastMCP with streamable-http transport accepts POST at /mcp
            # Just check if port is reachable
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
        mcp_url = os.getenv("POOL_RISK_MCP_URL", "http://localhost:8002/mcp")
        
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            
            logger.info(f"Connecting to MCP server at {mcp_url}...")
            
            self.mcp_client = MultiServerMCPClient({
                "pool_risk": {
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
    
    async def invoke(self, request: AgentRequest) -> AgentResponse:
        """
        Invoke the agent with a request.
        
        Args:
            request: Agent request with user question and pool address
            
        Returns:
            Agent response with analysis results
        """
        logger.info(f"Invoking agent for pool: {request.pool_address}")
        logger.info(f"Question: {request.user_question}")
        
        # Lazy load MCP tools on first request if server was available at startup
        if self.mcp_available and not self.mcp_tools:
            logger.info("Lazy loading MCP tools on first request...")
            await self._init_mcp_tools()
            
            # If tools loaded successfully, rebuild the graph with MCP
            if self.mcp_tools:
                system_prompt = self.prompts["prompts"]["pool_risk_agent"]["system"]
                planning_prompt = self.prompts["prompts"].get("planning_agent", {}).get(
                    "system", 
                    "You are an expert DeFi analyst. Analyze the user's question and decide which risk analysis tools are needed."
                )
                self.graph_instance = PlanExecuteGraph(
                    llm=self.llm,
                    mcp_tools=self.mcp_tools,
                    config=self.config,
                    system_prompt=system_prompt,
                    planning_prompt=planning_prompt
                )
                logger.info("Rebuilt graph with MCP tools")
        
        logger.info(f"MCP available: {self.mcp_available}, Tools loaded: {len(self.mcp_tools)}")
        
        try:
            # Prepare initial state
            initial_state = {
                "user_question": request.user_question,
                "pool_address": request.pool_address,
                "trace_id": request.trace_id,
                "exit_flag": False,
                "messages": []  # For MCP tool calling
            }
            
            # Execute LangGraph workflow
            result = await self.graph_instance.graph.ainvoke(
                initial_state,
                config={
                    "run_name": "pool-risk-agent",
                    "metadata": {
                        "pool_address": request.pool_address,
                        "trace_id": request.trace_id,
                        "mcp_enabled": self.mcp_available
                    }
                }
            )
            
            logger.info("LangGraph execution completed")
            
            # Build response
            metadata = result.get("metadata", {})
            metadata["mcp_available"] = self.mcp_available
            
            response = AgentResponse(
                answer=result["answer"],
                metadata=metadata,
                risk_score=metadata.get("risk_score")
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Agent invocation failed: {str(e)}", exc_info=True)
            raise
