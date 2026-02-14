"""
Token Resolver - DexScreener integration for pool/token resolution.
Identifies tokens from pool addresses and fetches market data.
"""

import time
from typing import Any, Dict, List, Optional
import httpx


class TokenResolver:
    """
    Resolves pool addresses to token information using DexScreener API.
    Also fetches market data (liquidity, volume, price changes).
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Configuration dict with token_intelligence settings
        """
        self.config = config
        ti_config = config.get("token_intelligence", {})
        self.base_url = ti_config.get("apis", {}).get(
            "dexscreener_url", "https://api.dexscreener.com/latest"
        )
        self.timeout = config.get("api", {}).get("timeout_seconds", 10)
    
    def resolve_pool(self, pool_address: str) -> Dict[str, Any]:
        """
        Resolve a pool address to its constituent tokens.
        
        Args:
            pool_address: The pool/pair contract address
            
        Returns:
            Dict with chain, dex, token0, token1 info, or error
        """
        url = f"{self.base_url}/dex/pairs/ethereum/{pool_address.lower()}"
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            pairs = data.get("pairs", [])
            if not pairs:
                # Try searching across all chains
                return self._search_pair_all_chains(pool_address)
            
            pair = pairs[0]
            return self._parse_pair_data(pair)
            
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error: {e.response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def _search_pair_all_chains(self, pool_address: str) -> Dict[str, Any]:
        """Search for pair across all supported chains."""
        chains = ["ethereum", "bsc", "polygon", "arbitrum", "optimism", "base", "avalanche"]
        
        for chain in chains:
            url = f"{self.base_url}/dex/pairs/{chain}/{pool_address.lower()}"
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url)
                    if response.status_code == 200:
                        data = response.json()
                        pairs = data.get("pairs", [])
                        if pairs:
                            return self._parse_pair_data(pairs[0])
                time.sleep(0.1)  # Rate limit
            except:
                continue
        
        return {"error": "Pool not found on any supported chain"}
    
    def _parse_pair_data(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """Parse DexScreener pair data into standardized format."""
        base_token = pair.get("baseToken", {})
        quote_token = pair.get("quoteToken", {})
        
        return {
            "chain": pair.get("chainId", "unknown"),
            "dex": pair.get("dexId", "unknown"),
            "pair_address": pair.get("pairAddress", ""),
            "token0": {
                "address": base_token.get("address", ""),
                "symbol": base_token.get("symbol", ""),
                "name": base_token.get("name", "")
            },
            "token1": {
                "address": quote_token.get("address", ""),
                "symbol": quote_token.get("symbol", ""),
                "name": quote_token.get("name", "")
            },
            "price_usd": float(pair.get("priceUsd", 0) or 0),
            "price_native": float(pair.get("priceNative", 0) or 0),
            "liquidity_usd": float(pair.get("liquidity", {}).get("usd", 0) or 0),
            "volume_24h": float(pair.get("volume", {}).get("h24", 0) or 0),
            "price_change_24h": float(pair.get("priceChange", {}).get("h24", 0) or 0),
            "txns_24h": {
                "buys": pair.get("txns", {}).get("h24", {}).get("buys", 0),
                "sells": pair.get("txns", {}).get("h24", {}).get("sells", 0)
            },
            "created_at": pair.get("pairCreatedAt"),
            "url": pair.get("url", "")
        }
    
    def get_token_pairs(self, token_address: str, chain: str = "ethereum") -> Dict[str, Any]:
        """
        Get all trading pairs for a specific token.
        
        Args:
            token_address: Token contract address
            chain: Blockchain name
            
        Returns:
            Dict with token info and all its pairs
        """
        url = f"{self.base_url}/dex/tokens/{token_address.lower()}"
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            pairs = data.get("pairs", [])
            if not pairs:
                return {"error": "No pairs found for token"}
            
            # Aggregate market data across all pairs
            total_liquidity = sum(float(p.get("liquidity", {}).get("usd", 0) or 0) for p in pairs)
            total_volume_24h = sum(float(p.get("volume", {}).get("h24", 0) or 0) for p in pairs)
            
            # Get token info from first pair
            first_pair = pairs[0]
            base_token = first_pair.get("baseToken", {})
            
            return {
                "token": {
                    "address": base_token.get("address", token_address),
                    "symbol": base_token.get("symbol", ""),
                    "name": base_token.get("name", "")
                },
                "pair_count": len(pairs),
                "total_liquidity_usd": total_liquidity,
                "total_volume_24h": total_volume_24h,
                "chains": list(set(p.get("chainId", "unknown") for p in pairs)),
                "dexes": list(set(p.get("dexId", "unknown") for p in pairs)),
                "top_pairs": [self._parse_pair_data(p) for p in pairs[:5]]
            }
            
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error: {e.response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_market_risk_flags(self, market_data: Dict[str, Any]) -> List[str]:
        """
        Generate risk flags based on market data.
        
        Args:
            market_data: Output from resolve_pool or get_token_pairs
            
        Returns:
            List of risk flag strings
        """
        flags = []
        thresholds = self.config.get("token_intelligence", {}).get("thresholds", {})
        
        min_liquidity = thresholds.get("min_liquidity_usd", 10000)
        
        liquidity = market_data.get("liquidity_usd", 0) or market_data.get("total_liquidity_usd", 0)
        
        if liquidity < min_liquidity:
            flags.append("LOW_LIQUIDITY")
        
        if liquidity < 1000:
            flags.append("EXTREMELY_LOW_LIQUIDITY")
        
        volume_24h = market_data.get("volume_24h", 0) or market_data.get("total_volume_24h", 0)
        if liquidity > 0 and volume_24h / liquidity > 10:
            flags.append("SUSPICIOUS_VOLUME_TO_LIQUIDITY")
        
        price_change = market_data.get("price_change_24h", 0)
        if abs(price_change) > 50:
            flags.append("HIGH_VOLATILITY")
        
        # Check pair age
        created_at = market_data.get("created_at")
        if created_at:
            try:
                from datetime import datetime, timezone
                created_ts = created_at / 1000 if created_at > 1e12 else created_at
                age_days = (datetime.now(timezone.utc).timestamp() - created_ts) / 86400
                if age_days < thresholds.get("suspicious_creation_days", 7):
                    flags.append("NEWLY_CREATED")
            except:
                pass
        
        return flags if flags else ["MARKET_OK"]
