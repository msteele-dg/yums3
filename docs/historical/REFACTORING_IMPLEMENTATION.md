# Refactoring Implementation Guide

## Overview
This document outlines the refactoring to eliminate duplication between `debs3.py` and `yums3.py`.

## Key Changes

### 1. Move YumRepo class to core/yum.py
- Extract entire `YumRepo` class from `yums3.py` 
- Add `REPO_TYPE = 'rpm'` class attribute
- Add `get_target_info(files)` method that returns `(el_version, arch, target_url)`
- Keep all existing methods intact

### 2. Move DebRepo class to core/deb.py
- Extract entire `DebRepo` class from `debs3.py`
- Add `REPO_TYPE = 'deb'` class attribute  
- Add `get_target_info(files)` method that returns `(distribution, component, arch, target_url)`
- Keep all existing methods intact

### 3. Create core/cli.py with generic main()
```python
def main(repo_type):
    """Generic main function for both RPM and DEB repos"""
    # Parse args (repo-specific subcommands)
    # Load config
    # Create repo instance
    # Show confirmation
    # Execute command
    # Handle errors
```

### 4. Update entry points
**yums3.py:**
```python
#!/usr/bin/env python3
from core.cli import main
import sys

if __name__ == '__main__':
    sys.exit(main('rpm'))
```

**debs3.py:**
```python
#!/usr/bin/env python3
from core.cli import main
import sys

if __name__ == '__main__':
    sys.exit(main('deb'))
```

### 5. Update core/__init__.py
```python
from core.yum import YumRepo
from core.deb import DebRepo

def create_repo_manager(config, repo_type):
    """Factory function to create appropriate repo manager"""
    if repo_type == 'rpm':
        return YumRepo(config)
    elif repo_type == 'deb':
        return DebRepo(config)
    else:
        raise ValueError(f"Unknown repo type: {repo_type}")
```

## Benefits
- Eliminates ~500 lines of duplicated code
- Single source of truth for CLI logic
- Easy to add new repo types
- Cleaner testing surface
- Maintains backward compatibility

## Migration Path
1. Create core/yum.py (copy YumRepo from yums3.py)
2. Create core/deb.py (copy DebRepo from debs3.py)
3. Create core/cli.py (extract common main() logic)
4. Update core/__init__.py
5. Replace yums3.py with thin wrapper
6. Replace debs3.py with thin wrapper
7. Run tests to verify
