"""
Token Intelligence MCP Server - exposes tools via Fast MCP HTTP.
"""

import sys
import json
from pathlib import Path

# Setup path - add parent directory for tools and common_ai
sys.path.insert(0, str(Path(__file__).parent.parent))  # token_intel_service
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common_ai"))

from fastmcp import FastMCP
from common_ai.common_utils.utils import load_config
from tools.token_resolver import TokenResolver
from tools.token_security import TokenSecurityAnalyzer
from tools.token_sentiment import TokenSentimentAnalyzer
from tools.token_classifier import TokenClassifier
import logging

logger = logging.getLogger(__name__)

# Initialize MCP
mcp = FastMCP("Token Intelligence Tools")

# Load configuration
config_path = str(Path(__file__).parent.parent / "config.json")
config = load_config(config_path)


@mcp.tool()
def resolve_pool_tokens(pool_address: str) -> str:
    """
    Resolve pool/pair address to token information.
    
    Args:
        pool_address: Pool or pair contract address
        
    Returns:
        JSON string with token details (symbol, address, liquidity, etc.)
    """
    try:
        resolver = TokenResolver(config)
        result = resolver.resolve_pool(pool_address)  # Method is resolve_pool, not resolve_pool_tokens
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def check_token_security(chain: str, token_address: str) -> str:
    """
    Check token contract security using GoPlus API.
    
    Args:
        chain: Blockchain name (ethereum, bsc, polygon, etc.)
        token_address: Token contract address
        
    Returns:
        JSON string with security analysis (honeypot, scam flags, ownership, etc.)
    """
    try:
        analyzer = TokenSecurityAnalyzer(config)
        result = analyzer.analyze(chain, token_address)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_token_sentiment(token_symbol: str, token_address: str) -> str:
    """
    Search for token sentiment and scam reports using web search.
    
    Args:
        token_symbol: Token ticker symbol
        token_address: Token contract address
        
    Returns:
        JSON string with sentiment analysis and news
    """
    try:
        analyzer = TokenSentimentAnalyzer(config)
        result = analyzer.analyze(token_symbol, token_address)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def classify_token_risk(
    token_symbol: str,
    token_address: str,
    security_data: dict,
    sentiment_data: dict = None
) -> str:
    """
    Classify token risk level as SAFE/RISKY/DANGER.
    
    Args:
        token_symbol: Token ticker symbol
        token_address: Token contract address
        security_data: Security analysis results from check_token_security
        sentiment_data: Optional sentiment analysis from search_token_sentiment
        
    Returns:
        JSON string with risk classification, score, and flags
    """
    try:
        classifier = TokenClassifier(config)
        token_info = {"symbol": token_symbol, "address": token_address}
        result = classifier.classify(token_info, security_data, sentiment_data or {})
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    # Run HTTP MCP server on port 8004 (service runs on 8003)
    mcp.run(transport="http", port=8004)
