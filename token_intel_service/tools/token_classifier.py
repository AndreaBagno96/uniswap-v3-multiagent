"""
Token Classifier - Aggregates security, market, and sentiment analysis into final classification.
Determines if a token is SAFE, RISKY, or DANGER.
"""

from typing import Any, Dict, List


class TokenClassifier:
    """
    Aggregates all token intelligence data and produces final risk classification.
    Uses weighted scoring across security, market, and sentiment dimensions.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Configuration dict with classification thresholds
        """
        self.config = config
        ti_config = config.get("token_intelligence", {})
        
        self.weights = ti_config.get("weights", {
            "security": 0.40,
            "market": 0.35,
            "sentiment": 0.25
        })
        
        self.classification = ti_config.get("classification", {
            "safe": {"max_score": 25},
            "risky": {"min_score": 26, "max_score": 60},
            "danger": {"min_score": 61}
        })
    
    def classify(
        self,
        security_result: Dict[str, Any],
        market_result: Dict[str, Any],
        sentiment_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Classify token based on all analysis results.
        
        Args:
            security_result: Output from TokenSecurityAnalyzer
            market_result: Output from TokenResolver (market data)
            sentiment_result: Output from TokenSentimentAnalyzer
            
        Returns:
            Dict with classification, composite_score, and aggregated flags
        """
        # Extract scores
        security_score = security_result.get("risk_score", 50)
        market_score = self._calculate_market_score(market_result)
        sentiment_score = sentiment_result.get("sentiment_score", 50)
        
        # Calculate weighted composite score
        composite_score = (
            security_score * self.weights["security"] +
            market_score * self.weights["market"] +
            sentiment_score * self.weights["sentiment"]
        )
        composite_score = int(round(composite_score))
        
        # Determine classification
        classification = self._determine_classification(composite_score, security_result)
        
        # Aggregate flags
        all_flags = (
            security_result.get("risk_flags", []) +
            market_result.get("market_flags", []) +
            sentiment_result.get("sentiment_flags", [])
        )
        
        # Remove OK flags if there are issues
        critical_flags = [f for f in all_flags if not f.endswith("_OK")]
        final_flags = critical_flags if critical_flags else ["ALL_CHECKS_PASSED"]
        
        # Generate recommendation
        recommendation = self._generate_recommendation(
            classification, final_flags, security_result, market_result
        )
        
        return {
            "classification": classification,
            "composite_score": composite_score,
            "component_scores": {
                "security": security_score,
                "market": market_score,
                "sentiment": sentiment_score
            },
            "weights_used": self.weights,
            "risk_flags": final_flags,
            "critical_issues": self._identify_critical_issues(security_result, market_result),
            "recommendation": recommendation,
            "token_info": {
                "name": security_result.get("token_name", ""),
                "symbol": security_result.get("token_symbol", ""),
                "is_honeypot": security_result.get("is_honeypot", False),
                "buy_tax": security_result.get("buy_tax_pct", 0),
                "sell_tax": security_result.get("sell_tax_pct", 0),
                "liquidity_usd": market_result.get("liquidity_usd", 0),
                "holder_count": security_result.get("holder_count", 0)
            }
        }
    
    def _calculate_market_score(self, market_result: Dict[str, Any]) -> int:
        """Calculate risk score from market data."""
        if "error" in market_result:
            return 50  # Unknown risk
        
        score = 0
        flags = []
        thresholds = self.config.get("token_intelligence", {}).get("thresholds", {})
        
        # Liquidity check
        liquidity = market_result.get("liquidity_usd", 0) or market_result.get("total_liquidity_usd", 0)
        min_liquidity = thresholds.get("min_liquidity_usd", 10000)
        
        if liquidity < 1000:
            score += 40
            flags.append("EXTREMELY_LOW_LIQUIDITY")
        elif liquidity < min_liquidity:
            score += 25
            flags.append("LOW_LIQUIDITY")
        elif liquidity < 50000:
            score += 10
            flags.append("MODERATE_LIQUIDITY")
        
        # Volume/liquidity ratio (wash trading indicator)
        volume = market_result.get("volume_24h", 0) or market_result.get("total_volume_24h", 0)
        if liquidity > 0:
            ratio = volume / liquidity
            if ratio > 10:
                score += 20
                flags.append("SUSPICIOUS_VOLUME")
            elif ratio > 5:
                score += 10
        
        # Price volatility
        price_change = abs(market_result.get("price_change_24h", 0))
        if price_change > 50:
            score += 15
            flags.append("HIGH_VOLATILITY")
        elif price_change > 20:
            score += 5
        
        # Pair count (more pairs = more established)
        pair_count = market_result.get("pair_count", 1)
        if pair_count == 1:
            score += 10
            flags.append("SINGLE_PAIR")
        
        # Store flags in result for later use
        market_result["market_flags"] = flags if flags else ["MARKET_OK"]
        
        return min(100, score)
    
    def _determine_classification(
        self, 
        composite_score: int, 
        security_result: Dict[str, Any]
    ) -> str:
        """Determine final classification with override for critical issues."""
        
        # Immediate DANGER for honeypot
        if security_result.get("is_honeypot"):
            return "DANGER"
        
        # Critical security flags override score
        critical_flags = ["HONEYPOT_DETECTED", "OWNER_CAN_MODIFY_BALANCE", "SELFDESTRUCT_FUNCTION"]
        security_flags = security_result.get("risk_flags", [])
        
        if any(flag in security_flags for flag in critical_flags):
            return "DANGER"
        
        # Score-based classification
        safe_max = self.classification["safe"]["max_score"]
        danger_min = self.classification["danger"]["min_score"]
        
        if composite_score <= safe_max:
            return "SAFE"
        elif composite_score >= danger_min:
            return "DANGER"
        else:
            return "RISKY"
    
    def _identify_critical_issues(
        self, 
        security_result: Dict[str, Any],
        market_result: Dict[str, Any]
    ) -> List[str]:
        """Identify critical issues that require immediate attention."""
        issues = []
        
        if security_result.get("is_honeypot"):
            issues.append("🚨 HONEYPOT: Cannot sell tokens")
        
        if security_result.get("owner_change_balance"):
            issues.append("🚨 Owner can modify token balances")
        
        if security_result.get("selfdestruct"):
            issues.append("🚨 Contract has self-destruct function")
        
        if security_result.get("hidden_owner"):
            issues.append("⚠️ Hidden owner detected")
        
        sell_tax = security_result.get("sell_tax_pct", 0)
        if sell_tax > 20:
            issues.append(f"⚠️ Very high sell tax: {sell_tax}%")
        
        liquidity = market_result.get("liquidity_usd", 0)
        if liquidity < 1000:
            issues.append(f"⚠️ Extremely low liquidity: ${liquidity:,.0f}")
        
        return issues
    
    def _generate_recommendation(
        self,
        classification: str,
        flags: List[str],
        security_result: Dict[str, Any],
        market_result: Dict[str, Any]
    ) -> str:
        """Generate human-readable recommendation."""
        
        if classification == "DANGER":
            if security_result.get("is_honeypot"):
                return "🛑 DO NOT INTERACT - This token is a confirmed honeypot. You will not be able to sell."
            return "🛑 HIGH RISK - Multiple critical security issues detected. Avoid this token."
        
        elif classification == "RISKY":
            issues = []
            if "LOW_LIQUIDITY" in flags or "EXTREMELY_LOW_LIQUIDITY" in flags:
                issues.append("low liquidity")
            if "HIGH_TAX_RATE" in flags:
                issues.append("high taxes")
            if "MINTABLE_TOKEN" in flags:
                issues.append("mintable supply")
            
            issue_str = ", ".join(issues) if issues else "various concerns"
            return f"⚠️ PROCEED WITH CAUTION - This token has {issue_str}. Only invest what you can afford to lose."
        
        else:  # SAFE
            liquidity = market_result.get("liquidity_usd", 0)
            if liquidity > 100000:
                return "✅ RELATIVELY SAFE - No major red flags detected and good liquidity. Standard DeFi risks still apply."
            else:
                return "✅ APPEARS SAFE - No major red flags, but liquidity is moderate. Trade carefully."
