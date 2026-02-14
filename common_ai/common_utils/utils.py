"""
Utility functions for loading configuration and prompts.
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any


def load_prompts(yaml_path: str) -> Dict[str, Any]:
    """
    Load prompts and task configurations from YAML file.
    
    Args:
        yaml_path: Path to YAML file (relative or absolute)
        
    Returns:
        Dictionary containing prompts and configurations
        
    Raises:
        FileNotFoundError: If YAML file doesn't exist
        yaml.YAMLError: If YAML is malformed
    """
    yaml_file = Path(yaml_path)
    
    if not yaml_file.exists():
        raise FileNotFoundError(f"Prompts file not found: {yaml_path}")
    
    with open(yaml_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    return data


def load_config(json_path: str) -> Dict[str, Any]:
    """
    Load configuration from JSON file.
    
    Args:
        json_path: Path to JSON configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If JSON is malformed
    """
    config_file = Path(json_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {json_path}")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    return config


def to_json_safe(obj: Any) -> Any:
    """
    Convert Pydantic models and other objects to JSON-safe formats.
    
    Args:
        obj: Object to convert
        
    Returns:
        JSON-serializable version of the object
    """
    if hasattr(obj, 'model_dump'):
        return obj.model_dump()
    elif hasattr(obj, 'dict'):
        return obj.dict()
    return obj
