# Refactoring Steps: Detailed Implementation Guide

## Overview
This document provides step-by-step instructions to complete the refactoring.

## Step 1: Create core/yum.py

### Extract from yums3.py
1. Copy lines 1-33 (imports and lxml check)
2. Copy lines 35-1200 (entire YumRepo class)
3. Add `REPO_TYPE = 'rpm'` as class attribute after `__init__`

### File structure:
```python
"""
YUM repository manager

Copyright (c) 2025 Deepgram
...
"""

import os
import subprocess
import re
import gzip
import hashlib
from datetime import datetime
import bz2

from core.backend import create_storage_backend
from core.config import RepoConfig
from core.sqlite_metadata import SQLiteMetadataManager
from core import Colors

try:
    from lxml import etree as ET
except ImportError:
    print("ERROR: lxml is not installed. Install it with: pip install lxml")
    import sys
    sys.exit(1)


class YumRepo:
    """YUM repository manager with pluggable storage backends"""
    
    REPO_TYPE = 'rpm'  # ADD THIS
    
    def __init__(self, config: RepoConfig):
        # ... existing code ...
    
    # ... all other methods ...
```

## Step 2: Create core/deb.py

### Extract from debs3.py
1. Copy lines 1-24 (imports)
2. Copy lines 26-1100 (entire DebRepo class)
3. Add `REPO_TYPE = 'deb'` as class attribute after `__init__`

### File structure:
```python
"""
Debian repository manager

Copyright (c) 2025 Deepgram
...
"""

import argparse
import os
import sys
import subprocess
import re
import gzip
import bz2
import hashlib
import io
from datetime import datetime
from pathlib import Path
import json
import tempfile

from core.backend import create_storage_backend
from core.config import RepoConfig
from core.constants import REPO_CONFIG_FILES
from core import Colors


class DebRepo:
    """Debian repository manager with pluggable storage backends"""
    
    REPO_TYPE = 'deb'  # ADD THIS
    
    def __init__(self, config: RepoConfig):
        # ... existing code ...
    
    # ... all other methods ...
```

## Step 3: Update core/__init__.py

### Current content:
```python
class Colors:
    # ... existing code ...
```

### New content:
```python
class Colors:
    # ... existing code ...

# Export factory function
from core.cli import create_repo_manager

__all__ = ['Colors', 'create_repo_manager']
```

## Step 4: Replace yums3.py

### Backup old file:
```bash
cp yums3.py yums3.py.old
```

### New content:
```python
#!/usr/bin/env python3
"""
yums3 - Efficient YUM repository manager for S3

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

from core.cli import main
import sys

if __name__ == '__main__':
    sys.exit(main('rpm'))
```

## Step 5: Replace debs3.py

### Backup old file:
```bash
cp debs3.py debs3.py.old
```

### New content:
```python
#!/usr/bin/env python3
"""
debs3 - Efficient Debian repository manager for S3

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

from core.cli import main
import sys

if __name__ == '__main__':
    sys.exit(main('deb'))
```

## Step 6: Verify Imports

### Check that all imports work:
```bash
python3 -c "from core.yum import YumRepo; print('YumRepo OK')"
python3 -c "from core.deb import DebRepo; print('DebRepo OK')"
python3 -c "from core.cli import main; print('CLI OK')"
python3 -c "from core import create_repo_manager; print('Factory OK')"
```

## Step 7: Test Functionality

### Test RPM operations:
```bash
# Config
./yums3.py config --list

# Add (dry run)
./yums3.py add test_rpms/hello-world-1.0.0-1.el9.x86_64.rpm

# Validate
./yums3.py validate el9/x86_64

# Remove (dry run)
./yums3.py remove hello-world-1.0.0-1.el9.x86_64.rpm
```

### Test DEB operations:
```bash
# Config
./debs3.py config --list

# Add (dry run)
./debs3.py add test_debs/hello-world_1.0.0_amd64.deb

# Validate
./debs3.py validate focal main amd64

# Remove (dry run)
./debs3.py remove hello-world_1.0.0_amd64.deb
```

## Step 8: Run Test Suite

```bash
# Run all tests
python3 -m pytest tests/

# Run specific test files
python3 -m pytest tests/test_cli_commands.py
python3 -m pytest tests/test_config.py
python3 -m pytest tests/test_backend.py
```

## Step 9: Clean Up

### If everything works:
```bash
# Remove backup files
rm yums3.py.old debs3.py.old

# Update documentation
# Update README.md to reflect new architecture
```

### If something breaks:
```bash
# Restore old files
mv yums3.py.old yums3.py
mv debs3.py.old debs3.py

# Debug and fix issues
# Then try again
```

## Verification Checklist

- [ ] core/yum.py created and imports successfully
- [ ] core/deb.py created and imports successfully
- [ ] core/cli.py exists and imports successfully
- [ ] core/__init__.py updated with factory export
- [ ] yums3.py replaced with thin wrapper
- [ ] debs3.py replaced with thin wrapper
- [ ] All imports work without errors
- [ ] yums3.py config command works
- [ ] debs3.py config command works
- [ ] yums3.py add command works (dry run)
- [ ] debs3.py add command works (dry run)
- [ ] yums3.py validate command works
- [ ] debs3.py validate command works
- [ ] All tests pass
- [ ] No regressions in functionality
- [ ] Documentation updated

## Troubleshooting

### Import Error: "No module named 'core.yum'"
- Check that core/yum.py exists
- Check that core/__init__.py exists
- Try: `python3 -c "import core.yum"`

### Import Error: "cannot import name 'create_repo_manager'"
- Check that core/cli.py exists
- Check that core/__init__.py has the import
- Try: `python3 -c "from core.cli import create_repo_manager"`

### Command Not Found: "./yums3.py"
- Check file permissions: `chmod +x yums3.py`
- Check shebang line: `#!/usr/bin/env python3`

### Tests Failing
- Check that all files are in place
- Check that imports work
- Run tests individually to isolate issue
- Check test expectations match new structure

## Success Criteria

✅ All files created
✅ All imports work
✅ All commands work
✅ All tests pass
✅ No regressions
✅ Code is cleaner and more maintainable

## Estimated Time

- Step 1-2: 10 minutes (copy/paste)
- Step 3-5: 5 minutes (simple updates)
- Step 6-7: 10 minutes (testing)
- Step 8: 5 minutes (test suite)
- Step 9: 2 minutes (cleanup)

**Total: ~30 minutes**

## Notes

- Keep backup files until fully verified
- Test incrementally (one step at a time)
- If stuck, restore backups and debug
- Document any issues encountered
