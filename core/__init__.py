"""
Core modules for yums3

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

from .backend import StorageBackend, S3StorageBackend, LocalStorageBackend, FileTracker
from .config import YumConfig, create_storage_backend_from_config

__all__ = [
    'StorageBackend',
    'S3StorageBackend', 
    'LocalStorageBackend',
    'FileTracker',
    'YumConfig',
    'create_storage_backend_from_config'
]

class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    @staticmethod
    def error(msg):
        return f"{Colors.RED}{msg}{Colors.RESET}"
    
    @staticmethod
    def success(msg):
        return f"{Colors.GREEN}{msg}{Colors.RESET}"
    
    @staticmethod
    def warning(msg):
        return f"{Colors.YELLOW}{msg}{Colors.RESET}"
    
    @staticmethod
    def info(msg):
        return f"{Colors.BLUE}{msg}{Colors.RESET}"
    
    @staticmethod
    def bold(msg):
        return f"{Colors.BOLD}{msg}{Colors.RESET}"
