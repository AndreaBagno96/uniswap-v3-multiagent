"""
Token Sentiment Analyzer - Tavily integration for web search and sentiment analysis.
Searches for project reputation, social signals, and scam reports.
"""

import os
from typing import Any, Dict, List
from tavily import TavilyClient


class TokenSentimentAnalyzer:
    """
    Analyzes token/project sentiment using web search via Tavily API.
    Searches for reputation, social signals, scam reports, and team info.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Configuration dict
        """
        self.config = config
        
        # Initialize Tavily client
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError("TAVILY_API_KEY environment variable is required")
        
        self.client = TavilyClient(api_key=api_key)
    
    def search(self, token_name: str, token_symbol: str, token_address: str = "") -> Dict[str, Any]:
        """
        Search for token/project information and analyze sentiment.
        
        Args:
            token_name: Full name of the token
            token_symbol: Token symbol (e.g., "ETH")
            token_address: Optional contract address for more specific search
            
        Returns:
            Dict with search results, sentiment_score, and flags
        """
        # Build search query
        search_query = self._build_search_query(token_name, token_symbol)
        
        try:
            # Perform search
            response = self.client.search(
                query=search_query,
                search_depth="advanced",
                max_results=10,
                include_domains=["twitter.com", "reddit.com", "medium.com", "coingecko.com", 
                               "coinmarketcap.com", "dextools.io", "etherscan.io"],
                exclude_domains=["pinterest.com", "facebook.com"]
            )
            
            results = response.get("results", [])
            
            # Analyze results for sentiment signals
            sentiment_analysis = self._analyze_results(results, token_name, token_symbol)
            
            # Search for scam reports specifically
            scam_check = self._search_scam_reports(token_name, token_symbol)
            
            # Combine analyses
            combined_flags = sentiment_analysis["flags"] + scam_check.get("flags", [])
            combined_score = (sentiment_analysis["score"] + scam_check.get("score", 0)) / 2
            
            return {
                "token_name": token_name,
                "token_symbol": token_symbol,
                "search_results_count": len(results),
                "top_results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", "")[:200] + "..." if len(r.get("content", "")) > 200 else r.get("content", "")
                    }
                    for r in results[:5]
                ],
                "sentiment_score": int(combined_score),
                "sentiment_flags": list(set(combined_flags)),
                "scam_mentions": scam_check.get("scam_mentions", 0),
                "positive_signals": sentiment_analysis.get("positive_signals", []),
                "negative_signals": sentiment_analysis.get("negative_signals", []),
                "summary": self._generate_summary(sentiment_analysis, scam_check)
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "sentiment_score": 50,
                "sentiment_flags": ["SEARCH_FAILED"]
            }
    
    def _build_search_query(self, token_name: str, token_symbol: str) -> str:
        """Build an effective search query for the token."""
        # Clean up names
        name = token_name.strip()
        symbol = token_symbol.strip().upper()
        
        # Construct query to find relevant crypto info
        return f"{name} {symbol} cryptocurrency token review legitimacy"
    
    def _analyze_results(self, results: List[Dict], token_name: str, token_symbol: str) -> Dict[str, Any]:
        """Analyze search results for sentiment signals."""
        positive_signals = []
        negative_signals = []
        flags = []
        score = 50  # Start neutral
        
        if not results:
            flags.append("NO_SEARCH_RESULTS")
            return {
                "score": 70,  # No info is slightly risky
                "flags": flags,
                "positive_signals": [],
                "negative_signals": ["No information found online"]
            }
        
        # Analyze content for signals
        combined_content = " ".join([
            (r.get("title", "") + " " + r.get("content", "")).lower() 
            for r in results
        ])
        
        # Positive signals
        positive_keywords = [
            "verified", "audited", "legitimate", "trusted", "official",
            "partnership", "listed on", "coingecko", "coinmarketcap",
            "strong community", "active development", "transparent"
        ]
        
        for keyword in positive_keywords:
            if keyword in combined_content:
                positive_signals.append(keyword)
                score -= 3
        
        # Negative signals
        negative_keywords = [
            "scam", "rug pull", "rugpull", "honeypot", "fraud",
            "warning", "avoid", "fake", "ponzi", "hack", "exploit",
            "drained", "stolen", "suspicious", "unsafe"
        ]
        
        for keyword in negative_keywords:
            count = combined_content.count(keyword)
            if count > 0:
                negative_signals.append(f"{keyword} ({count} mentions)")
                score += 5 * min(count, 5)  # Cap contribution per keyword
        
        # Check for established presence
        domains_found = [r.get("url", "").split("/")[2] if "/" in r.get("url", "") else "" for r in results]
        
        if any("coingecko.com" in d for d in domains_found):
            positive_signals.append("Listed on CoinGecko")
            score -= 10
        
        if any("coinmarketcap.com" in d for d in domains_found):
            positive_signals.append("Listed on CoinMarketCap")
            score -= 10
        
        # Generate flags
        if len(negative_signals) > 3:
            flags.append("MULTIPLE_NEGATIVE_MENTIONS")
        
        if "scam" in combined_content or "rug pull" in combined_content:
            flags.append("SCAM_REPORTS_FOUND")
            score += 20
        
        if not positive_signals and len(negative_signals) > 0:
            flags.append("NO_POSITIVE_SIGNALS")
        
        if positive_signals and not negative_signals:
            flags.append("POSITIVE_SENTIMENT")
        
        # Clamp score
        score = max(0, min(100, score))
        
        if not flags:
            flags.append("SENTIMENT_NEUTRAL")
        
        return {
            "score": score,
            "flags": flags,
            "positive_signals": positive_signals,
            "negative_signals": negative_signals
        }
    
    def _search_scam_reports(self, token_name: str, token_symbol: str) -> Dict[str, Any]:
        """Specifically search for scam reports about the token."""
        try:
            query = f"{token_name} {token_symbol} scam OR rugpull OR fraud warning"
            
            response = self.client.search(
                query=query,
                search_depth="basic",
                max_results=5
            )
            
            results = response.get("results", [])
            scam_mentions = 0
            flags = []
            score = 0
            
            for result in results:
                content = (result.get("title", "") + " " + result.get("content", "")).lower()
                
                # Check if this is actually about our token being a scam
                if token_symbol.lower() in content or token_name.lower() in content:
                    if "scam" in content:
                        scam_mentions += 1
                        score += 15
                    if "rug" in content:
                        scam_mentions += 1
                        score += 15
                    if "honeypot" in content:
                        scam_mentions += 1
                        score += 20
            
            if scam_mentions > 0:
                flags.append(f"SCAM_REPORTS_{scam_mentions}")
            
            return {
                "scam_mentions": scam_mentions,
                "score": min(100, score),
                "flags": flags
            }
            
        except Exception as e:
            return {"scam_mentions": 0, "score": 0, "flags": [], "error": str(e)}
    
    def _generate_summary(self, sentiment: Dict, scam_check: Dict) -> str:
        """Generate a human-readable summary of findings."""
        parts = []
        
        positive = sentiment.get("positive_signals", [])
        negative = sentiment.get("negative_signals", [])
        scam_count = scam_check.get("scam_mentions", 0)
        
        if scam_count > 0:
            parts.append(f"⚠️ Found {scam_count} potential scam report(s) online.")
        
        if positive:
            parts.append(f"✅ Positive signals: {', '.join(positive[:3])}")
        
        if negative:
            parts.append(f"❌ Negative signals: {', '.join(negative[:3])}")
        
        if not positive and not negative and scam_count == 0:
            parts.append("ℹ️ Limited information available online about this token.")
        
        return " ".join(parts)
