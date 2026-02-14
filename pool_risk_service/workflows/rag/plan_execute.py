"""
Plan-Execute StateGraph - Dynamic tool selection with MCP protocol.

This workflow allows the agent to:
1. Plan which tools to call based on the user's question
2. Execute selected tools in parallel via MCP
3. Synthesize results into a final answer
"""

import operator
from typing import Dict, Any, List, Annotated, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.types import Send
import logging

from .state import InputState, OutputState, OverallState, AnalysisPlan

logger = logging.getLogger(__name__)


# Worker state for parallel tool execution
class ToolWorkerState(Dict):
    """State for individual tool worker."""
    tool_name: str
    pool_address: str
    result: Dict[str, Any]


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
        "analyze_concentration_risk",
        "analyze_liquidity_depth", 
        "analyze_market_risk",
        "analyze_behavioral_risk",
        "calculate_composite_risk_score"
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
            f"- {tool.name}: {tool.description[:100]}..." 
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
                    "analyze_concentration_risk",
                    "analyze_liquidity_depth",
                    "analyze_market_risk", 
                    "analyze_behavioral_risk"
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
        
        Args:
            state: Current state with tools_to_call
            
        Returns:
            Updated state with tool_results
        """
        import asyncio
        
        tools_to_call = state.get("tools_to_call", [])
        pool_address = state.get("pool_address")
        
        if not pool_address:
            return {
                "tool_results": [{"error": "No pool address provided"}],
                "exit_flag": True
            }
        
        async def execute_single_tool(tool_name: str) -> Dict[str, Any]:
            """Execute a single tool asynchronously."""
            tool = self.tools_by_name.get(tool_name)
            if not tool:
                return {"tool": tool_name, "error": f"Tool {tool_name} not found"}
            
            try:
                # Most tools just need pool_address
                if tool_name == "analyze_liquidity_depth":
                    result = await tool.ainvoke({"pool_address": pool_address, "current_price": 1.0})
                elif tool_name == "calculate_composite_risk_score":
                    # Skip - will be calculated after other tools
                    return {"tool": tool_name, "skip": True}
                else:
                    result = await tool.ainvoke({"pool_address": pool_address})
                
                logger.info(f"Tool {tool_name} executed successfully")
                return {"tool": tool_name, "result": result}
                
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                return {"tool": tool_name, "error": str(e)}
        
        # Execute tools in parallel
        tasks = [execute_single_tool(name) for name in tools_to_call if name != "calculate_composite_risk_score"]
        results = await asyncio.gather(*tasks)
        
        # Filter out skipped results
        results = [r for r in results if not r.get("skip")]
        
        # If composite score was requested and we have enough results
        if "calculate_composite_risk_score" in tools_to_call:
            risk_results = {r["tool"]: r.get("result", {}) for r in results if "result" in r}
            if len(risk_results) >= 4:
                try:
                    composite_tool = self.tools_by_name.get("calculate_composite_risk_score")
                    if composite_tool:
                        composite_result = await composite_tool.ainvoke({
                            "concentration_result": risk_results.get("analyze_concentration_risk", {}),
                            "liquidity_result": risk_results.get("analyze_liquidity_depth", {}),
                            "market_result": risk_results.get("analyze_market_risk", {}),
                            "behavioral_result": risk_results.get("analyze_behavioral_risk", {})
                        })
                        results.append({"tool": "calculate_composite_risk_score", "result": composite_result})
                except Exception as e:
                    logger.error(f"Composite score calculation failed: {e}")
        
        return {
            "tool_results": results,
            "exit_flag": False
        }
    
    def _no_tools_response_node(self, state: OverallState) -> Dict[str, Any]:
        """Handle case where no tools were selected."""
        user_question = state["user_question"]
        plan = state.get("plan", "")
        
        response = f"""Based on your question "{user_question}", I determined that no specific risk analysis tools are needed.

My reasoning: {plan}

If you'd like me to analyze a Uniswap V3 pool, please:
1. Provide a pool address (0x...)
2. Ask about specific risks like concentration, liquidity depth, market risk, or behavioral patterns
3. Or request a comprehensive risk analysis

Example: "Analyze the concentration risk for pool 0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
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
                if isinstance(result, dict):
                    risk_score = result.get("risk_score", "N/A")
                    risk_flags = result.get("risk_flags", [])
                    results_text += f"\n{tool_name}:\n  - Risk Score: {risk_score}/100\n  - Flags: {', '.join(risk_flags) if risk_flags else 'None'}\n  - Details: {result}"
                else:
                    results_text += f"\n{tool_name}: {result}"
        
        synthesis_prompt = f"""{self.system_prompt}

User Question: {user_question}
Pool Address: {pool_address}

My Analysis Plan: {plan}

Tool Results:
{results_text}

Based on these analysis results, provide a clear, data-driven answer to the user's question.
Include specific numbers, risk levels, and actionable insights.
If there are critical risks, highlight them prominently.
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
        
        # Extract composite score if available
        risk_score = None
        risk_level = None
        for tr in tool_results:
            if tr.get("tool") == "calculate_composite_risk_score" and "result" in tr:
                risk_score = tr["result"].get("composite_score")
                risk_level = tr["result"].get("risk_level")
                break
        
        metadata = {
            "plan": plan,
            "tools_called": tools_called,
            "tool_count": len(tools_called),
            "mcp_protocol": True
        }
        
        if risk_score is not None:
            metadata["risk_score"] = risk_score
            metadata["risk_level"] = risk_level
        
        return {
            "answer": state.get("synthesized_answer", "No answer generated"),
            "metadata": metadata
        }
