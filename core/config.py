"""
Configuration management for yums3

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import json
from typing import Any, Dict, List, Optional, Tuple
from core.constants import (
    AVAIL_BACKEND_TYPES,
    DEFAULTS,
    RepoConfigFiles
)

def load_config(args, repo_type):
    if 'file' in args and args.file:
        config_file = args.file
    elif 'system' in args and args.system:
        config_file = RepoConfigFiles.SYSTEM
    elif 'local' in args and args.local:
        config_file = RepoConfigFiles.LOCAL
    else:  # --global or default
        locations = [
            RepoConfigFiles.LOCAL,
            RepoConfigFiles.USER,
            RepoConfigFiles.SYSTEM
        ]
        print(locations)
        for location in locations:
            if os.path.exists(location.value):
                config_file = location.value

    return RepoConfig(config_file, repo_type)


class RepoConfig:
    """Git-style configuration manager with dot notation
    
    Supports flat JSON structure with dot-notated keys for hierarchical organization.
    Example:
        {
            "backend.type": "s3",
            "backend.s3.bucket": "my-bucket",
            "repo.cache_dir": "/var/cache/yums3"
        }
    """
    
    # Default values

        
    def __init__(self, config_file: str, repo_type: str):
        """Initialize configuration
        
        Args:
            config_file: Path to config file (if None, searches standard locations)
        """
        self.repo_type = repo_type
        self.config_file = config_file
        self.data = self._load()
        self.track_defaults = []

        for k, v in DEFAULTS.items():
            if not self.has(k):
                self.set(k, v)
                self.track_defaults.append(k)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dot-notated key
        
        Args:
            key: Dot-notated key (e.g., 'backend.s3.bucket')
            default: Default value if key not found
        
        Returns:
            Config value or default
        """
        # Check actual config first
        if key in self.data:
            return self.data[key]

        return default
    
    def set(self, key: str, value: Any) -> None:
        """Set a config value by dot-notated key
        
        Args:
            key: Dot-notated key (e.g., 'backend.s3.bucket')
            value: Value to set
        """
        self.data[key] = value
    
    def unset(self, key: str) -> bool:
        """Remove a config key
        
        Args:
            key: Dot-notated key to remove
        
        Returns:
            True if key was removed, False if it didn't exist
        """
        if key in self.data:
            del self.data[key]
            return True
        return False
    
    def has(self, key: str) -> bool:
        """Check if a key exists in config
        
        Args:
            key: Dot-notated key to check
        
        Returns:
            True if key exists (in data or defaults)
        """
        return key in self.data
    
    def get_section(self, prefix: str) -> Dict[str, Any]:
        """Get all keys under a prefix
        
        Args:
            prefix: Key prefix (e.g., 'backend.s3')
        
        Returns:
            Dictionary of matching keys and values
        """
        prefix_dot = prefix + '.'
        result = {}
        
        # Check data
        for key, value in self.data.items():
            if key.startswith(prefix_dot) or key == prefix:
                result[key] = value
                
        return result
    
    def get_for_type(self, base_key: str, repo_type: str, default: Any = None) -> Any:
        """Get a config value with type-specific fallback
        
        Lookup order:
        1. Type-specific key (e.g., 'backend.rpm.s3.bucket')
        2. Shared key (e.g., 'backend.s3.bucket')
        3. Default value
        
        Args:
            base_key: Base key without type (e.g., 'backend.s3.bucket')
            repo_type: Repository type ('rpm' or 'deb')
            default: Default value if key not found
        
        Returns:
            Config value or default
        
        Example:
            # For RPM repos, checks 'backend.rpm.s3.bucket' then 'backend.s3.bucket'
            bucket = config.get_for_type('backend.s3.bucket', 'rpm')
        """
        # Parse the base key to insert type
        parts = base_key.split('.')
        if len(parts) >= 2:
            # Insert type after first component: backend.s3.bucket -> backend.rpm.s3.bucket
            type_specific_key = f"{parts[0]}.{repo_type}.{'.'.join(parts[1:])}"
        else:
            # Fallback for simple keys
            type_specific_key = f"{repo_type}.{base_key}"
        
        # Try type-specific key first
        value = self.get(type_specific_key)
        if value is not None:
            return value
        
        # Fall back to shared key
        value = self.get(base_key)
        if value is not None:
            return value
        
        # Return default
        return default
    
    def save(self, config_file: Optional[str] = None) -> None:
        """Save configuration to file
        
        Args:
            config_file: Path to save to (if None, uses self.config_file)
        """
        target_file = config_file or self.config_file
        
        # Create directory if needed
        config_dir = os.path.dirname(target_file)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        
        # Write sorted JSON for readability
        with open(target_file, 'w') as f:
            json.dump(self.data, f, indent=2, sort_keys=True)
    
    def _load(self) -> dict:
        """Load configuration from file"""
        if not os.path.exists(self.config_file):
            # No config file, use defaults
            return {}
        
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            raise ValueError(f"Failed to load config from {self.config_file}: {e}")
    
    def __repr__(self) -> str:
        """String representation"""
        return f"RepoConfig(file={self.config_file}, keys={len(self.data)})"
    
    def __str__(self) -> str:
        """Human-readable string"""
        lines = [f"Config file: {self.config_file}"]
        for key, value in sorted(self.data.items()):
            lines.append(f"  {key} = {value}")
        return '\n'.join(lines)
