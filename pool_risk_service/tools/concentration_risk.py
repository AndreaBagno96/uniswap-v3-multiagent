"""
Concentration Risk Analyzer - Whale Analysis Module
Calculates Gini coefficient, HHI, Top 10 dominance, and LP age distribution.
"""

import numpy as np
from typing import Dict, Any, List
from utils import GraphPaginator, CacheManager


class ConcentrationRiskAnalyzer:
    """
    Analyzes concentration risk by examining LP distribution.
    Identifies systematic risk if top LPs exit.
    """
    
    def __init__(self, paginator: GraphPaginator, cache: CacheManager, config: Dict[str, Any]):
        """
        Args:
            paginator: GraphPaginator instance for fetching data
            cache: CacheManager instance (positions are not cached per config)
            config: Configuration dict
        """
        self.paginator = paginator
        self.cache = cache
        self.config = config
    
    def analyze(self, pool_address: str) -> Dict[str, Any]:
        """
        Perform concentration risk analysis on a pool.
        
        Args:
            pool_address: Ethereum address of the Uniswap V3 pool
            
        Returns:
            Dict containing raw metrics and risk flags
        """
        # Fetch all positions with liquidity > 0
        positions = self._fetch_positions(pool_address)
        
        if not positions:
            return {
                "error": "No positions found for this pool",
                "gini": None,
                "hhi": None,
                "top10_dominance_pct": None,
                "lp_age_distribution": None,
                "risk_flags": ["NO_DATA"]
            }
        
        # Extract liquidity values
        liquidity_values = [float(p["liquidity"]) for p in positions]
        total_liquidity = sum(liquidity_values)
        
        # Calculate metrics
        gini = self._calculate_gini(liquidity_values)
        hhi = self._calculate_hhi(liquidity_values, total_liquidity)
        top10_dominance = self._calculate_top_n_dominance(liquidity_values, total_liquidity, 10)
        lp_age_dist = self._calculate_lp_age_distribution(positions)
        
        # Generate risk flags
        risk_flags = self._generate_risk_flags(gini, hhi, top10_dominance, lp_age_dist)
        
        return {
            "gini_coefficient": round(gini, 4),
            "herfindahl_hirschman_index": round(hhi, 2),
            "top10_dominance_pct": round(top10_dominance, 2),
            "lp_age_distribution": lp_age_dist,
            "total_positions": len(positions),
            "risk_flags": risk_flags,
            "risk_score": self._calculate_risk_score(gini, hhi, top10_dominance)
        }
    
    def _fetch_positions(self, pool_address: str) -> List[Dict[str, Any]]:
        """
        Fetch all positions for a pool using pagination.
        """
        query = """
        query ($pool_id: String!, $last_id: ID!, $batch_size: Int!) {
          positions(
            first: $batch_size
            where: {
              pool: $pool_id
              liquidity_gt: "0"
              id_gt: $last_id
            }
            orderBy: id
            orderDirection: asc
          ) {
            id
            owner
            liquidity
            transaction {
              timestamp
            }
          }
        }
        """
        
        variables = {"pool_id": pool_address.lower()}
        
        return self.paginator.fetch_all(
            query_template=query,
            variables=variables,
            entity_name="positions"
        )
    
    def _calculate_gini(self, values: List[float]) -> float:
        """
        Calculate Gini coefficient (0 = perfect equality, 1 = perfect inequality).
        
        Args:
            values: List of liquidity values
            
        Returns:
            Gini coefficient
        """
        if not values:
            return 0.0
        
        # Sort values
        sorted_values = np.sort(values)
        n = len(sorted_values)
        
        # Calculate cumulative sum
        cumsum = np.cumsum(sorted_values)
        
        # Gini formula
        gini = (2 * np.sum((np.arange(1, n + 1)) * sorted_values)) / (n * cumsum[-1]) - (n + 1) / n
        
        return gini
    
    def _calculate_hhi(self, values: List[float], total: float) -> float:
        """
        Calculate Herfindahl-Hirschman Index (market concentration).
        HHI ranges from 0 to 10,000.
        < 1500: Competitive
        1500-2500: Moderate concentration
        > 2500: High concentration
        
        Args:
            values: List of liquidity values
            total: Total liquidity
            
        Returns:
            HHI score
        """
        if total == 0:
            return 0.0
        
        # Calculate market shares (as percentages)
        market_shares = [(v / total) * 100 for v in values]
        
        # HHI = sum of squared market shares
        hhi = sum(share ** 2 for share in market_shares)
        
        return hhi
    
    def _calculate_top_n_dominance(self, values: List[float], total: float, n: int) -> float:
        """
        Calculate percentage of total held by top N holders.
        
        Args:
            values: List of liquidity values
            total: Total liquidity
            n: Number of top holders to consider
            
        Returns:
            Percentage held by top N (0-100)
        """
        if total == 0:
            return 0.0
        
        # Sort descending and take top N
        sorted_values = sorted(values, reverse=True)
        top_n_sum = sum(sorted_values[:n])
        
        return (top_n_sum / total) * 100
    
    def _calculate_lp_age_distribution(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Classify LP positions by age (mercenary vs long-term).
        
        Args:
            positions: List of position dicts with transaction timestamps
            
        Returns:
            Dict with age distribution stats
        """
        import time
        
        current_time = int(time.time())
        
        mercenary_threshold = self.config["queries"]["lp_age_thresholds_days"]["mercenary"] * 86400
        long_term_threshold = self.config["queries"]["lp_age_thresholds_days"]["long_term"] * 86400
        
        mercenary_count = 0
        medium_count = 0
        long_term_count = 0
        mercenary_liquidity = 0.0
        medium_liquidity = 0.0
        long_term_liquidity = 0.0
        
        for pos in positions:
            age_seconds = current_time - int(pos["transaction"]["timestamp"])
            liquidity = float(pos["liquidity"])
            
            if age_seconds < mercenary_threshold:
                mercenary_count += 1
                mercenary_liquidity += liquidity
            elif age_seconds < long_term_threshold:
                medium_count += 1
                medium_liquidity += liquidity
            else:
                long_term_count += 1
                long_term_liquidity += liquidity
        
        total_liquidity = mercenary_liquidity + medium_liquidity + long_term_liquidity
        
        return {
            "mercenary": {
                "count": mercenary_count,
                "liquidity_pct": round((mercenary_liquidity / total_liquidity * 100) if total_liquidity > 0 else 0, 2)
            },
            "medium_term": {
                "count": medium_count,
                "liquidity_pct": round((medium_liquidity / total_liquidity * 100) if total_liquidity > 0 else 0, 2)
            },
            "long_term": {
                "count": long_term_count,
                "liquidity_pct": round((long_term_liquidity / total_liquidity * 100) if total_liquidity > 0 else 0, 2)
            }
        }
    
    def _generate_risk_flags(
        self,
        gini: float,
        hhi: float,
        top10_dominance: float,
        lp_age_dist: Dict[str, Any]
    ) -> List[str]:
        """
        Generate risk flags based on thresholds.
        """
        flags = []
        thresholds = self.config["risk_thresholds"]["concentration"]
        
        # Top 10 dominance checks
        if top10_dominance > thresholds["top10_dominance_critical_pct"]:
            flags.append("CRITICAL_TOP10_DOMINANCE")
        elif top10_dominance > thresholds["top10_dominance_high_risk_pct"]:
            flags.append("HIGH_TOP10_DOMINANCE")
        
        # Gini coefficient checks
        if gini > thresholds["gini_critical"]:
            flags.append("CRITICAL_GINI")
        elif gini > thresholds["gini_high_risk"]:
            flags.append("HIGH_GINI")
        
        # HHI checks
        if hhi > thresholds["hhi_critical"]:
            flags.append("CRITICAL_HHI")
        elif hhi > thresholds["hhi_high_risk"]:
            flags.append("HIGH_HHI")
        
        # Mercenary liquidity check
        if lp_age_dist["mercenary"]["liquidity_pct"] > 50:
            flags.append("HIGH_MERCENARY_LIQUIDITY")
        
        return flags if flags else ["LOW_RISK"]
    
    def _calculate_risk_score(self, gini: float, hhi: float, top10_dominance: float) -> int:
        """
        Calculate a 0-100 risk score for concentration.
        
        Args:
            gini: Gini coefficient (0-1)
            hhi: HHI score (0-10000)
            top10_dominance: Top 10 dominance percentage (0-100)
            
        Returns:
            Risk score 0-100
        """
        # Normalize each metric to 0-100 scale
        gini_score = gini * 100  # Already 0-1
        hhi_score = min((hhi / 10000) * 100, 100)  # Normalize to 0-100
        dominance_score = top10_dominance  # Already 0-100
        
        # Weighted average (equal weights)
        composite = (gini_score + hhi_score + dominance_score) / 3
        
        return int(round(composite))
