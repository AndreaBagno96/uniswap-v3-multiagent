"""
Core utilities for querying The Graph with pagination and caching.
Follows KISS, DRY, and Separation of Concerns principles.
"""

import time
import json
import os
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import requests


class GraphPaginator:
    """
    Generic ID-based pagination for The Graph queries.
    Handles rate limiting and automatic retrying.
    """
    
    def __init__(self, endpoint: str, config: Dict[str, Any]):
        """
        Args:
            endpoint: The Graph API endpoint URL
            config: Configuration dict containing pagination settings
        """
        self.endpoint = endpoint
        self.batch_size = config["pagination"]["batch_size"]
        self.rate_limit_delay = config["pagination"]["rate_limit_delay_seconds"]
        self.max_retries = config["pagination"]["max_retries"]
        self.retry_delay = config["pagination"]["retry_delay_seconds"]
        self.timeout = config["api"]["timeout_seconds"]
    
    def fetch_all(
        self,
        query_template: str,
        variables: Dict[str, Any],
        entity_name: str,
        id_field: str = "id"
    ) -> List[Dict[str, Any]]:
        """
        Fetch all entities using ID-based pagination.
        
        Args:
            query_template: GraphQL query with $last_id variable placeholder
            variables: Query variables (pool address, etc.)
            entity_name: Name of the entity in the GraphQL response
            id_field: Field name to use for pagination (default: "id")
            
        Returns:
            List of all fetched entities
        """
        all_entities = []
        last_id = ""
        
        while True:
            # Prepare variables for this batch
            batch_vars = {**variables, "last_id": last_id, "batch_size": self.batch_size}
            
            # Execute query with retry logic
            response_data = self._execute_with_retry(query_template, batch_vars)
            
            # Extract entities from response
            entities = response_data.get("data", {}).get(entity_name, [])
            
            if not entities:
                break
            
            all_entities.extend(entities)
            
            # Update last_id for next iteration
            last_id = entities[-1][id_field]
            
            # Check if we got fewer results than batch size (indicates last page)
            if len(entities) < self.batch_size:
                break
            
            # Rate limiting delay
            time.sleep(self.rate_limit_delay)
        
        return all_entities
    
    def _execute_with_retry(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a GraphQL query with automatic retry on failure.
        
        Args:
            query: GraphQL query string
            variables: Query variables
            
        Returns:
            Response data dict
            
        Raises:
            Exception: If all retries fail (fail-fast principle)
        """
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.endpoint,
                    json={"query": query, "variables": variables},
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Check for GraphQL errors
                if "errors" in data:
                    raise Exception(f"GraphQL errors: {data['errors']}")
                
                return data
                
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    # Last attempt failed - let it propagate (fail-fast)
                    raise Exception(f"Query failed after {self.max_retries} retries: {str(e)}")
                
                # Wait before retry
                time.sleep(self.retry_delay * (attempt + 1))
        
        # Should never reach here, but satisfy type checker
        raise Exception("Unexpected error in retry logic")


class CacheManager:
    """
    Hybrid caching strategy for static vs dynamic data.
    Static data (ticks, poolDayData): 1 hour TTL
    Dynamic data (swaps, positions): Never cached
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Configuration dict containing cache settings
        """
        self.enabled = config["cache"]["enabled"]
        self.cache_dir = config["cache"]["directory"]
        self.static_ttl = config["cache"]["static_data_ttl_seconds"]
        self.cache_entities = config["cache"]["cache_entities"]
        
        # Create cache directory if it doesn't exist
        if self.enabled and not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def get(self, key: str, entity_type: str) -> Optional[Any]:
        """
        Retrieve cached data if available and not expired.
        
        Args:
            key: Unique cache key (e.g., pool_address + entity_type)
            entity_type: Type of entity (ticks, poolDayData, etc.)
            
        Returns:
            Cached data or None if not found/expired
        """
        if not self.enabled or not self.cache_entities.get(entity_type, False):
            return None
        
        cache_file = self._get_cache_path(key)
        
        if not os.path.exists(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check expiration
            cached_at = datetime.fromisoformat(cache_data["cached_at"])
            if datetime.now() - cached_at > timedelta(seconds=self.static_ttl):
                # Expired - remove file
                os.remove(cache_file)
                return None
            
            return cache_data["data"]
            
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupted cache - remove it (fail-fast)
            if os.path.exists(cache_file):
                os.remove(cache_file)
            return None
    
    def set(self, key: str, entity_type: str, data: Any) -> None:
        """
        Store data in cache.
        
        Args:
            key: Unique cache key
            entity_type: Type of entity
            data: Data to cache
        """
        if not self.enabled or not self.cache_entities.get(entity_type, False):
            return
        
        cache_file = self._get_cache_path(key)
        
        cache_data = {
            "cached_at": datetime.now().isoformat(),
            "entity_type": entity_type,
            "data": data
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)
    
    def _get_cache_path(self, key: str) -> str:
        """
        Generate a filesystem-safe cache file path.
        
        Args:
            key: Cache key
            
        Returns:
            Full path to cache file
        """
        # Hash the key to create a safe filename
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{key_hash}.json")


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """
    Load configuration from JSON file.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dict
        
    Raises:
        Exception: If config file is missing or invalid (fail-fast)
    """
    if not os.path.exists(config_path):
        raise Exception(f"Configuration file not found: {config_path}")
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Validate required keys exist
        required_keys = ["api", "pagination", "cache", "queries", "risk_thresholds", "scoring"]
        for key in required_keys:
            if key not in config:
                raise Exception(f"Missing required configuration section: {key}")
        
        return config
        
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in config file: {str(e)}")
