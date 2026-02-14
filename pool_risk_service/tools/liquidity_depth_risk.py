"""
Liquidity Depth & Slippage Risk Analyzer
Simulates large sell orders and analyzes liquidity distribution in Uniswap V3.
"""

import numpy as np
from typing import Dict, Any, List, Tuple
from utils import GraphPaginator, CacheManager


class LiquidityDepthAnalyzer:
    """
    Analyzes pool resilience to large sell orders using concentrated liquidity model.
    Calculates market depth, slippage, and TVL volatility.
    """
    
    def __init__(self, paginator: GraphPaginator, cache: CacheManager, config: Dict[str, Any]):
        """
        Args:
            paginator: GraphPaginator instance for fetching data
            cache: CacheManager instance (ticks and poolDayData are cached)
            config: Configuration dict
        """
        self.paginator = paginator
        self.cache = cache
        self.config = config
    
    def analyze(self, pool_address: str, current_price: float) -> Dict[str, Any]:
        """
        Perform liquidity depth analysis on a pool.
        
        Args:
            pool_address: Ethereum address of the Uniswap V3 pool
            current_price: Current price (token1/token0)
            
        Returns:
            Dict containing raw metrics and risk flags
        """
        # Fetch ticks (with caching)
        ticks = self._fetch_ticks(pool_address)
        
        if not ticks:
            return {
                "error": "No tick data found for this pool",
                "price_impact_100k": None,
                "price_impact_1m": None,
                "active_liquidity_pct": None,
                "tvl_volatility_pct": None,
                "risk_flags": ["NO_DATA"]
            }
        
        # Simulate sell orders
        impact_100k = self._simulate_sell_order(ticks, current_price, 100_000)
        impact_1m = self._simulate_sell_order(ticks, current_price, 1_000_000)
        
        # Calculate active vs inactive liquidity
        active_liquidity_pct = self._calculate_active_liquidity(ticks, current_price)
        
        # Get TVL volatility from poolDayData
        tvl_volatility = self._calculate_tvl_volatility(pool_address)
        
        # Generate risk flags
        risk_flags = self._generate_risk_flags(impact_100k, impact_1m, active_liquidity_pct, tvl_volatility)
        
        return {
            "price_impact_100k_pct": round(impact_100k, 4),
            "price_impact_1m_pct": round(impact_1m, 4),
            "active_liquidity_pct": round(active_liquidity_pct, 2),
            "tvl_volatility_30d_pct": round(tvl_volatility, 2),
            "total_ticks": len(ticks),
            "risk_flags": risk_flags,
            "risk_score": self._calculate_risk_score(impact_100k, impact_1m, active_liquidity_pct, tvl_volatility)
        }
    
    def _fetch_ticks(self, pool_address: str) -> List[Dict[str, Any]]:
        """
        Fetch all active ticks for a pool (with caching).
        """
        cache_key = f"{pool_address}_ticks"
        cached = self.cache.get(cache_key, "ticks")
        
        if cached is not None:
            return cached
        
        query = """
        query ($pool_id: String!, $last_id: ID!, $batch_size: Int!) {
          ticks(
            first: $batch_size
            where: {
              pool: $pool_id
              liquidityNet_not: "0"
              id_gt: $last_id
            }
            orderBy: id
            orderDirection: asc
          ) {
            id
            tickIdx
            liquidityNet
            liquidityGross
          }
        }
        """
        
        variables = {"pool_id": pool_address.lower()}
        
        ticks = self.paginator.fetch_all(
            query_template=query,
            variables=variables,
            entity_name="ticks"
        )
        
        # Cache the result
        self.cache.set(cache_key, "ticks", ticks)
        
        return ticks
    
    def _simulate_sell_order(self, ticks: List[Dict[str, Any]], current_price: float, sell_amount_usd: float) -> float:
        """
        Simulate a sell order and calculate price impact.
        
        Args:
            ticks: List of tick data
            current_price: Current price (token1/token0)
            sell_amount_usd: Size of sell order in USD
            
        Returns:
            Price impact as percentage
        """
        # This is a simplified simulation
        # In reality, you'd need to walk through ticks and calculate the exact output
        # For this implementation, we use a heuristic based on liquidity distribution
        
        # Sort ticks by tick index
        sorted_ticks = sorted(ticks, key=lambda t: int(t["tickIdx"]))
        
        # Calculate total liquidity in range
        total_liquidity = sum(abs(float(t["liquidityGross"])) for t in sorted_ticks)
        
        if total_liquidity == 0:
            return 100.0  # Max impact
        
        # Simplified price impact formula:
        # impact ≈ (sell_amount / sqrt(liquidity))
        # This is a rough approximation of AMM slippage
        
        impact = (sell_amount_usd / np.sqrt(total_liquidity)) * 100
        
        return min(impact, 100.0)  # Cap at 100%
    
    def _calculate_active_liquidity(self, ticks: List[Dict[str, Any]], current_price: float) -> float:
        """
        Calculate percentage of liquidity that is in-range (active).
        
        Args:
            ticks: List of tick data
            current_price: Current price
            
        Returns:
            Percentage of active liquidity (0-100)
        """
        if not ticks:
            return 0.0
        
        # Convert price to tick (Uniswap V3 formula: tick = log_1.0001(price))
        current_tick = int(np.log(current_price) / np.log(1.0001))
        
        # Define "active range" as ±10% price movement
        tick_spacing = int(np.log(1.1) / np.log(1.0001))  # ~953 ticks
        lower_bound = current_tick - tick_spacing
        upper_bound = current_tick + tick_spacing
        
        active_liquidity = 0.0
        total_liquidity = 0.0
        
        for tick in ticks:
            tick_idx = int(tick["tickIdx"])
            liquidity = abs(float(tick["liquidityGross"]))
            
            total_liquidity += liquidity
            
            if lower_bound <= tick_idx <= upper_bound:
                active_liquidity += liquidity
        
        if total_liquidity == 0:
            return 0.0
        
        return (active_liquidity / total_liquidity) * 100
    
    def _calculate_tvl_volatility(self, pool_address: str) -> float:
        """
        Calculate standard deviation of TVL over last 30 days.
        
        Args:
            pool_address: Pool address
            
        Returns:
            TVL volatility as percentage
        """
        cache_key = f"{pool_address}_poolDayData"
        cached = self.cache.get(cache_key, "poolDayData")
        
        if cached is not None:
            pool_day_data = cached
        else:
            pool_day_data = self._fetch_pool_day_data(pool_address)
            self.cache.set(cache_key, "poolDayData", pool_day_data)
        
        if len(pool_day_data) < 2:
            return 0.0
        
        # Extract TVL values
        tvl_values = [float(d["tvlUSD"]) for d in pool_day_data]
        
        # Calculate standard deviation
        mean_tvl = np.mean(tvl_values)
        std_dev = np.std(tvl_values)
        
        if mean_tvl == 0:
            return 0.0
        
        # Return as percentage of mean
        return (std_dev / mean_tvl) * 100
    
    def _fetch_pool_day_data(self, pool_address: str) -> List[Dict[str, Any]]:
        """
        Fetch last 30 days of pool data.
        """
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
          }
        }
        """
        
        variables = {
            "pool_id": pool_address.lower(),
            "days": self.config["queries"]["pool_day_data_days"]
        }
        
        # This query doesn't need pagination (only 30 records)
        response = self.paginator._execute_with_retry(query, variables)
        
        return response.get("data", {}).get("poolDayDatas", [])
    
    def _generate_risk_flags(
        self,
        impact_100k: float,
        impact_1m: float,
        active_liquidity_pct: float,
        tvl_volatility: float
    ) -> List[str]:
        """
        Generate risk flags based on thresholds.
        """
        flags = []
        thresholds = self.config["risk_thresholds"]["liquidity_depth"]
        
        # Handle None values
        if impact_100k is None or impact_1m is None:
            return ["NO_DATA"]
        
        # Price impact checks
        if impact_100k > thresholds["price_impact_100k_critical_pct"]:
            flags.append("CRITICAL_SLIPPAGE_100K")
        elif impact_100k > thresholds["price_impact_100k_high_pct"]:
            flags.append("HIGH_SLIPPAGE_100K")
        
        if impact_1m > thresholds["price_impact_1m_critical_pct"]:
            flags.append("CRITICAL_SLIPPAGE_1M")
        elif impact_1m > thresholds["price_impact_1m_high_pct"]:
            flags.append("HIGH_SLIPPAGE_1M")
        
        # Active liquidity check
        if active_liquidity_pct is not None and active_liquidity_pct < thresholds["active_liquidity_low_pct"]:
            flags.append("LOW_ACTIVE_LIQUIDITY")
        
        # TVL volatility check
        if tvl_volatility is not None and tvl_volatility > thresholds["tvl_volatility_high_pct"]:
            flags.append("HIGH_TVL_VOLATILITY")
        
        return flags if flags else ["LOW_RISK"]
    
    def _calculate_risk_score(
        self,
        impact_100k: float,
        impact_1m: float,
        active_liquidity_pct: float,
        tvl_volatility: float
    ) -> int:
        """
        Calculate a 0-100 risk score for liquidity depth.
        """
        # Handle None values
        if impact_100k is None or impact_1m is None:
            return 100  # Max risk if no data
        
        # Normalize metrics to 0-100 scale
        impact_score = min((impact_100k + impact_1m) / 2 * 10, 100)  # Scale up
        inactive_liquidity_score = 100 - (active_liquidity_pct or 0)
        volatility_score = min((tvl_volatility or 0) * 2, 100)  # Scale up
        
        # Weighted average
        composite = (impact_score * 0.5) + (inactive_liquidity_score * 0.3) + (volatility_score * 0.2)
        
        return int(round(composite))
