"""
Risk Scorer - Aggregates all risk analysis modules into composite score.
"""

from typing import Dict, Any


class RiskScorer:
    """
    Combines outputs from all risk analyzers into a weighted composite score.
    Determines overall risk level (LOW/MEDIUM/HIGH/CRITICAL).
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Configuration dict containing scoring weights and thresholds
        """
        self.config = config
        self.weights = config["scoring"]["weights"]
        self.risk_levels = config["scoring"]["risk_levels"]
    
    def score(
        self,
        concentration_result: Dict[str, Any],
        liquidity_result: Dict[str, Any],
        market_result: Dict[str, Any],
        behavioral_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate composite risk score from all analyzer outputs.
        
        Args:
            concentration_result: Output from ConcentrationRiskAnalyzer
            liquidity_result: Output from LiquidityDepthAnalyzer
            market_result: Output from MarketRiskAnalyzer
            behavioral_result: Output from BehavioralRiskAnalyzer
            
        Returns:
            Dict containing composite score, risk level, and all raw metrics
        """
        # Extract individual risk scores
        concentration_score = concentration_result.get("risk_score", 0)
        liquidity_score = liquidity_result.get("risk_score", 0)
        market_score = market_result.get("risk_score", 0)
        behavioral_score = behavioral_result.get("risk_score", 0)
        
        # Calculate weighted composite score
        composite_score = (
            concentration_score * self.weights["concentration"] +
            liquidity_score * self.weights["liquidity_depth"] +
            market_score * self.weights["market_risk"] +
            behavioral_score * self.weights["behavioral"]
        )
        
        # Round to integer
        composite_score = int(round(composite_score))
        
        # Determine risk level
        risk_level = self._determine_risk_level(composite_score)
        
        # Aggregate all risk flags
        all_flags = (
            concentration_result.get("risk_flags", []) +
            liquidity_result.get("risk_flags", []) +
            market_result.get("risk_flags", []) +
            behavioral_result.get("risk_flags", [])
        )
        
        # Remove "LOW_RISK" flags if there are other flags
        critical_flags = [f for f in all_flags if f != "LOW_RISK"]
        final_flags = critical_flags if critical_flags else ["LOW_RISK"]
        
        return {
            "composite_score": composite_score,
            "risk_level": risk_level,
            "risk_flags": final_flags,
            "component_scores": {
                "concentration": concentration_score,
                "liquidity_depth": liquidity_score,
                "market_risk": market_score,
                "behavioral": behavioral_score
            },
            "raw_metrics": {
                "concentration": concentration_result,
                "liquidity_depth": liquidity_result,
                "market_risk": market_result,
                "behavioral": behavioral_result
            }
        }
    
    def _determine_risk_level(self, score: int) -> str:
        """
        Map composite score to risk level based on configured thresholds.
        
        Args:
            score: Composite risk score (0-100)
            
        Returns:
            Risk level string (LOW/MEDIUM/HIGH/CRITICAL)
        """
        for level, bounds in self.risk_levels.items():
            if bounds["min"] <= score <= bounds["max"]:
                return level.upper()
        
        # Fallback (should never reach here with valid config)
        return "UNKNOWN"
