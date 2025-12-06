# Project Organization

This document describes the current organization of the yums3 project.

**Last Updated:** November 2024

## Quick Links

- [Architecture Documentation](ARCHITECTURE.md) - System design and architecture
- [User Guide](USER_GUIDE.md) - Complete user documentation
- [Developer Guide](DEVELOPER_GUIDE.md) - For contributors
- [Configuration Reference](CONFIG_COMMAND_REFERENCE.md) - Config command details
- [CLI Migration Guide](CLI_MIGRATION_GUIDE.md) - Migrating to new CLI

## Directory Structure

```
yums3/
├── core/                    # Core modules
│   ├── __init__.py         # Module exports and Colors class
│   ├── backend.py          # Storage backend abstraction (S3/Local)
│   ├── config.py           # Configuration management (RepoConfig)
│   └── sqlite_metadata.py  # SQLite database generation
│
├── tests/                   # Test suite
│   ├── test_config.py                # RepoConfig unit tests
│   ├── test_config_command.py        # Config command integration tests
│   ├── test_storage_backend.py       # Storage backend tests
│   ├── test_sqlite_integration.py    # SQLite database tests
│   ├── test_dnf_compatibility.py     # DNF compatibility tests
│   ├── test_actual_merge.py          # Metadata merge tests
│   └── test_yums3_merge.py           # Integration tests
│
├── docs/                    # Documentation
│   ├── CONFIG_COMMAND_REFERENCE.md   # Config command quick reference
│   ├── REPOCONFIG_COMPLETE.md        # Complete RepoConfig documentation
│   ├── DOT_NOTATION_CONFIG_DESIGN.md # Configuration design document
│   ├── STORAGE_BACKEND_INTEGRATION.md # Storage backend details
│   ├── PHASE1_CONFIG_COMPLETE.md     # Phase 1 completion summary
│   ├── BUGFIX_SUMMARY.md             # Bug fixes documentation
│   ├── FINAL_SUMMARY.md              # Project summary
│   ├── VALIDATION_REFACTOR_COMPLETE.md # Validation refactor
│   ├── VALIDATION_REFACTOR_PLAN.md   # Validation planning
│   ├── STORAGE_BACKEND_REFACTOR.md   # Backend refactor docs
│   ├── LXML_MIGRATION.md             # lxml migration notes
│   ├── DNF_COMPATIBILITY_FIX.md      # DNF compatibility fixes
│   ├── CONFIG_ANALYSIS.md            # Configuration analysis
│   ├── HOWTO_COMPARE_REPOS.md        # Repository comparison guide
│   └── PROJECT_ORGANIZATION.md       # This file
│
├── test_rpms/              # Test RPM packages
│   ├── README.md
│   ├── build_test_rpms.sh
│   ├── hello-world-1.0.0-1.el9.x86_64.rpm
│   └── goodbye-forever-2.0.0-1.el9.x86_64.rpm
│
├── yums3.py                # Main script
├── README.md               # Project README
├── LICENSE                 # MIT License
│
├── fix_corrupted_repo.py   # Utility: Fix corrupted repositories
├── regenerate_sqlite_dbs.py # Utility: Regenerate SQLite databases
├── validate_repo_structure.py # Utility: Validate repository structure
│
├── yums3.conf.example      # Example configuration file
├── yums3.conf.local.example # Example local configuration
├── yums3_compare.conf      # Configuration for comparison tests
└── yums3_merge_test.conf   # Configuration for merge tests
```

## Module Organization

### Core Modules (`core/`)

**`backend.py`** - Storage backend abstraction
- `StorageBackend` - Abstract base class
- `S3StorageBackend` - S3 implementation
- `LocalStorageBackend` - Local filesystem implementation
- `FileTracker` - Track file operations for rollback

**`config.py`** - Configuration management
- `RepoConfig` - Git-style configuration with dot notation
- `create_storage_backend_from_config()` - Factory function
- Automatic legacy config migration
- Configuration validation

**`sqlite_metadata.py`** - SQLite database generation
- `SQLiteMetadataManager` - Generate SQLite databases from XML
- Support for primary, filelists, and other databases
- Schema validation

**`__init__.py`** - Module exports
- Exports all public classes and functions
- `Colors` class for terminal output

### Test Suite (`tests/`)

All test files have been moved to the `tests/` directory and updated to reference the parent directory for imports.

**Configuration Tests:**
- `test_config.py` - Unit tests for RepoConfig class
- `test_config_command.py` - Integration tests for config command

**Storage Tests:**
- `test_storage_backend.py` - Storage backend tests
- `test_sqlite_integration.py` - SQLite database tests

**Integration Tests:**
- `test_dnf_compatibility.py` - DNF compatibility tests
- `test_actual_merge.py` - Metadata merge tests
- `test_yums3_merge.py` - Full integration tests
- `test_cli_commands.py` - CLI command tests

### Documentation (`docs/`)

All documentation files (except README.md) have been moved to the `docs/` directory.

**Configuration Documentation:**
- `CONFIG_COMMAND_REFERENCE.md` - Quick reference for config command
- `REPOCONFIG_COMPLETE.md` - Complete configuration documentation
- `DOT_NOTATION_CONFIG_DESIGN.md` - Design document

**Technical Documentation:**
- `STORAGE_BACKEND_INTEGRATION.md` - Storage backend details
- `VALIDATION_REFACTOR_COMPLETE.md` - Validation system
- `LXML_MIGRATION.md` - XML library migration

**Project History:**
- `PHASE1_CONFIG_COMPLETE.md` - Phase 1 completion
- `BUGFIX_SUMMARY.md` - Bug fixes
- `FINAL_SUMMARY.md` - Project summary
- `CLI_MIGRATION_GUIDE.md` - CLI migration guide

## Running Tests

All tests can be run from the project root:

```bash
# Configuration tests
python3 tests/test_config.py
python3 tests/test_config_command.py

# Storage tests
python3 tests/test_storage_backend.py
python3 tests/test_sqlite_integration.py

# Integration tests
python3 tests/test_dnf_compatibility.py
python3 tests/test_actual_merge.py
python3 tests/test_yums3_merge.py
```

## Import Paths

After reorganization, imports work as follows:

**From main script (`yums3.py`):**
```python
from core.backend import S3StorageBackend, LocalStorageBackend
from core.config import RepoConfig, create_storage_backend_from_config
from core.sqlite_metadata import SQLiteMetadataManager
from core import Colors
```

**From tests (`tests/*.py`):**
```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.config import RepoConfig
from core.backend import LocalStorageBackend
```

## Configuration Files

**User Configuration:**
- `~/.yums3.conf` - User-specific configuration
- `./yums3.conf` - Project-specific configuration
- `/etc/yums3.conf` - System-wide configuration

**Example Configurations:**
- `yums3.conf.example` - Example S3 configuration
- `yums3.conf.local.example` - Example local configuration
- `yums3_compare.conf` - Configuration for comparison tests
- `yums3_merge_test.conf` - Configuration for merge tests

## Utilities

**`fix_corrupted_repo.py`** - Fix corrupted repositories
- Restore from backups
- Rebuild metadata

**`regenerate_sqlite_dbs.py`** - Regenerate SQLite databases
- Rebuild SQLite databases from XML
- Useful after manual metadata edits

**`validate_repo_structure.py`** - Validate repository structure
- Check metadata integrity
- Verify package consistency

## Benefits of This Organization

1. **Clear Separation**: Core code, tests, and docs are clearly separated
2. **Easy Navigation**: Related files are grouped together
3. **Maintainability**: Easy to find and update specific components
4. **Testing**: All tests in one place, easy to run
5. **Documentation**: All docs in one place, easy to reference
6. **Scalability**: Easy to add new modules, tests, or docs

## Migration Notes

When moving files:
- Test files updated to use `os.path.dirname(os.path.dirname(__file__))` for parent directory
- Import paths updated to use `core.` prefix
- All tests verified to work from new locations
- README updated to reflect new structure
