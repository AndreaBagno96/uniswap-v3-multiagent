"""
Market Risk & Impermanent Loss Analyzer
Calculates utilization rates and price correlation for IL risk assessment.
"""

import numpy as np
from typing import Dict, Any, List
from utils import GraphPaginator, CacheManager


class MarketRiskAnalyzer:
    """
    Analyzes market efficiency and impermanent loss risk.
    Examines utilization rates and token price correlations.
    """
    
    def __init__(self, paginator: GraphPaginator, cache: CacheManager, config: Dict[str, Any]):
        """
        Args:
            paginator: GraphPaginator instance for fetching data
            cache: CacheManager instance (poolDayData is cached)
            config: Configuration dict
        """
        self.paginator = paginator
        self.cache = cache
        self.config = config
    
    def analyze(self, pool_address: str) -> Dict[str, Any]:
        """
        Perform market risk analysis on a pool.
        
        Args:
            pool_address: Ethereum address of the Uniswap V3 pool
            
        Returns:
            Dict containing raw metrics and risk flags
        """
        # Fetch pool day data (with caching)
        pool_day_data = self._fetch_pool_day_data(pool_address)
        
        if not pool_day_data:
            return {
                "error": "No historical data found for this pool",
                "avg_utilization_rate": None,
                "price_correlation": None,
                "il_risk_level": None,
                "risk_flags": ["NO_DATA"]
            }
        
        # Calculate utilization rate (Volume/TVL)
        avg_utilization = self._calculate_avg_utilization(pool_day_data)
        
        # Calculate price correlation
        price_correlation = self._calculate_price_correlation(pool_day_data)
        
        # Determine IL risk level
        il_risk_level = self._determine_il_risk(price_correlation)
        
        # Generate risk flags
        risk_flags = self._generate_risk_flags(avg_utilization, price_correlation)
        
        return {
            "avg_utilization_rate": round(avg_utilization, 6),
            "price_correlation": round(price_correlation, 4),
            "il_risk_level": il_risk_level,
            "data_points": len(pool_day_data),
            "risk_flags": risk_flags,
            "risk_score": self._calculate_risk_score(avg_utilization, price_correlation)
        }
    
    def _fetch_pool_day_data(self, pool_address: str) -> List[Dict[str, Any]]:
        """
        Fetch last 30 days of pool data (with caching).
        """
        cache_key = f"{pool_address}_poolDayData_market"
        cached = self.cache.get(cache_key, "poolDayData")
        
        if cached is not None:
            return cached
        
        query = """
        query ($pool_id: String!, $days: Int!) {
          poolDayDatas(
            first: $days
            where: { pool: $pool_id }
            orderBy: date
            orderDirection: desc
          ) {
            date
            tvlUSD
            volumeUSD
            token0Price
            token1Price
          }
        }
        """
        
        variables = {
            "pool_id": pool_address.lower(),
            "days": self.config["queries"]["pool_day_data_days"]
        }
        
        # This query doesn't need pagination (only 30 records)
        response = self.paginator._execute_with_retry(query, variables)
        pool_day_data = response.get("data", {}).get("poolDayDatas", [])
        
        # Cache the result
        self.cache.set(cache_key, "poolDayData", pool_day_data)
        
        return pool_day_data
    
    def _calculate_avg_utilization(self, pool_day_data: List[Dict[str, Any]]) -> float:
        """
        Calculate average utilization rate (Volume/TVL).
        
        Args:
            pool_day_data: List of daily pool data
            
        Returns:
            Average daily utilization rate
        """
        utilization_rates = []
        
        for day_data in pool_day_data:
            tvl = float(day_data.get("tvlUSD", 0))
            volume = float(day_data.get("volumeUSD", 0))
            
            if tvl > 0:
                utilization_rates.append(volume / tvl)
        
        if not utilization_rates:
            return 0.0
        
        return np.mean(utilization_rates)
    
    def _calculate_price_correlation(self, pool_day_data: List[Dict[str, Any]]) -> float:
        """
        Calculate correlation between token0 and token1 price movements.
        Low/negative correlation = High IL risk.
        
        Args:
            pool_day_data: List of daily pool data
            
        Returns:
            Pearson correlation coefficient (-1 to 1)
        """
        token0_prices = []
        token1_prices = []
        
        for day_data in pool_day_data:
            token0_price = float(day_data.get("token0Price", 0))
            token1_price = float(day_data.get("token1Price", 0))
            
            if token0_price > 0 and token1_price > 0:
                token0_prices.append(token0_price)
                token1_prices.append(token1_price)
        
        if len(token0_prices) < 2:
            return 0.0
        
        # Calculate percentage changes
        token0_returns = np.diff(token0_prices) / token0_prices[:-1]
        token1_returns = np.diff(token1_prices) / token1_prices[:-1]
        
        if len(token0_returns) < 2:
            return 0.0
        
        # Calculate Pearson correlation
        correlation = np.corrcoef(token0_returns, token1_returns)[0, 1]
        
        # Handle NaN (can occur if variance is 0)
        if np.isnan(correlation):
            return 0.0
        
        return correlation
    
    def _determine_il_risk(self, correlation: float) -> str:
        """
        Determine impermanent loss risk level based on correlation.
        
        Args:
            correlation: Price correlation coefficient
            
        Returns:
            Risk level string
        """
        thresholds = self.config["risk_thresholds"]["market_risk"]
        
        if correlation < thresholds["price_correlation_high_il_risk"]:
            return "VERY_HIGH"  # Negative correlation
        elif correlation < thresholds["price_correlation_low_il_risk"]:
            return "HIGH"  # Low/no correlation
        elif correlation < 0.7:
            return "MEDIUM"
        else:
            return "LOW"  # High positive correlation
    
    def _generate_risk_flags(self, utilization: float, correlation: float) -> List[str]:
        """
        Generate risk flags based on thresholds.
        """
        flags = []
        thresholds = self.config["risk_thresholds"]["market_risk"]
        
        # Utilization rate checks
        if utilization < thresholds["utilization_rate_critical_low"]:
            flags.append("CRITICAL_LOW_UTILIZATION")
        elif utilization < thresholds["utilization_rate_low"]:
            flags.append("LOW_UTILIZATION")
        
        # Price correlation checks (IL risk)
        if correlation < thresholds["price_correlation_high_il_risk"]:
            flags.append("VERY_HIGH_IL_RISK")
        elif correlation < thresholds["price_correlation_low_il_risk"]:
            flags.append("HIGH_IL_RISK")
        
        return flags if flags else ["LOW_RISK"]
    
    def _calculate_risk_score(self, utilization: float, correlation: float) -> int:
        """
        Calculate a 0-100 risk score for market risk.
        
        Args:
            utilization: Average utilization rate
            correlation: Price correlation
            
        Returns:
            Risk score 0-100
        """
        # Low utilization = High risk (LPs not earning fees)
        # Target utilization: 0.05 (5% daily volume/TVL is healthy)
        target_utilization = 0.05
        utilization_score = max(0, 100 - (utilization / target_utilization * 100))
        utilization_score = min(utilization_score, 100)
        
        # Low/negative correlation = High IL risk
        # Convert correlation (-1 to 1) to risk score (0 to 100)
        # correlation = 1 -> score = 0 (low risk)
        # correlation = -1 -> score = 100 (high risk)
        correlation_score = (1 - correlation) / 2 * 100
        
        # Weighted average (IL risk weighted more heavily)
        composite = (utilization_score * 0.3) + (correlation_score * 0.7)
        
        return int(round(composite))
