"""
Node implementations for Pool Risk RAG workflow.
Each node performs a specific step in the analysis pipeline.
"""

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import logging

logger = logging.getLogger(__name__)


class PoolRiskNodes:
    """Node implementations for pool risk analysis graph."""
    
    def __init__(
        self,
        llm: ChatOpenAI,
        paginator: Any,
        cache: Any,
        config: Dict[str, Any],
        system_prompt: str
    ):
        """
        Initialize nodes with dependencies.
        
        Args:
            llm: Language model for analysis
            paginator: GraphPaginator instance for The Graph queries
            cache: CacheManager instance
            config: Configuration dictionary
            system_prompt: System prompt for the agent
        """
        self.llm = llm
        self.paginator = paginator
        self.cache = cache
        self.config = config
        self.system_prompt = system_prompt
    
    def enhance_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance user query with pool address context.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with enhanced_query
        """
        user_question = state["user_question"]
        pool_address = state.get("pool_address")
        
        if pool_address:
            enhanced = f"Pool address: {pool_address}\n\nUser query: {user_question}"
        else:
            enhanced = user_question
        
        return {
            "enhanced_query": enhanced,
            "exit_flag": False
        }
    
    def extract_entities(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract entities and analysis type from query.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with extracted_entities
        """
        enhanced_query = state["enhanced_query"]
        pool_address = state.get("pool_address")
        
        # Use LLM to determine what analysis is needed
        extraction_prompt = f"""Based on this user question, identify which risk analyses are needed:

Question: {enhanced_query}

Available analyses:
- concentration: Whale analysis, Gini coefficient, HHI
- liquidity_depth: Slippage simulation, active liquidity
- market_risk: Utilization rate, impermanent loss
- behavioral: Wash trading, MEV exposure
- comprehensive: Full report with all metrics

Respond with a JSON object containing:
- analyses_needed: list of analysis types
- pool_address: extracted pool address (if mentioned)
"""
        
        try:
            response = self.llm.invoke([SystemMessage(content="You are a DeFi analysis assistant."), 
                                       HumanMessage(content=extraction_prompt)])
            
            # For simplicity, we'll default to comprehensive analysis
            # In production, parse LLM response properly
            entities = {
                "analyses_needed": ["comprehensive"],
                "pool_address": pool_address
            }
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            entities = {
                "analyses_needed": ["comprehensive"],
                "pool_address": pool_address
            }
        
        return {
            "extracted_entities": entities,
            "exit_flag": False
        }
    
    def run_analyses(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run requested analyses using tools.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with tool_results
        """
        from tools.concentration_risk import ConcentrationRiskAnalyzer
        from tools.liquidity_depth_risk import LiquidityDepthAnalyzer
        from tools.market_risk import MarketRiskAnalyzer
        from tools.behavioral_risk import BehavioralRiskAnalyzer
        from tools.risk_scorer import RiskScorer
        
        entities = state.get("extracted_entities", {})
        pool_address = entities.get("pool_address") or state.get("pool_address")
        
        if not pool_address:
            return {
                "tool_results": [{"error": "No pool address provided"}],
                "exit_flag": True
            }
        
        results = []
        
        try:
            # Run comprehensive analysis
            concentration_analyzer = ConcentrationRiskAnalyzer(self.paginator, self.cache, self.config)
            liquidity_analyzer = LiquidityDepthAnalyzer(self.paginator, self.cache, self.config)
            market_analyzer = MarketRiskAnalyzer(self.paginator, self.cache, self.config)
            behavioral_analyzer = BehavioralRiskAnalyzer(self.paginator, self.cache, self.config)
            
            # Fetch pool info first to get current price
            pool_info = self._fetch_pool_info(pool_address)
            current_price = float(pool_info.get("token1Price", 1))
            
            # Run analyses
            concentration_result = concentration_analyzer.analyze(pool_address)
            liquidity_result = liquidity_analyzer.analyze(pool_address, current_price)
            market_result = market_analyzer.analyze(pool_address)
            behavioral_result = behavioral_analyzer.analyze(pool_address)
            
            # Calculate composite score
            scorer = RiskScorer(self.config)
            risk_score = scorer.score(
                concentration_result,
                liquidity_result,
                market_result,
                behavioral_result
            )
            
            results.append({
                "type": "comprehensive_analysis",
                "pool_info": pool_info,
                "concentration": concentration_result,
                "liquidity_depth": liquidity_result,
                "market_risk": market_result,
                "behavioral": behavioral_result,
                "composite_score": risk_score
            })
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            results.append({"error": str(e)})
            return {
                "tool_results": results,
                "exit_flag": True
            }
        
        return {
            "tool_results": results,
            "exit_flag": False
        }
    
    def synthesize_answer(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize final answer from analysis results.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with synthesized_answer
        """
        user_question = state["user_question"]
        tool_results = state.get("tool_results", [])
        
        if not tool_results or "error" in tool_results[0]:
            error_msg = tool_results[0].get("error", "Unknown error") if tool_results else "No results"
            return {
                "synthesized_answer": f"Analysis failed: {error_msg}",
                "exit_flag": True
            }
        
        # Build context from results
        result = tool_results[0]
        
        context = f"""
Pool Analysis Results:

Pool Information:
- Tokens: {result['pool_info'].get('token0', {}).get('symbol', 'Unknown')} / {result['pool_info'].get('token1', {}).get('symbol', 'Unknown')}
- TVL: ${result['pool_info'].get('totalValueLockedUSD', 'N/A')}
- Fee Tier: {result['pool_info'].get('feeTier', 'N/A')}

Risk Scores:
- Concentration Risk: {result['concentration'].get('risk_score', 'N/A')}/100
- Liquidity Depth Risk: {result['liquidity_depth'].get('risk_score', 'N/A')}/100
- Market Risk: {result['market_risk'].get('risk_score', 'N/A')}/100
- Behavioral Risk: {result['behavioral'].get('risk_score', 'N/A')}/100
- Composite Risk: {result['composite_score'].get('composite_score', 'N/A')}/100 - {result['composite_score'].get('risk_level', 'Unknown')}

Key Findings:
{self._format_findings(result)}
"""
        
        # Generate answer using LLM
        synthesis_prompt = f"""{self.system_prompt}

Based on the following analysis results, answer the user's question:

{context}

User Question: {user_question}

Provide a clear, data-driven answer with specific numbers and risk levels.
"""
        
        try:
            response = self.llm.invoke([HumanMessage(content=synthesis_prompt)])
            answer = response.content
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            answer = f"Failed to generate answer: {e}"
        
        return {
            "synthesized_answer": answer,
            "exit_flag": False
        }
    
    def finalize_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare final output.
        
        Args:
            state: Current state
            
        Returns:
            Final output state
        """
        tool_results = state.get("tool_results", [])
        
        metadata = {}
        if tool_results and "composite_score" in tool_results[0]:
            metadata["risk_score"] = tool_results[0]["composite_score"].get("composite_score")
            metadata["risk_level"] = tool_results[0]["composite_score"].get("risk_level")
        
        return {
            "answer": state["synthesized_answer"],
            "metadata": metadata
        }
    
    def _fetch_pool_info(self, pool_address: str) -> Dict[str, Any]:
        """Fetch basic pool information."""
        query = """
        query ($pool_id: String!) {
          pool(id: $pool_id) {
            id
            token0 { symbol id decimals }
            token1 { symbol id decimals }
            feeTier
            liquidity
            totalValueLockedUSD
            volumeUSD
            token0Price
            token1Price
            txCount
          }
        }
        """
        try:
            response = self.paginator._execute_with_retry(query, {"pool_id": pool_address.lower()})
            pool = response.get("data", {}).get("pool")
            if not pool:
                return {"error": "Pool not found"}
            return pool
        except Exception as e:
            return {"error": str(e)}
    
    def _format_findings(self, result: Dict[str, Any]) -> str:
        """Format key findings from analysis results."""
        findings = []
        
        # Concentration findings
        conc_flags = result.get('concentration', {}).get('risk_flags', [])
        if conc_flags:
            findings.append(f"Concentration: {', '.join(conc_flags)}")
        
        # Liquidity findings  
        liq_flags = result.get('liquidity_depth', {}).get('risk_flags', [])
        if liq_flags:
            findings.append(f"Liquidity: {', '.join(liq_flags)}")
        
        # Market findings
        market_flags = result.get('market_risk', {}).get('risk_flags', [])
        if market_flags:
            findings.append(f"Market: {', '.join(market_flags)}")
        
        # Behavioral findings
        behav_flags = result.get('behavioral', {}).get('risk_flags', [])
        if behav_flags:
            findings.append(f"Behavioral: {', '.join(behav_flags)}")
        
        return "\n".join(findings) if findings else "No critical risk flags detected"
