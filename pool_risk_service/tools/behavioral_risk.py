"""
Behavioral Risk Analyzer - Wash Trading & MEV Detection
Detects inorganic volume and predatory bot activity.
"""

from typing import Dict, Any, List, Set
from collections import defaultdict
from utils import GraphPaginator, CacheManager


class BehavioralRiskAnalyzer:
    """
    Analyzes swap patterns to detect wash trading and MEV exploitation.
    Always fetches fresh data (no caching).
    """
    
    def __init__(self, paginator: GraphPaginator, cache: CacheManager, config: Dict[str, Any]):
        """
        Args:
            paginator: GraphPaginator instance for fetching data
            cache: CacheManager instance (not used for swaps per config)
            config: Configuration dict
        """
        self.paginator = paginator
        self.cache = cache
        self.config = config
    
    def analyze(self, pool_address: str) -> Dict[str, Any]:
        """
        Perform behavioral risk analysis on a pool.
        
        Args:
            pool_address: Ethereum address of the Uniswap V3 pool
            
        Returns:
            Dict containing raw metrics and risk flags
        """
        # Fetch last N swaps (fresh, no cache)
        swaps = self._fetch_recent_swaps(pool_address)
        
        if not swaps:
            return {
                "error": "No swap data found for this pool",
                "wash_trading_pct": None,
                "mev_exposure_pct": None,
                "suspicious_patterns": [],
                "risk_flags": ["NO_DATA"]
            }
        
        # Detect wash trading
        wash_trading_pct, wash_patterns = self._detect_wash_trading(swaps)
        
        # Detect sandwich attacks (MEV)
        mev_exposure_pct, sandwich_victims = self._detect_sandwich_attacks(swaps)
        
        # Generate risk flags
        risk_flags = self._generate_risk_flags(wash_trading_pct, mev_exposure_pct)
        
        return {
            "wash_trading_pct": round(wash_trading_pct, 2),
            "mev_exposure_pct": round(mev_exposure_pct, 2),
            "total_swaps_analyzed": len(swaps),
            "wash_trading_patterns": len(wash_patterns),
            "sandwich_victims": len(sandwich_victims),
            "suspicious_patterns": wash_patterns[:10],  # Top 10 for reporting
            "risk_flags": risk_flags,
            "risk_score": self._calculate_risk_score(wash_trading_pct, mev_exposure_pct)
        }
    
    def _fetch_recent_swaps(self, pool_address: str) -> List[Dict[str, Any]]:
        """
        Fetch last N swaps (configurable, default 2000).
        Always fresh - no caching.
        """
        swap_limit = self.config["queries"]["swap_limit"]
        
        query = """
        query ($pool_id: String!, $last_id: ID!, $batch_size: Int!) {
          swaps(
            first: $batch_size
            where: {
              pool: $pool_id
              id_gt: $last_id
            }
            orderBy: timestamp
            orderDirection: desc
          ) {
            id
            timestamp
            sender
            recipient
            origin
            amount0
            amount1
            amountUSD
            transaction {
              id
              blockNumber
            }
          }
        }
        """
        
        variables = {"pool_id": pool_address.lower()}
        
        # Fetch up to swap_limit swaps
        all_swaps = self.paginator.fetch_all(
            query_template=query,
            variables=variables,
            entity_name="swaps"
        )
        
        # Limit to configured amount
        return all_swaps[:swap_limit]
    
    def _detect_wash_trading(self, swaps: List[Dict[str, Any]]) -> tuple[float, List[Dict[str, Any]]]:
        """
        Detect wash trading patterns (circular flows A→B→A).
        
        Args:
            swaps: List of swap transactions
            
        Returns:
            Tuple of (wash_trading_percentage, list_of_patterns)
        """
        # Group swaps by block
        swaps_by_block = defaultdict(list)
        for swap in swaps:
            block = swap["transaction"]["blockNumber"]
            swaps_by_block[block].append(swap)
        
        suspicious_patterns = []
        suspicious_swap_count = 0
        
        # Analyze each block for circular patterns
        for block, block_swaps in swaps_by_block.items():
            if len(block_swaps) < 2:
                continue
            
            # Track sender-recipient flows
            flows = defaultdict(list)
            for swap in block_swaps:
                sender = swap["sender"]
                recipient = swap["recipient"]
                flows[sender].append(recipient)
            
            # Detect circular patterns
            for sender, recipients in flows.items():
                for recipient in recipients:
                    # Check if recipient also sends back to sender
                    if sender in flows.get(recipient, []):
                        suspicious_patterns.append({
                            "block": block,
                            "addresses": [sender, recipient],
                            "pattern": "circular"
                        })
                        suspicious_swap_count += 2  # Both swaps are suspicious
        
        if not swaps:
            return 0.0, []
        
        wash_trading_pct = (suspicious_swap_count / len(swaps)) * 100
        
        return wash_trading_pct, suspicious_patterns
    
    def _detect_sandwich_attacks(self, swaps: List[Dict[str, Any]]) -> tuple[float, List[str]]:
        """
        Detect sandwich attack victims.
        Pattern: Same attacker (origin) with swaps before and after victim's swap in same block.
        
        Args:
            swaps: List of swap transactions
            
        Returns:
            Tuple of (mev_exposure_percentage, list_of_victim_tx_ids)
        """
        # Group swaps by block
        swaps_by_block = defaultdict(list)
        for swap in swaps:
            block = swap["transaction"]["blockNumber"]
            swaps_by_block[block].append(swap)
        
        sandwich_victims: Set[str] = set()
        
        # Analyze each block
        for block, block_swaps in swaps_by_block.items():
            if len(block_swaps) < 3:
                continue
            
            # Sort by transaction ID (represents order within block)
            sorted_swaps = sorted(block_swaps, key=lambda s: s["id"])
            
            # Look for sandwich pattern: same origin appears before and after different txs
            for i in range(len(sorted_swaps) - 2):
                swap_before = sorted_swaps[i]
                middle_swap = sorted_swaps[i + 1]
                swap_after = sorted_swaps[i + 2]
                
                # Check if first and last swap have same origin (attacker)
                # and middle swap has different origin (victim)
                if (swap_before["origin"] == swap_after["origin"] and
                    middle_swap["origin"] != swap_before["origin"]):
                    sandwich_victims.add(middle_swap["transaction"]["id"])
        
        if not swaps:
            return 0.0, []
        
        # Count unique victim transactions
        mev_exposure_pct = (len(sandwich_victims) / len(swaps)) * 100
        
        return mev_exposure_pct, list(sandwich_victims)
    
    def _generate_risk_flags(self, wash_trading_pct: float, mev_exposure_pct: float) -> List[str]:
        """
        Generate risk flags based on thresholds.
        """
        flags = []
        thresholds = self.config["risk_thresholds"]["behavioral"]
        
        # Wash trading checks
        if wash_trading_pct > thresholds["wash_trading_critical_pct"]:
            flags.append("CRITICAL_WASH_TRADING")
        elif wash_trading_pct > thresholds["wash_trading_high_pct"]:
            flags.append("HIGH_WASH_TRADING")
        
        # MEV exposure checks
        if mev_exposure_pct > thresholds["mev_exposure_critical_pct"]:
            flags.append("CRITICAL_MEV_EXPOSURE")
        elif mev_exposure_pct > thresholds["mev_exposure_high_pct"]:
            flags.append("HIGH_MEV_EXPOSURE")
        
        return flags if flags else ["LOW_RISK"]
    
    def _calculate_risk_score(self, wash_trading_pct: float, mev_exposure_pct: float) -> int:
        """
        Calculate a 0-100 risk score for behavioral risk.
        
        Args:
            wash_trading_pct: Percentage of wash trading
            mev_exposure_pct: Percentage of MEV exposure
            
        Returns:
            Risk score 0-100
        """
        # Both metrics are already 0-100 percentages
        # Weight them equally
        composite = (wash_trading_pct + mev_exposure_pct) / 2
        
        return int(round(min(composite, 100)))
