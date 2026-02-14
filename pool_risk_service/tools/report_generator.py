"""
Report Generator - Converts raw risk metrics into human-readable Markdown.
"""

from typing import Dict, Any
from datetime import datetime


class ReportGenerator:
    """
    Generates human-readable Markdown reports from risk analysis results.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Configuration dict (for reference)
        """
        self.config = config
    
    def generate(self, pool_address: str, pool_info: Dict[str, Any], risk_score_result: Dict[str, Any]) -> str:
        """
        Generate a comprehensive Markdown report.
        
        Args:
            pool_address: Pool address
            pool_info: Basic pool information (token symbols, TVL, etc.)
            risk_score_result: Output from RiskScorer
            
        Returns:
            Markdown-formatted report string
        """
        sections = []
        
        # Header
        sections.append(self._generate_header(pool_address, pool_info, risk_score_result))
        
        # Executive Summary
        sections.append(self._generate_executive_summary(risk_score_result))
        
        # Detailed Analysis Sections
        sections.append(self._generate_concentration_section(risk_score_result["raw_metrics"]["concentration"]))
        sections.append(self._generate_liquidity_section(risk_score_result["raw_metrics"]["liquidity_depth"]))
        sections.append(self._generate_market_section(risk_score_result["raw_metrics"]["market_risk"]))
        sections.append(self._generate_behavioral_section(risk_score_result["raw_metrics"]["behavioral"]))
        
        # Recommendations
        sections.append(self._generate_recommendations(risk_score_result))
        
        # Footer
        sections.append(self._generate_footer())
        
        return "\n\n".join(sections)
    
    def _generate_header(self, pool_address: str, pool_info: Dict[str, Any], risk_score_result: Dict[str, Any]) -> str:
        """Generate report header."""
        risk_level = risk_score_result["risk_level"]
        composite_score = risk_score_result["composite_score"]
        
        # Risk level emoji
        emoji_map = {
            "LOW": "🟢",
            "MEDIUM": "🟡",
            "HIGH": "🟠",
            "CRITICAL": "🔴"
        }
        emoji = emoji_map.get(risk_level, "⚪")
        
        token0 = pool_info.get("token0", {}).get("symbol", "TOKEN0")
        token1 = pool_info.get("token1", {}).get("symbol", "TOKEN1")
        
        return f"""# Uniswap V3 Pool Risk Analysis Report

**Pool:** {token0}/{token1}  
**Address:** `{pool_address}`  
**Risk Level:** {emoji} **{risk_level}** (Score: {composite_score}/100)  
**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}"""
    
    def _generate_executive_summary(self, risk_score_result: Dict[str, Any]) -> str:
        """Generate executive summary section."""
        risk_level = risk_score_result["risk_level"]
        composite_score = risk_score_result["composite_score"]
        flags = risk_score_result["risk_flags"]
        component_scores = risk_score_result["component_scores"]
        
        # Filter out LOW_RISK flag for display
        critical_flags = [f for f in flags if f != "LOW_RISK"]
        
        summary = f"""## Executive Summary

This pool has been assigned a **{risk_level}** risk rating with a composite score of **{composite_score}/100**.

### Component Risk Scores
- **Concentration Risk:** {component_scores['concentration']}/100
- **Liquidity Depth Risk:** {component_scores['liquidity_depth']}/100
- **Market Risk:** {component_scores['market_risk']}/100
- **Behavioral Risk:** {component_scores['behavioral']}/100"""
        
        if critical_flags:
            summary += f"\n\n### ⚠️ Active Risk Flags\n"
            for flag in critical_flags:
                summary += f"- `{flag}`\n"
        else:
            summary += f"\n\n### ✅ No Critical Risk Flags Detected"
        
        return summary
    
    def _generate_concentration_section(self, concentration_data: Dict[str, Any]) -> str:
        """Generate concentration risk section."""
        if "error" in concentration_data:
            return f"## 1. Concentration Risk (Whale Analysis)\n\n⚠️ {concentration_data['error']}"
        
        gini = concentration_data["gini_coefficient"]
        hhi = concentration_data["herfindahl_hirschman_index"]
        top10 = concentration_data["top10_dominance_pct"]
        lp_age = concentration_data["lp_age_distribution"]
        
        section = f"""## 1. Concentration Risk (Whale Analysis)

### Inequality Metrics
- **Gini Coefficient:** {gini} (0 = perfect equality, 1 = perfect inequality)
- **HHI Index:** {hhi} (>2500 = high concentration)
- **Top 10 Holder Dominance:** {top10}%

### LP Age Distribution
- **Mercenary LPs (<7 days):** {lp_age['mercenary']['count']} positions ({lp_age['mercenary']['liquidity_pct']}% of liquidity)
- **Medium-term LPs (7-30 days):** {lp_age['medium_term']['count']} positions ({lp_age['medium_term']['liquidity_pct']}% of liquidity)
- **Long-term LPs (>30 days):** {lp_age['long_term']['count']} positions ({lp_age['long_term']['liquidity_pct']}% of liquidity)

### Interpretation
"""
        
        # Add interpretation
        if top10 > 70:
            section += "⚠️ **CRITICAL:** Liquidity is extremely concentrated. Top 10 holders control the majority of the pool.\n"
        elif top10 > 50:
            section += "⚠️ **HIGH RISK:** Top 10 holders have significant control. Pool vulnerable to coordinated exits.\n"
        else:
            section += "✅ Liquidity distribution appears healthy.\n"
        
        if lp_age['mercenary']['liquidity_pct'] > 50:
            section += "⚠️ **FLIGHT RISK:** Majority of liquidity is from new positions (<7 days old).\n"
        
        return section
    
    def _generate_liquidity_section(self, liquidity_data: Dict[str, Any]) -> str:
        """Generate liquidity depth section."""
        if "error" in liquidity_data:
            return f"## 2. Liquidity & Depth Risk\n\n⚠️ {liquidity_data['error']}"
        
        impact_100k = liquidity_data["price_impact_100k_pct"]
        impact_1m = liquidity_data["price_impact_1m_pct"]
        active = liquidity_data["active_liquidity_pct"]
        volatility = liquidity_data["tvl_volatility_30d_pct"]
        
        section = f"""## 2. Liquidity & Depth Risk

### Slippage Simulation
- **$100K Sell Order Impact:** {impact_100k}%
- **$1M Sell Order Impact:** {impact_1m}%

### Liquidity Efficiency
- **Active (In-Range) Liquidity:** {active}%
- **TVL Volatility (30-day):** {volatility}%

### Interpretation
"""
        
        # Add interpretation
        if impact_100k > 3:
            section += "⚠️ **CRITICAL:** Extremely high slippage for moderate-sized orders. Poor liquidity depth.\n"
        elif impact_100k > 1:
            section += "⚠️ **MODERATE:** Noticeable slippage on $100K orders. May deter large traders.\n"
        else:
            section += "✅ Good liquidity depth for retail-sized orders.\n"
        
        if active < 30:
            section += "⚠️ **INEFFICIENT:** Most liquidity is out-of-range and not earning fees or providing depth.\n"
        
        return section
    
    def _generate_market_section(self, market_data: Dict[str, Any]) -> str:
        """Generate market risk section."""
        if "error" in market_data:
            return f"## 3. Market Risk & Impermanent Loss\n\n⚠️ {market_data['error']}"
        
        utilization = market_data["avg_utilization_rate"]
        correlation = market_data["price_correlation"]
        il_risk = market_data["il_risk_level"]
        
        section = f"""## 3. Market Risk & Impermanent Loss

### Efficiency Metrics
- **Avg Utilization Rate (Volume/TVL):** {utilization:.4f} ({utilization*100:.2f}% daily)
- **Token Price Correlation:** {correlation}
- **IL Risk Level:** {il_risk}

### Interpretation
"""
        
        # Add interpretation
        if utilization < 0.01:
            section += "⚠️ **CRITICAL:** Very low utilization. LPs earning minimal fees, likely to exit.\n"
        elif utilization < 0.05:
            section += "⚠️ **LOW EFFICIENCY:** Below-average utilization. May not attract long-term LPs.\n"
        else:
            section += "✅ Healthy utilization rate. LPs are earning competitive fees.\n"
        
        if il_risk in ["VERY_HIGH", "HIGH"]:
            section += f"⚠️ **{il_risk} IL RISK:** Token prices are moving independently. High impermanent loss exposure.\n"
        
        return section
    
    def _generate_behavioral_section(self, behavioral_data: Dict[str, Any]) -> str:
        """Generate behavioral risk section."""
        if "error" in behavioral_data:
            return f"## 4. Behavioral Risk (Wash Trading & MEV)\n\n⚠️ {behavioral_data['error']}"
        
        wash = behavioral_data["wash_trading_pct"]
        mev = behavioral_data["mev_exposure_pct"]
        swaps = behavioral_data["total_swaps_analyzed"]
        
        section = f"""## 4. Behavioral Risk (Wash Trading & MEV)

### Bot Activity Metrics
- **Wash Trading Index:** {wash}% of {swaps} swaps
- **MEV Exposure (Sandwich Attacks):** {mev}%

### Interpretation
"""
        
        # Add interpretation
        if wash > 15:
            section += "⚠️ **CRITICAL:** Extremely high wash trading detected. Volume is likely inorganic.\n"
        elif wash > 5:
            section += "⚠️ **MODERATE:** Notable wash trading activity. Exercise caution with volume metrics.\n"
        else:
            section += "✅ Low wash trading. Volume appears organic.\n"
        
        if mev > 25:
            section += "⚠️ **CRITICAL:** Pool is heavily targeted by MEV bots. Retail traders at high risk.\n"
        elif mev > 10:
            section += "⚠️ **MODERATE:** Significant MEV activity. Users should use MEV protection.\n"
        
        return section
    
    def _generate_recommendations(self, risk_score_result: Dict[str, Any]) -> str:
        """Generate actionable recommendations."""
        risk_level = risk_score_result["risk_level"]
        flags = risk_score_result["risk_flags"]
        
        recommendations = ["## Recommendations\n"]
        
        if risk_level == "CRITICAL":
            recommendations.append("🔴 **DO NOT PROVIDE LIQUIDITY** to this pool without understanding the severe risks.")
        elif risk_level == "HIGH":
            recommendations.append("🟠 **CAUTION ADVISED:** Only provide liquidity if you can actively monitor and exit quickly.")
        elif risk_level == "MEDIUM":
            recommendations.append("🟡 **MODERATE RISK:** Suitable for experienced LPs who understand concentrated liquidity.")
        else:
            recommendations.append("🟢 **GENERALLY SAFE:** Pool shows healthy fundamentals for liquidity provision.")
        
        recommendations.append("\n### Specific Actions:\n")
        
        # Flag-specific recommendations
        if any("TOP10_DOMINANCE" in f for f in flags):
            recommendations.append("- Monitor large LP positions for exit signals")
        
        if any("MERCENARY" in f for f in flags):
            recommendations.append("- Expect potential liquidity flight; avoid long-term commitments")
        
        if any("SLIPPAGE" in f for f in flags):
            recommendations.append("- Use limit orders and slippage protection for large trades")
        
        if any("UTILIZATION" in f for f in flags):
            recommendations.append("- Low fee generation; consider more active pools")
        
        if any("IL_RISK" in f for f in flags):
            recommendations.append("- Tokens are uncorrelated; prepare for significant impermanent loss")
        
        if any("WASH_TRADING" in f for f in flags):
            recommendations.append("- Volume metrics are unreliable; verify with other data sources")
        
        if any("MEV" in f for f in flags):
            recommendations.append("- Use MEV-protected RPC endpoints (e.g., Flashbots, MEVBlocker)")
        
        return "\n".join(recommendations)
    
    def _generate_footer(self) -> str:
        """Generate report footer."""
        return """---

**Disclaimer:** This analysis is for informational purposes only and does not constitute financial advice. 
Risk metrics are based on on-chain data and mathematical models, which may not capture all risk factors. 
Always conduct your own research before providing liquidity or trading."""
