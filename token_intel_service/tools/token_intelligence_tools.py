"""
Token Intelligence LangChain Tools - Tool wrappers for the Token Intelligence Agent.
"""

import json
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool


# ============================================================================
# Input Schemas
# ============================================================================

class PoolAddressInput(BaseModel):
    """Input for resolving pool to tokens."""
    pool_address: str = Field(..., description="The pool/pair contract address to resolve")


class TokenAddressInput(BaseModel):
    """Input for token-specific analysis."""
    chain: str = Field(..., description="Blockchain name (ethereum, bsc, polygon, arbitrum, etc.)")
    token_address: str = Field(..., description="Token contract address")


class TokenSearchInput(BaseModel):
    """Input for sentiment search."""
    token_name: str = Field(..., description="Full name of the token")
    token_symbol: str = Field(..., description="Token symbol (e.g., ETH, USDC)")
    token_address: str = Field(default="", description="Optional contract address")


class FullIntelligenceInput(BaseModel):
    """Input for full token intelligence analysis."""
    pool_address: str = Field(..., description="Pool/pair address to analyze both tokens")


# ============================================================================
# Tool Implementations
# ============================================================================

class ResolvePoolTokensTool(BaseTool):
    """Tool to resolve a pool address to its constituent tokens using DexScreener."""
    
    name: str = "resolve_pool_tokens"
    description: str = """Resolves a liquidity pool address to identify the tokens in the pair.
    Returns:
    - Chain (ethereum, bsc, polygon, etc.)
    - Token0 and Token1 addresses, symbols, names
    - Current price, liquidity, 24h volume
    - Price change and transaction counts
    Use this first to identify what tokens are in a pool before analyzing them."""
    args_schema: Type[BaseModel] = PoolAddressInput
    
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, pool_address: str) -> str:
        from tools.token_resolver import TokenResolver
        
        resolver = TokenResolver(self.config)
        result = resolver.resolve_pool(pool_address)
        
        if "error" not in result:
            # Add market risk flags
            flags = resolver.get_market_risk_flags(result)
            result["market_flags"] = flags
        
        return json.dumps(result, indent=2)


class CheckTokenSecurityTool(BaseTool):
    """Tool to check token smart contract security using GoPlus."""
    
    name: str = "check_token_security"
    description: str = """Performs comprehensive security analysis on a token smart contract.
    Checks for:
    - Honeypot (can you sell?)
    - Proxy contract (upgradeable = risky)
    - Mintable supply (inflation risk)
    - Owner privileges (can modify balances, pause transfers)
    - Hidden owner, self-destruct functions
    - Buy/sell tax rates
    - Holder count and concentration
    Returns risk_score (0-100) and security flags."""
    args_schema: Type[BaseModel] = TokenAddressInput
    
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, chain: str, token_address: str) -> str:
        from tools.token_security import TokenSecurityAnalyzer
        
        analyzer = TokenSecurityAnalyzer(self.config)
        result = analyzer.analyze(chain, token_address)
        return json.dumps(result, indent=2)


class SearchTokenSentimentTool(BaseTool):
    """Tool to search for token reputation and sentiment online using Tavily."""
    
    name: str = "search_token_sentiment"
    description: str = """Searches the web for information about a token/project.
    Analyzes:
    - Scam reports and warnings
    - Community sentiment (Reddit, Twitter)
    - Official listings (CoinGecko, CoinMarketCap)
    - News articles and reviews
    - Team and project legitimacy
    Returns sentiment_score and flags indicating positive/negative signals found."""
    args_schema: Type[BaseModel] = TokenSearchInput
    
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, token_name: str, token_symbol: str, token_address: str = "") -> str:
        from tools.token_sentiment import TokenSentimentAnalyzer
        
        analyzer = TokenSentimentAnalyzer(self.config)
        result = analyzer.search(token_name, token_symbol, token_address)
        return json.dumps(result, indent=2)


class ClassifyTokenRiskTool(BaseTool):
    """Tool to classify token as SAFE, RISKY, or DANGER."""
    
    name: str = "classify_token_risk"
    description: str = """Aggregates security, market, and sentiment data to produce final classification.
    NOTE: This tool runs ALL analyses automatically for BOTH tokens in a pool.
    Just provide the pool address and it will:
    1. Resolve pool to identify tokens
    2. Check security for each token (GoPlus)
    3. Analyze market data (DexScreener)
    4. Search sentiment (Tavily)
    5. Classify each token as SAFE / RISKY / DANGER
    Returns comprehensive intelligence report with recommendations."""
    args_schema: Type[BaseModel] = FullIntelligenceInput
    
    config: Dict[str, Any] = Field(default_factory=dict, repr=False)
    
    def _run(self, pool_address: str) -> str:
        from tools.token_resolver import TokenResolver
        from tools.token_security import TokenSecurityAnalyzer
        from tools.token_sentiment import TokenSentimentAnalyzer
        from tools.token_classifier import TokenClassifier
        
        # Initialize analyzers
        resolver = TokenResolver(self.config)
        security_analyzer = TokenSecurityAnalyzer(self.config)
        classifier = TokenClassifier(self.config)
        
        # Try to initialize sentiment analyzer (may fail if no TAVILY_API_KEY)
        try:
            sentiment_analyzer = TokenSentimentAnalyzer(self.config)
            has_sentiment = True
        except ValueError:
            sentiment_analyzer = None
            has_sentiment = False
        
        # Step 1: Resolve pool
        pool_data = resolver.resolve_pool(pool_address)
        if "error" in pool_data:
            return json.dumps({"error": f"Failed to resolve pool: {pool_data['error']}"})
        
        chain = pool_data["chain"]
        market_flags = resolver.get_market_risk_flags(pool_data)
        pool_data["market_flags"] = market_flags
        
        results = {
            "pool": {
                "address": pool_address,
                "chain": chain,
                "dex": pool_data.get("dex", "unknown"),
                "liquidity_usd": pool_data.get("liquidity_usd", 0),
                "volume_24h": pool_data.get("volume_24h", 0)
            },
            "tokens": []
        }
        
        # Step 2-5: Analyze each token
        for token_key in ["token0", "token1"]:
            token_info = pool_data.get(token_key, {})
            token_address = token_info.get("address", "")
            token_name = token_info.get("name", "")
            token_symbol = token_info.get("symbol", "")
            
            if not token_address:
                continue
            
            # Skip stablecoins and wrapped native tokens (usually safe)
            skip_tokens = ["USDC", "USDT", "DAI", "WETH", "WBNB", "WMATIC", "WBTC"]
            if token_symbol.upper() in skip_tokens:
                results["tokens"].append({
                    "address": token_address,
                    "symbol": token_symbol,
                    "name": token_name,
                    "classification": "SAFE",
                    "note": "Standard wrapped/stable token - skipping detailed analysis",
                    "composite_score": 0,
                    "risk_flags": ["KNOWN_SAFE_TOKEN"]
                })
                continue
            
            # Security analysis
            security_result = security_analyzer.analyze(chain, token_address)
            
            # Sentiment analysis (if available)
            if has_sentiment and token_name:
                sentiment_result = sentiment_analyzer.search(token_name, token_symbol, token_address)
            else:
                sentiment_result = {
                    "sentiment_score": 50,
                    "sentiment_flags": ["SENTIMENT_ANALYSIS_UNAVAILABLE"]
                }
            
            # Create market result from pool data
            market_result = {
                "liquidity_usd": pool_data.get("liquidity_usd", 0),
                "volume_24h": pool_data.get("volume_24h", 0),
                "price_change_24h": pool_data.get("price_change_24h", 0),
                "pair_count": 1,
                "market_flags": market_flags
            }
            
            # Classify
            classification = classifier.classify(security_result, market_result, sentiment_result)
            classification["address"] = token_address
            classification["symbol"] = token_symbol
            classification["name"] = token_name
            
            results["tokens"].append(classification)
        
        # Overall pool assessment
        token_classifications = [t.get("classification", "UNKNOWN") for t in results["tokens"]]
        if "DANGER" in token_classifications:
            results["overall_assessment"] = "DANGER"
            results["overall_recommendation"] = "🛑 At least one token in this pool is flagged as DANGER. Avoid interacting."
        elif "RISKY" in token_classifications:
            results["overall_assessment"] = "RISKY"
            results["overall_recommendation"] = "⚠️ At least one token has risk factors. Proceed with caution."
        else:
            results["overall_assessment"] = "SAFE"
            results["overall_recommendation"] = "✅ Both tokens appear relatively safe. Standard DeFi risks apply."
        
        return json.dumps(results, indent=2)


# ============================================================================
# Tool Builder
# ============================================================================

def build_token_intelligence_tools(config: Dict[str, Any]) -> List[BaseTool]:
    """
    Build token intelligence tools.
    
    Args:
        config: Application configuration
        
    Returns:
        List of configured tools
    """
    tools = [
        ResolvePoolTokensTool(config=config),
        CheckTokenSecurityTool(config=config),
        SearchTokenSentimentTool(config=config),
        ClassifyTokenRiskTool(config=config),
    ]
    
    return tools
