"""
LangChain tool implementations for the Graph Analysis Agent.

"""

import json
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool


# ============================================================================
# Input Schemas (Pydantic models for tool arguments)
# ============================================================================

class PoolAddressInput(BaseModel):
    """Input schema for tools that need a pool address."""
    pool_address: str = Field(
        ...,
        description="The Ethereum address of the Uniswap V3 pool (0x...)"
    )


class PoolAnalysisInput(BaseModel):
    """Input schema for analysis tools."""
    pool_address: str = Field(
        ...,
        description="The Ethereum address of the Uniswap V3 pool (0x...)"
    )
    current_price: Optional[float] = Field(
        default=None,
        description="Current price (token1/token0). If not provided, will be fetched."
    )


class ReportInput(BaseModel):
    """Input schema for report generation."""
    pool_address: str = Field(..., description="Pool address")
    include_raw_data: bool = Field(default=False, description="Include raw JSON data in output")


# ============================================================================
# Tool Implementations
# ============================================================================

class FetchPoolInfoTool(BaseTool):
    """Tool to fetch basic pool information from The Graph."""
    
    name: str = "fetch_pool_info"
    description: str = """Fetches basic information about a Uniswap V3 pool including:
    - Token pair (symbols and addresses)
    - Fee tier
    - Total Value Locked (TVL) in USD
    - Trading volume
    - Current prices
    Use this first to understand what pool you're analyzing."""
    args_schema: Type[BaseModel] = PoolAddressInput
    
    # Injected dependencies
    paginator: Any = Field(default=None, repr=False)
    
    def _run(self, pool_address: str) -> str:
        """Fetch pool info and return as JSON string."""
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
            variables = {"pool_id": pool_address.lower()}
            response = self.paginator._execute_with_retry(query, variables)
            pool = response.get("data", {}).get("pool")
            
            if not pool:
                return json.dumps({
                    "error": "Pool not found in Uniswap V3 subgraph",
                    "pool_address": pool_address,
                    "suggestion": "Verify this is a valid Uniswap V3 pool address on Ethereum mainnet. Check on https://info.uniswap.org/#/pools",
                    "note": "The pool must exist on Ethereum mainnet and be indexed by The Graph"
                })
            
            # Format for readability
            result = {
                "pool_address": pool["id"],
                "token0": pool["token0"]["symbol"],
                "token1": pool["token1"]["symbol"],
                "fee_tier": int(pool["feeTier"]) / 10000,  # Convert to percentage
                "tvl_usd": float(pool["totalValueLockedUSD"]),
                "volume_usd": float(pool["volumeUSD"]),
                "token0_price": float(pool["token0Price"]),
                "token1_price": float(pool["token1Price"]),
                "tx_count": int(pool["txCount"]),
            }
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({
                "error": f"Failed to fetch pool data: {str(e)}",
                "pool_address": pool_address,
                "suggestion": "Check your internet connection and The Graph API key"
            })


class AnalyzeConcentrationTool(BaseTool):
    """Tool to analyze concentration/whale risk."""
    
    name: str = "analyze_concentration_risk"
    description: str = """Analyzes concentration risk (whale analysis) for a pool:
    - Gini coefficient (inequality measure, 0-1)
    - HHI (Herfindahl-Hirschman Index, market concentration)
    - Top 10 holder dominance percentage
    - LP age distribution (mercenary vs long-term liquidity)
    Returns risk flags if concentration is dangerously high."""
    args_schema: Type[BaseModel] = PoolAddressInput
    
    # Injected dependencies
    paginator: Any = Field(default=None, repr=False)
    cache: Any = Field(default=None, repr=False)
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, pool_address: str) -> str:
        """Run concentration analysis and return JSON."""
        from tools.concentration_risk import ConcentrationRiskAnalyzer
        
        analyzer = ConcentrationRiskAnalyzer(self.paginator, self.cache, self.config)
        result = analyzer.analyze(pool_address)
        return json.dumps(result, indent=2)


class AnalyzeLiquidityDepthTool(BaseTool):
    """Tool to analyze liquidity depth and slippage risk."""
    
    name: str = "analyze_liquidity_depth"
    description: str = """Analyzes liquidity depth and slippage risk:
    - Simulates $100K and $1M sell orders to calculate price impact
    - Measures active (in-range) vs inactive liquidity percentage
    - Calculates TVL volatility over 30 days
    High slippage indicates poor liquidity depth."""
    args_schema: Type[BaseModel] = PoolAnalysisInput
    
    # Injected dependencies
    paginator: Any = Field(default=None, repr=False)
    cache: Any = Field(default=None, repr=False)
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, pool_address: str, current_price: Optional[float] = None) -> str:
        """Run liquidity analysis and return JSON."""
        from tools.liquidity_depth_risk import LiquidityDepthAnalyzer
        
        # If no price provided, fetch it
        if current_price is None:
            current_price = self._fetch_price(pool_address)
        
        analyzer = LiquidityDepthAnalyzer(self.paginator, self.cache, self.config)
        result = analyzer.analyze(pool_address, current_price)
        return json.dumps(result, indent=2)
    
    def _fetch_price(self, pool_address: str) -> float:
        """Fetch current price from pool."""
        query = """
        query ($pool_id: String!) {
          pool(id: $pool_id) { token1Price }
        }
        """
        try:
            response = self.paginator._execute_with_retry(query, {"pool_id": pool_address.lower()})
            return float(response.get("data", {}).get("pool", {}).get("token1Price", 1))
        except:
            return 1.0


class AnalyzeMarketRiskTool(BaseTool):
    """Tool to analyze market risk and impermanent loss."""
    
    name: str = "analyze_market_risk"
    description: str = """Analyzes market efficiency and impermanent loss risk:
    - Utilization rate (daily volume / TVL)
    - Token price correlation (low correlation = high IL risk)
    - IL risk level classification
    Low utilization means LPs earn few fees and may exit."""
    args_schema: Type[BaseModel] = PoolAddressInput
    
    # Injected dependencies
    paginator: Any = Field(default=None, repr=False)
    cache: Any = Field(default=None, repr=False)
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, pool_address: str) -> str:
        """Run market risk analysis and return JSON."""
        from tools.market_risk import MarketRiskAnalyzer
        
        analyzer = MarketRiskAnalyzer(self.paginator, self.cache, self.config)
        result = analyzer.analyze(pool_address)
        return json.dumps(result, indent=2)


class AnalyzeBehavioralRiskTool(BaseTool):
    """Tool to analyze wash trading and MEV exposure."""
    
    name: str = "analyze_behavioral_risk"
    description: str = """Detects inorganic trading activity and MEV exploitation:
    - Wash trading index (circular trading patterns)
    - MEV exposure (sandwich attack victims percentage)
    - Suspicious transaction patterns
    High values indicate the pool is dominated by bots."""
    args_schema: Type[BaseModel] = PoolAddressInput
    
    # Injected dependencies
    paginator: Any = Field(default=None, repr=False)
    cache: Any = Field(default=None, repr=False)
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, pool_address: str) -> str:
        """Run behavioral analysis and return JSON."""
        from tools.behavioral_risk import BehavioralRiskAnalyzer
        
        analyzer = BehavioralRiskAnalyzer(self.paginator, self.cache, self.config)
        result = analyzer.analyze(pool_address)
        return json.dumps(result, indent=2)


class CalculateRiskScoreTool(BaseTool):
    """Tool to calculate composite risk score."""
    
    name: str = "calculate_risk_score"
    description: str = """Aggregates all risk analyses into a composite score.
    NOTE: This tool runs ALL analyses automatically - do NOT run individual analyses first.
    Just provide the pool address and it will:
    1. Run concentration analysis
    2. Run liquidity depth analysis  
    3. Run market risk analysis
    4. Run behavioral risk analysis
    5. Calculate composite score
    Returns risk level: LOW (0-25), MEDIUM (26-50), HIGH (51-75), CRITICAL (76-100)."""
    args_schema: Type[BaseModel] = PoolAddressInput
    
    # Injected dependencies
    paginator: Any = Field(default=None, repr=False)
    cache: Any = Field(default=None, repr=False)
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, pool_address: str) -> str:
        """Run all analyses and calculate composite score."""
        from tools.concentration_risk import ConcentrationRiskAnalyzer
        from tools.liquidity_depth_risk import LiquidityDepthAnalyzer
        from tools.market_risk import MarketRiskAnalyzer
        from tools.behavioral_risk import BehavioralRiskAnalyzer
        from tools.risk_scorer import RiskScorer
        
        # Fetch current price first
        current_price = self._fetch_price(pool_address)
        
        # Run all analyses
        concentration_analyzer = ConcentrationRiskAnalyzer(self.paginator, self.cache, self.config)
        liquidity_analyzer = LiquidityDepthAnalyzer(self.paginator, self.cache, self.config)
        market_analyzer = MarketRiskAnalyzer(self.paginator, self.cache, self.config)
        behavioral_analyzer = BehavioralRiskAnalyzer(self.paginator, self.cache, self.config)
        
        concentration_result = concentration_analyzer.analyze(pool_address)
        liquidity_result = liquidity_analyzer.analyze(pool_address, current_price)
        market_result = market_analyzer.analyze(pool_address)
        behavioral_result = behavioral_analyzer.analyze(pool_address)
        
        # Calculate score
        scorer = RiskScorer(self.config)
        result = scorer.score(
            concentration_result,
            liquidity_result,
            market_result,
            behavioral_result
        )
        return json.dumps(result, indent=2)
    
    def _fetch_price(self, pool_address: str) -> float:
        """Fetch current price from pool."""
        query = """
        query ($pool_id: String!) {
          pool(id: $pool_id) { token1Price }
        }
        """
        try:
            response = self.paginator._execute_with_retry(query, {"pool_id": pool_address.lower()})
            return float(response.get("data", {}).get("pool", {}).get("token1Price", 1))
        except:
            return 1.0


class GenerateReportTool(BaseTool):
    """Tool to generate comprehensive markdown report."""
    
    name: str = "generate_report"
    description: str = """Generates a comprehensive human-readable markdown report.
    NOTE: This tool runs ALL analyses automatically - do NOT run other analyses first.
    Just provide the pool address and it will:
    1. Fetch pool information
    2. Run all risk analyses
    3. Calculate composite score
    4. Generate detailed markdown report with:
       - Executive summary
       - Risk level and scores
       - Detailed findings per category
       - Actionable recommendations"""
    args_schema: Type[BaseModel] = ReportInput
    
    # Injected dependencies
    paginator: Any = Field(default=None, repr=False)
    cache: Any = Field(default=None, repr=False)
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, pool_address: str, include_raw_data: bool = False) -> str:
        """Generate markdown report by running full analysis."""
        from tools.concentration_risk import ConcentrationRiskAnalyzer
        from tools.liquidity_depth_risk import LiquidityDepthAnalyzer
        from tools.market_risk import MarketRiskAnalyzer
        from tools.behavioral_risk import BehavioralRiskAnalyzer
        from tools.risk_scorer import RiskScorer
        from tools.report_generator import ReportGenerator
        
        # Fetch pool info
        pool_info = self._fetch_pool_info(pool_address)
        if "error" in pool_info:
            return json.dumps({"error": pool_info["error"]})
        
        current_price = float(pool_info.get("token1Price", 1))
        
        # Run all analyses
        concentration_analyzer = ConcentrationRiskAnalyzer(self.paginator, self.cache, self.config)
        liquidity_analyzer = LiquidityDepthAnalyzer(self.paginator, self.cache, self.config)
        market_analyzer = MarketRiskAnalyzer(self.paginator, self.cache, self.config)
        behavioral_analyzer = BehavioralRiskAnalyzer(self.paginator, self.cache, self.config)
        
        concentration_result = concentration_analyzer.analyze(pool_address)
        liquidity_result = liquidity_analyzer.analyze(pool_address, current_price)
        market_result = market_analyzer.analyze(pool_address)
        behavioral_result = behavioral_analyzer.analyze(pool_address)
        
        # Calculate score
        scorer = RiskScorer(self.config)
        risk_score = scorer.score(
            concentration_result,
            liquidity_result,
            market_result,
            behavioral_result
        )
        
        # Generate report
        generator = ReportGenerator(self.config)
        report = generator.generate(pool_address, pool_info, risk_score)
        
        if include_raw_data:
            return json.dumps({
                "report": report,
                "raw_data": risk_score
            }, indent=2)
        
        return report
    
    def _fetch_pool_info(self, pool_address: str) -> Dict[str, Any]:
        """Fetch pool info for report."""
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


# ============================================================================
# Tool Builder
# ============================================================================

def build_tools(config: Dict[str, Any], paginator: Any, cache: Any) -> List[BaseTool]:
    """
    Build all tools with injected dependencies.
    
    Args:
        config: Application configuration
        paginator: GraphPaginator instance
        cache: CacheManager instance
        
    Returns:
        List of configured tools
    """
    tools = [
        FetchPoolInfoTool(paginator=paginator),
        AnalyzeConcentrationTool(paginator=paginator, cache=cache, config=config),
        AnalyzeLiquidityDepthTool(paginator=paginator, cache=cache, config=config),
        AnalyzeMarketRiskTool(paginator=paginator, cache=cache, config=config),
        AnalyzeBehavioralRiskTool(paginator=paginator, cache=cache, config=config),
        CalculateRiskScoreTool(paginator=paginator, cache=cache, config=config),
        GenerateReportTool(paginator=paginator, cache=cache, config=config),
    ]
    
    return tools
