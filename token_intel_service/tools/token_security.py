"""
Token Security Analyzer - GoPlus integration for smart contract security checks.
Detects honeypots, malicious functions, and other security risks.
"""

from typing import Any, Dict, List
import httpx


class TokenSecurityAnalyzer:
    """
    Analyzes token smart contracts for security risks using GoPlus API.
    Checks for honeypots, proxy contracts, mint functions, tax rates, etc.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Configuration dict with token_intelligence settings
        """
        self.config = config
        ti_config = config.get("token_intelligence", {})
        self.base_url = ti_config.get("apis", {}).get(
            "goplus_url", "https://api.gopluslabs.io/api/v1"
        )
        self.chain_mapping = ti_config.get("chain_mapping", {
            "ethereum": "1",
            "bsc": "56",
            "polygon": "137",
            "arbitrum": "42161",
            "optimism": "10",
            "base": "8453"
        })
        self.thresholds = ti_config.get("thresholds", {})
        self.timeout = config.get("api", {}).get("timeout_seconds", 10)
    
    def analyze(self, chain: str, token_address: str) -> Dict[str, Any]:
        """
        Perform comprehensive security analysis on a token.
        
        Args:
            chain: Blockchain name (e.g., "ethereum", "bsc")
            token_address: Token contract address
            
        Returns:
            Dict with security metrics, risk_score, and flags
        """
        chain_id = self._resolve_chain_id(chain)
        if not chain_id:
            return {"error": f"Unsupported chain: {chain}", "risk_score": 100}
        
        url = f"{self.base_url}/token_security/{chain_id}"
        params = {"contract_addresses": token_address.lower()}
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            
            if data.get("code") != 1:
                return {"error": data.get("message", "API error"), "risk_score": 50}
            
            result = data.get("result", {})
            token_data = result.get(token_address.lower(), {})
            
            if not token_data:
                return {"error": "Token not found in GoPlus", "risk_score": 50}
            
            return self._parse_security_data(token_data)
            
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error: {e.response.status_code}", "risk_score": 50}
        except Exception as e:
            return {"error": str(e), "risk_score": 50}
    
    def _resolve_chain_id(self, chain: str) -> str | None:
        """Convert chain name to chain ID."""
        chain_lower = chain.lower()
        
        # Direct chain ID
        if chain_lower.isdigit():
            return chain_lower
        
        return self.chain_mapping.get(chain_lower)
    
    def _parse_security_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse GoPlus response into standardized security analysis."""
        
        # Extract boolean flags (GoPlus uses "0"/"1" strings)
        def to_bool(val) -> bool:
            return str(val) == "1"
        
        def to_float(val) -> float:
            try:
                return float(val) if val else 0.0
            except:
                return 0.0
        
        # Core security checks
        is_honeypot = to_bool(data.get("is_honeypot"))
        is_proxy = to_bool(data.get("is_proxy"))
        is_mintable = to_bool(data.get("is_mintable"))
        can_take_back_ownership = to_bool(data.get("can_take_back_ownership"))
        owner_change_balance = to_bool(data.get("owner_change_balance"))
        hidden_owner = to_bool(data.get("hidden_owner"))
        selfdestruct = to_bool(data.get("selfdestruct"))
        external_call = to_bool(data.get("external_call"))
        is_blacklisted = to_bool(data.get("is_blacklisted"))
        is_whitelisted = to_bool(data.get("is_whitelisted"))
        anti_whale_modifiable = to_bool(data.get("anti_whale_modifiable"))
        trading_cooldown = to_bool(data.get("trading_cooldown"))
        transfer_pausable = to_bool(data.get("transfer_pausable"))
        is_open_source = to_bool(data.get("is_open_source"))
        
        # Tax rates
        buy_tax = to_float(data.get("buy_tax"))
        sell_tax = to_float(data.get("sell_tax"))
        
        # Holder info
        holder_count = int(data.get("holder_count", 0) or 0)
        total_supply = to_float(data.get("total_supply"))
        
        # Owner info
        owner_address = data.get("owner_address", "")
        owner_balance = to_float(data.get("owner_balance"))
        owner_percent = to_float(data.get("owner_percent"))
        creator_address = data.get("creator_address", "")
        creator_balance = to_float(data.get("creator_balance"))
        creator_percent = to_float(data.get("creator_percent"))
        
        # LP info
        lp_holder_count = int(data.get("lp_holder_count", 0) or 0)
        lp_total_supply = to_float(data.get("lp_total_supply"))
        
        # Calculate risk score
        risk_score, risk_flags = self._calculate_risk(
            is_honeypot=is_honeypot,
            is_proxy=is_proxy,
            is_mintable=is_mintable,
            can_take_back_ownership=can_take_back_ownership,
            owner_change_balance=owner_change_balance,
            hidden_owner=hidden_owner,
            selfdestruct=selfdestruct,
            buy_tax=buy_tax,
            sell_tax=sell_tax,
            holder_count=holder_count,
            owner_percent=owner_percent,
            creator_percent=creator_percent,
            is_open_source=is_open_source,
            transfer_pausable=transfer_pausable
        )
        
        return {
            "token_name": data.get("token_name", ""),
            "token_symbol": data.get("token_symbol", ""),
            "is_honeypot": is_honeypot,
            "is_proxy": is_proxy,
            "is_mintable": is_mintable,
            "is_open_source": is_open_source,
            "can_take_back_ownership": can_take_back_ownership,
            "owner_change_balance": owner_change_balance,
            "hidden_owner": hidden_owner,
            "selfdestruct": selfdestruct,
            "external_call": external_call,
            "transfer_pausable": transfer_pausable,
            "is_blacklisted": is_blacklisted,
            "is_whitelisted": is_whitelisted,
            "anti_whale_modifiable": anti_whale_modifiable,
            "trading_cooldown": trading_cooldown,
            "buy_tax_pct": buy_tax * 100,
            "sell_tax_pct": sell_tax * 100,
            "holder_count": holder_count,
            "owner_address": owner_address,
            "owner_percent": owner_percent * 100,
            "creator_address": creator_address,
            "creator_percent": creator_percent * 100,
            "lp_holder_count": lp_holder_count,
            "risk_score": risk_score,
            "risk_flags": risk_flags,
            "is_dangerous": risk_score >= 70
        }
    
    def _calculate_risk(
        self,
        is_honeypot: bool,
        is_proxy: bool,
        is_mintable: bool,
        can_take_back_ownership: bool,
        owner_change_balance: bool,
        hidden_owner: bool,
        selfdestruct: bool,
        buy_tax: float,
        sell_tax: float,
        holder_count: int,
        owner_percent: float,
        creator_percent: float,
        is_open_source: bool,
        transfer_pausable: bool
    ) -> tuple[int, List[str]]:
        """Calculate security risk score and generate flags."""
        score = 0
        flags = []
        
        # Critical flags (immediate danger)
        if is_honeypot:
            score += 50
            flags.append("HONEYPOT_DETECTED")
        
        if selfdestruct:
            score += 30
            flags.append("SELFDESTRUCT_FUNCTION")
        
        if owner_change_balance:
            score += 25
            flags.append("OWNER_CAN_MODIFY_BALANCE")
        
        # High risk flags
        if is_mintable:
            score += 15
            flags.append("MINTABLE_TOKEN")
        
        if can_take_back_ownership:
            score += 15
            flags.append("OWNERSHIP_RECOVERABLE")
        
        if hidden_owner:
            score += 15
            flags.append("HIDDEN_OWNER")
        
        if transfer_pausable:
            score += 10
            flags.append("TRANSFER_PAUSABLE")
        
        # Medium risk flags
        if is_proxy:
            score += 10
            flags.append("PROXY_CONTRACT")
        
        if not is_open_source:
            score += 10
            flags.append("NOT_OPEN_SOURCE")
        
        # Tax analysis
        max_tax = self.thresholds.get("max_tax_pct", 10) / 100
        if buy_tax > max_tax or sell_tax > max_tax:
            score += 15
            flags.append(f"HIGH_TAX_RATE")
        
        if sell_tax > buy_tax * 2:
            score += 10
            flags.append("SELL_TAX_HIGHER_THAN_BUY")
        
        # Holder analysis
        min_holders = self.thresholds.get("min_holder_count", 100)
        if holder_count < min_holders:
            score += 10
            flags.append("LOW_HOLDER_COUNT")
        
        # Ownership concentration
        max_owner_pct = self.thresholds.get("max_owner_balance_pct", 50) / 100
        if owner_percent > max_owner_pct or creator_percent > max_owner_pct:
            score += 15
            flags.append("HIGH_OWNER_CONCENTRATION")
        
        # Cap at 100
        score = min(100, score)
        
        if not flags:
            flags.append("SECURITY_OK")
        
        return score, flags
