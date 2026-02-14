"""
Plan-Execute StateGraph - Dynamic tool selection with MCP protocol for Token Intelligence.

This workflow allows the agent to:
1. Plan which tools to call based on the user's question
2. Execute selected tools in parallel via MCP
3. Synthesize results into a final answer
"""

import asyncio
import json
from typing import Dict, Any, List, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END
import logging

from .state import InputState, OutputState, OverallState, AnalysisPlan

logger = logging.getLogger(__name__)


class PlanExecuteGraph:
    """
    StateGraph for plan-and-execute workflow with MCP tools.
    
    The agent:
    1. Analyzes the user's question and plans which tools to call
    2. Executes selected tools in parallel
    3. Synthesizes results into a coherent answer
    """
    
    # Available tools for planning reference
    AVAILABLE_TOOLS = [
        "resolve_pool_tokens",
        "check_token_security",
        "search_token_sentiment",
        "classify_token_risk"
    ]
    
    def __init__(
        self,
        llm: ChatOpenAI,
        mcp_tools: List[BaseTool],
        config: Dict[str, Any],
        system_prompt: str,
        planning_prompt: str
    ):
        """
        Initialize the plan-execute graph.
        
        Args:
            llm: Language model for planning and synthesis
            mcp_tools: List of tools loaded from MCP server
            config: Configuration dictionary
            system_prompt: System prompt for synthesis
            planning_prompt: Prompt for planning step
        """
        self.llm = llm
        self.mcp_tools = mcp_tools
        self.tools_by_name = {tool.name: tool for tool in mcp_tools}
        self.config = config
        self.system_prompt = system_prompt
        self.planning_prompt = planning_prompt
        
        # Create planner LLM with structured output
        self.planner_llm = llm.with_structured_output(AnalysisPlan)
        
        # Create tool-augmented LLM
        self.llm_with_tools = llm.bind_tools(mcp_tools) if mcp_tools else llm
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the StateGraph workflow."""
        builder = StateGraph(
            OverallState,
            input=InputState,
            output=OutputState
        )
        
        # Add nodes
        builder.add_node("plan", self._plan_node)
        builder.add_node("execute_tools", self._execute_tools_node)
        builder.add_node("synthesize", self._synthesize_node)
        builder.add_node("finalize", self._finalize_node)
        builder.add_node("no_tools_response", self._no_tools_response_node)
        
        # Define flow
        builder.add_edge(START, "plan")
        
        # Conditional edge after planning
        builder.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {
                "execute_tools": "execute_tools",
                "no_tools": "no_tools_response",
                "error": "finalize"
            }
        )
        
        builder.add_edge("execute_tools", "synthesize")
        builder.add_edge("synthesize", "finalize")
        builder.add_edge("no_tools_response", "finalize")
        builder.add_edge("finalize", END)
        
        return builder.compile()
    
    def _plan_node(self, state: OverallState) -> Dict[str, Any]:
        """
        Planning node: LLM decides which tools to call.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with plan and tools_to_call
        """
        user_question = state["user_question"]
        pool_address = state.get("pool_address")
        
        # Build planning prompt
        available_tools_desc = "\n".join([
            f"- {tool.name}: {tool.description[:150]}..." 
            for tool in self.mcp_tools
        ]) if self.mcp_tools else "No tools available"
        
        planning_message = f"""{self.planning_prompt}

User Question: {user_question}
Pool Address: {pool_address or "Not provided"}

Available Tools:
{available_tools_desc}

Analyze the question and decide which tools are needed. If the user wants a comprehensive or full analysis, set needs_comprehensive=True.
"""
        
        try:
            plan_result: AnalysisPlan = self.planner_llm.invoke([
                HumanMessage(content=planning_message)
            ])
            
            # If comprehensive analysis requested, use all tools
            if plan_result.needs_comprehensive:
                tools_to_call = [
                    "resolve_pool_tokens",
                    "check_token_security",
                    "search_token_sentiment"
                ]
            else:
                # Filter to only valid tools
                tools_to_call = [
                    t for t in plan_result.tools_to_call 
                    if t in self.tools_by_name
                ]
            
            logger.info(f"Plan: {plan_result.reasoning}")
            logger.info(f"Tools selected: {tools_to_call}")
            
            return {
                "plan": plan_result.reasoning,
                "tools_to_call": tools_to_call,
                "exit_flag": False
            }
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return {
                "plan": f"Planning failed: {str(e)}",
                "tools_to_call": [],
                "exit_flag": True
            }
    
    def _route_after_plan(self, state: OverallState) -> Literal["execute_tools", "no_tools", "error"]:
        """Route based on planning result."""
        if state.get("exit_flag"):
            return "error"
        
        tools_to_call = state.get("tools_to_call", [])
        if not tools_to_call:
            return "no_tools"
        
        return "execute_tools"
    
    async def _execute_tools_node(self, state: OverallState) -> Dict[str, Any]:
        """
        Execute selected tools in parallel using async.
        
        Token Intelligence tool execution requires special handling:
        - resolve_pool_tokens must run first to get token info
        - check_token_security needs chain and token_address from resolved tokens
        - search_token_sentiment needs token_symbol and token_address
        - classify_token_risk needs security_data and sentiment_data
        
        Args:
            state: Current state with tools_to_call
            
        Returns:
            Updated state with tool_results
        """
        tools_to_call = state.get("tools_to_call", [])
        pool_address = state.get("pool_address")
        
        if not pool_address:
            return {
                "tool_results": [{"error": "No pool address provided"}],
                "exit_flag": True
            }
        
        results = []
        resolved_tokens = None
        security_results = []
        sentiment_results = []
        
        # Step 1: Always resolve tokens first if requested or if other tools need it
        needs_resolution = "resolve_pool_tokens" in tools_to_call or any(
            t in tools_to_call for t in ["check_token_security", "search_token_sentiment", "classify_token_risk"]
        )
        
        if needs_resolution:
            resolve_tool = self.tools_by_name.get("resolve_pool_tokens")
            if resolve_tool:
                try:
                    result = await resolve_tool.ainvoke({"pool_address": pool_address})
                    resolved_tokens = json.loads(result) if isinstance(result, str) else result
                    # Ensure resolved_tokens is a dict, not a list
                    if isinstance(resolved_tokens, list):
                        # If it's a list, take the first element
                        resolved_tokens = resolved_tokens[0] if resolved_tokens else {}
                    results.append({"tool": "resolve_pool_tokens", "result": resolved_tokens})
                    logger.info(f"Token resolution completed: {list(resolved_tokens.keys()) if isinstance(resolved_tokens, dict) else 'unknown'}")
                except Exception as e:
                    logger.error(f"Token resolution failed: {e}")
                    results.append({"tool": "resolve_pool_tokens", "error": str(e)})
        
        # Step 2: Run security and sentiment checks in parallel if we have tokens
        if resolved_tokens and isinstance(resolved_tokens, dict) and not resolved_tokens.get("error"):
            # DexScreener returns token0 and token1, not a tokens list
            tokens = []
            if "token0" in resolved_tokens:
                tokens.append(resolved_tokens["token0"])
            if "token1" in resolved_tokens:
                tokens.append(resolved_tokens["token1"])
            # Also support tokens list format if present
            if "tokens" in resolved_tokens:
                tokens = resolved_tokens["tokens"]
            
            # Get chain from resolved tokens
            chain = resolved_tokens.get("chain", "ethereum")
            
            async def check_security_for_token(token: Dict) -> Dict:
                """Check security for a single token."""
                tool = self.tools_by_name.get("check_token_security")
                if not tool:
                    return {"error": "Tool not found"}
                
                symbol = token.get("symbol", "UNKNOWN")
                address = token.get("address", "")
                
                # Skip stablecoins and wrapped tokens
                if symbol.upper() in ["USDC", "USDT", "DAI", "FRAX", "WETH", "WBTC"]:
                    return {"token": symbol, "result": {"skip": True, "reason": "Standard token"}}
                
                try:
                    result = await tool.ainvoke({
                        "chain": chain,  # Use chain from resolved tokens
                        "token_address": address
                    })
                    parsed = json.loads(result) if isinstance(result, str) else result
                    return {"token": symbol, "address": address, "result": parsed}
                except Exception as e:
                    return {"token": symbol, "error": str(e)}
            
            async def search_sentiment_for_token(token: Dict) -> Dict:
                """Search sentiment for a single token."""
                tool = self.tools_by_name.get("search_token_sentiment")
                if not tool:
                    return {"error": "Tool not found"}
                
                symbol = token.get("symbol", "UNKNOWN")
                address = token.get("address", "")
                
                # Skip stablecoins and wrapped tokens
                if symbol.upper() in ["USDC", "USDT", "DAI", "FRAX", "WETH", "WBTC"]:
                    return {"token": symbol, "result": {"skip": True, "reason": "Standard token"}}
                
                try:
                    result = await tool.ainvoke({
                        "token_symbol": symbol,
                        "token_address": address
                    })
                    parsed = json.loads(result) if isinstance(result, str) else result
                    return {"token": symbol, "address": address, "result": parsed}
                except Exception as e:
                    return {"token": symbol, "error": str(e)}
            
            # Execute security and sentiment in parallel
            parallel_tasks = []
            
            if "check_token_security" in tools_to_call:
                for token in tokens:
                    parallel_tasks.append(("security", token, check_security_for_token(token)))
            
            if "search_token_sentiment" in tools_to_call:
                for token in tokens:
                    parallel_tasks.append(("sentiment", token, search_sentiment_for_token(token)))
            
            if parallel_tasks:
                # Group tasks by type
                security_tasks = [t[2] for t in parallel_tasks if t[0] == "security"]
                sentiment_tasks = [t[2] for t in parallel_tasks if t[0] == "sentiment"]
                
                # Run all in parallel
                all_results = await asyncio.gather(*security_tasks, *sentiment_tasks, return_exceptions=True)
                
                # Split results
                security_results = all_results[:len(security_tasks)]
                sentiment_results = all_results[len(security_tasks):]
                
                if security_results:
                    results.append({
                        "tool": "check_token_security",
                        "result": [r if not isinstance(r, Exception) else {"error": str(r)} for r in security_results]
                    })
                
                if sentiment_results:
                    results.append({
                        "tool": "search_token_sentiment", 
                        "result": [r if not isinstance(r, Exception) else {"error": str(r)} for r in sentiment_results]
                    })
        
        # Step 3: Classify tokens if requested (requires security and optionally sentiment data)
        if "classify_token_risk" in tools_to_call and resolved_tokens:
            classify_tool = self.tools_by_name.get("classify_token_risk")
            if classify_tool:
                # Re-extract tokens from resolved_tokens (same logic as Step 2)
                classify_tokens = []
                if "token0" in resolved_tokens:
                    classify_tokens.append(resolved_tokens["token0"])
                if "token1" in resolved_tokens:
                    classify_tokens.append(resolved_tokens["token1"])
                if "tokens" in resolved_tokens:
                    classify_tokens = resolved_tokens["tokens"]
                
                classifications = []
                
                for i, token in enumerate(classify_tokens):
                    symbol = token.get("symbol", "UNKNOWN")
                    address = token.get("address", "")
                    
                    # Get security and sentiment data for this token
                    security_data = {}
                    sentiment_data = {}
                    
                    for sr in security_results:
                        if isinstance(sr, dict) and sr.get("token") == symbol:
                            security_data = sr.get("result", {})
                            break
                    
                    for sr in sentiment_results:
                        if isinstance(sr, dict) and sr.get("token") == symbol:
                            sentiment_data = sr.get("result", {})
                            break
                    
                    try:
                        result = await classify_tool.ainvoke({
                            "token_symbol": symbol,
                            "token_address": address,
                            "security_data": security_data,
                            "sentiment_data": sentiment_data
                        })
                        parsed = json.loads(result) if isinstance(result, str) else result
                        classifications.append({"token": symbol, "classification": parsed})
                    except Exception as e:
                        classifications.append({"token": symbol, "error": str(e)})
                
                results.append({"tool": "classify_token_risk", "result": classifications})
        
        return {
            "tool_results": results,
            "resolved_tokens": resolved_tokens,
            "security_results": security_results,
            "sentiment_results": sentiment_results,
            "exit_flag": False
        }
    
    def _no_tools_response_node(self, state: OverallState) -> Dict[str, Any]:
        """Handle case where no tools were selected."""
        user_question = state["user_question"]
        plan = state.get("plan", "")
        
        response = f"""Based on your question "{user_question}", I determined that no specific token intelligence tools are needed.

My reasoning: {plan}

If you'd like me to analyze tokens in a Uniswap V3 pool, please:
1. Provide a pool address (0x...)
2. Ask about token security, sentiment, or risk classification
3. Or request a comprehensive token analysis

Example: "Analyze token security for pool 0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
"""
        
        return {
            "synthesized_answer": response,
            "exit_flag": False
        }
    
    def _synthesize_node(self, state: OverallState) -> Dict[str, Any]:
        """
        Synthesize tool results into a coherent answer.
        
        Args:
            state: Current state with tool_results
            
        Returns:
            Updated state with synthesized_answer
        """
        user_question = state["user_question"]
        pool_address = state.get("pool_address")
        plan = state.get("plan", "")
        tool_results = state.get("tool_results", [])
        
        # Format results for the LLM
        results_text = ""
        for tr in tool_results:
            tool_name = tr.get("tool", "unknown")
            if "error" in tr:
                results_text += f"\n{tool_name}: ERROR - {tr['error']}"
            else:
                result = tr.get("result", {})
                results_text += f"\n{tool_name}:\n{result}\n"
        
        synthesis_prompt = f"""{self.system_prompt}

User Question: {user_question}
Pool Address: {pool_address}

My Analysis Plan: {plan}

Tool Results:
{results_text}

Based on these analysis results, provide a clear, data-driven answer to the user's question.
Focus on token-level risks: security vulnerabilities, scams, honeypots, suspicious activities.
If there are dangerous tokens, prominently warn the user with specific concerns.
"""
        
        try:
            response = self.llm.invoke([HumanMessage(content=synthesis_prompt)])
            answer = response.content
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            answer = f"Analysis completed but synthesis failed: {e}\n\nRaw results: {results_text}"
        
        return {
            "synthesized_answer": answer,
            "exit_flag": False
        }
    
    def _finalize_node(self, state: OverallState) -> Dict[str, Any]:
        """Prepare final output."""
        tool_results = state.get("tool_results", [])
        plan = state.get("plan", "")
        tools_called = state.get("tools_to_call", [])
        resolved_tokens = state.get("resolved_tokens", {})
        
        # Extract classification risk scores if available
        risk_classifications = {}
        for tr in tool_results:
            if tr.get("tool") == "classify_token_risk" and "result" in tr:
                for classification in tr["result"]:
                    token = classification.get("token")
                    if token and "classification" in classification:
                        risk_classifications[token] = classification["classification"]
        
        metadata = {
            "plan": plan,
            "tools_called": tools_called,
            "tool_count": len(tools_called),
            "mcp_protocol": True,
            "resolved_tokens": resolved_tokens,
            "classifications": risk_classifications
        }
        
        return {
            "answer": state.get("synthesized_answer", "No answer generated"),
            "metadata": metadata
        }
