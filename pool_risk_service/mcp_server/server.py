"""
Fast MCP Server for Pool Risk Tools.
Exposes risk analyzers via HTTP on port 8002 for dynamic tool discovery.
"""

import os
import sys

# Add pool_risk_service and project root to path
_current_dir = os.path.dirname(__file__)
_service_dir = os.path.abspath(os.path.join(_current_dir, '..'))
_project_root = os.path.abspath(os.path.join(_current_dir, '../..'))
sys.path.insert(0, _service_dir)
sys.path.insert(0, _project_root)

from fastmcp import FastMCP
from dotenv import load_dotenv
import logging

from common_ai.common_utils.utils import load_config
from utils import GraphPaginator, CacheManager
from tools.concentration_risk import ConcentrationRiskAnalyzer
from tools.liquidity_depth_risk import LiquidityDepthAnalyzer
from tools.market_risk import MarketRiskAnalyzer
from tools.behavioral_risk import BehavioralRiskAnalyzer
from tools.risk_scorer import RiskScorer

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create MCP server
mcp = FastMCP("Pool Risk Tools")

# Initialize dependencies
config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
config = load_config(config_path)

api_key = os.getenv("THE_GRAPH_API_KEY")
if not api_key:
    logger.warning("THE_GRAPH_API_KEY not set, using fallback endpoint")
    endpoint = config["api"]["fallback_endpoint"]
else:
    endpoint = f"{config['api']['base_url']}/{api_key}/subgraphs/id/{config['api']['subgraph_id']}"

paginator = GraphPaginator(endpoint, config)
cache = CacheManager(config)

logger.info("MCP Server initialized with dependencies")


@mcp.tool()
def analyze_concentration_risk(pool_address: str) -> dict:
    """
    Analyze concentration/whale risk for a Uniswap V3 pool.
    
    Returns Gini coefficient, HHI index, top 10 holder dominance,
    and LP age distribution metrics.
    
    Args:
        pool_address: Ethereum address of the Uniswap V3 pool
        
    Returns:
        Dictionary with risk_score (0-100), risk_flags, and detailed metrics
    """
    logger.info(f"Analyzing concentration risk for pool: {pool_address}")
    analyzer = ConcentrationRiskAnalyzer(paginator, cache, config)
    return analyzer.analyze(pool_address)


@mcp.tool()
def analyze_liquidity_depth(pool_address: str, current_price: float = 1.0) -> dict:
    """
    Analyze liquidity depth and slippage risk for a pool.
    
    Simulates price impact for $100K and $1M swaps, calculates
    active vs inactive liquidity, and TVL volatility.
    
    Args:
        pool_address: Ethereum address of the Uniswap V3 pool
        current_price: Current price of token1 in terms of token0
        
    Returns:
        Dictionary with risk_score, slippage metrics, and liquidity efficiency
    """
    logger.info(f"Analyzing liquidity depth for pool: {pool_address}")
    analyzer = LiquidityDepthAnalyzer(paginator, cache, config)
    return analyzer.analyze(pool_address, current_price)


@mcp.tool()
def analyze_market_risk(pool_address: str) -> dict:
    """
    Analyze market risk and impermanent loss exposure.
    
    Calculates utilization rate (volume/TVL), token price correlation,
    and impermanent loss risk classification.
    
    Args:
        pool_address: Ethereum address of the Uniswap V3 pool
        
    Returns:
        Dictionary with risk_score, utilization rate, IL risk level
    """
    logger.info(f"Analyzing market risk for pool: {pool_address}")
    analyzer = MarketRiskAnalyzer(paginator, cache, config)
    return analyzer.analyze(pool_address)


@mcp.tool()
def analyze_behavioral_risk(pool_address: str) -> dict:
    """
    Analyze wash trading and MEV exposure.
    
    Detects circular trading patterns (wash trading) and calculates
    the percentage of swaps that are sandwich attack victims.
    
    Args:
        pool_address: Ethereum address of the Uniswap V3 pool
        
    Returns:
        Dictionary with risk_score, wash trading index, MEV exposure percentage
    """
    logger.info(f"Analyzing behavioral risk for pool: {pool_address}")
    analyzer = BehavioralRiskAnalyzer(paginator, cache, config)
    return analyzer.analyze(pool_address)


@mcp.tool()
def calculate_composite_risk_score(
    concentration_result: dict,
    liquidity_result: dict,
    market_result: dict,
    behavioral_result: dict
) -> dict:
    """
    Calculate composite risk score from individual analysis results.
    
    Combines all risk dimensions using configured weights to produce
    an overall risk score and classification (LOW/MEDIUM/HIGH/CRITICAL).
    
    Args:
        concentration_result: Output from analyze_concentration_risk
        liquidity_result: Output from analyze_liquidity_depth
        market_result: Output from analyze_market_risk
        behavioral_result: Output from analyze_behavioral_risk
        
    Returns:
        Dictionary with composite_score (0-100) and risk_level classification
    """
    logger.info("Calculating composite risk score")
    scorer = RiskScorer(config)
    return scorer.score(
        concentration_result,
        liquidity_result,
        market_result,
        behavioral_result
    )


if __name__ == "__main__":
    port = int(os.getenv("POOL_RISK_MCP_PORT", "8002"))
    logger.info(f"Starting Pool Risk MCP Server on port {port}")
    
    # Run with HTTP transport
    mcp.run(transport="http", port=port, host="0.0.0.0")
