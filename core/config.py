"""
Configuration management for yums3

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import json
from typing import Any, Dict, List, Optional, Tuple


class YumConfig:
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
    DEFAULTS = {
        'backend.type': 's3',
        'repo.cache_dir': '~/yum-repo',
        'validation.enabled': True,
        'behavior.confirm': True,
        'behavior.backup': True,
    }
    
    # Legacy key mapping for backward compatibility
    LEGACY_KEY_MAP = {
        'storage_type': 'backend.type',
        's3_bucket': 'backend.s3.bucket',
        'aws_profile': 'backend.s3.profile',
        's3_endpoint_url': 'backend.s3.endpoint',
        'local_storage_path': 'backend.local.path',
        'local_repo_base': 'repo.cache_dir',
    }
    
    def __init__(self, config_file: Optional[str] = None, auto_migrate: bool = True):
        """Initialize configuration
        
        Args:
            config_file: Path to config file (if None, searches standard locations)
            auto_migrate: Automatically migrate legacy config format (default: True)
        """
        self.config_file = config_file or self._find_config_file()
        self.auto_migrate = auto_migrate
        self.data = {}
        self._load()
    
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
        
        # Check defaults
        if key in self.DEFAULTS:
            return self.DEFAULTS[key]
        
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
        return key in self.data or key in self.DEFAULTS
    
    def list_all(self) -> Dict[str, Any]:
        """Get all config key-value pairs including defaults
        
        Returns:
            Dictionary of all config values
        """
        result = dict(self.DEFAULTS)
        result.update(self.data)
        return result
    
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
        
        # Check defaults
        for key, value in self.DEFAULTS.items():
            if key not in result and (key.startswith(prefix_dot) or key == prefix):
                result[key] = value
        
        return result
    
    def validate(self) -> List[str]:
        """Validate configuration
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Check backend type
        backend_type = self.get('backend.type')
        if backend_type not in ['s3', 'local']:
            errors.append(f"Invalid backend.type: '{backend_type}' (must be 's3' or 'local')")
        
        # Check required keys per backend
        if backend_type == 's3':
            if not self.get('backend.s3.bucket'):
                errors.append("backend.s3.bucket is required for S3 backend")
        elif backend_type == 'local':
            if not self.get('backend.local.path'):
                errors.append("backend.local.path is required for local backend")
        
        # Validate cache_dir is set
        cache_dir = self.get('repo.cache_dir')
        if not cache_dir:
            errors.append("repo.cache_dir must be set")
        
        return errors
    
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
    
    def _load(self) -> None:
        """Load configuration from file"""
        if not os.path.exists(self.config_file):
            # No config file, use defaults
            return
        
        try:
            with open(self.config_file, 'r') as f:
                self.data = json.load(f)
            
            # Check if migration is needed
            if self.auto_migrate and self._needs_migration():
                self._migrate_legacy_config()
        
        except (json.JSONDecodeError, IOError) as e:
            raise ValueError(f"Failed to load config from {self.config_file}: {e}")
    
    def _needs_migration(self) -> bool:
        """Check if config contains legacy keys"""
        return any(key in self.data for key in self.LEGACY_KEY_MAP.keys())
    
    def _migrate_legacy_config(self) -> None:
        """Migrate legacy config format to new dot notation format"""
        migrated = {}
        
        # Migrate known legacy keys
        for old_key, new_key in self.LEGACY_KEY_MAP.items():
            if old_key in self.data:
                migrated[new_key] = self.data[old_key]
        
        # Keep any keys that are already in new format
        for key, value in self.data.items():
            if key not in self.LEGACY_KEY_MAP and '.' in key:
                migrated[key] = value
        
        # Update data and save
        self.data = migrated
        self.save()
    
    def _find_config_file(self) -> str:
        """Find config file in standard locations
        
        Searches in order:
        1. ./yums3.conf (current directory)
        2. ~/.yums3.conf (user home)
        3. /etc/yums3.conf (system-wide)
        
        Returns:
            Path to first existing config file, or ~/.yums3.conf as default
        """
        locations = [
            './yums3.conf',
            os.path.expanduser('~/.yums3.conf'),
            '/etc/yums3.conf'
        ]
        
        for location in locations:
            if os.path.exists(location):
                return location
        
        # Default to user config
        return os.path.expanduser('~/.yums3.conf')
    
    def __repr__(self) -> str:
        """String representation"""
        return f"YumConfig(file={self.config_file}, keys={len(self.data)})"
    
    def __str__(self) -> str:
        """Human-readable string"""
        lines = [f"Config file: {self.config_file}"]
        for key, value in sorted(self.list_all().items()):
            lines.append(f"  {key} = {value}")
        return '\n'.join(lines)


def create_storage_backend_from_config(config: YumConfig):
    """Create storage backend from configuration
    
    Args:
        config: YumConfig instance
    
    Returns:
        StorageBackend instance (S3StorageBackend or LocalStorageBackend)
    
    Raises:
        ValueError: If backend type is invalid or required config is missing
    """
    from .backend import S3StorageBackend, LocalStorageBackend
    
    backend_type = config.get('backend.type', 's3')
    
    if backend_type == 's3':
        bucket = config.get('backend.s3.bucket')
        if not bucket:
            raise ValueError("backend.s3.bucket is required for S3 backend")
        
        return S3StorageBackend(
            bucket_name=bucket,
            aws_profile=config.get('backend.s3.profile'),
            endpoint_url=config.get('backend.s3.endpoint')
        )
    
    elif backend_type == 'local':
        path = config.get('backend.local.path')
        if not path:
            raise ValueError("backend.local.path is required for local backend")
        
        return LocalStorageBackend(base_path=path)
    
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")
