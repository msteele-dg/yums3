# Refactoring Proposal: Unified CLI Architecture

## Current State
- `yums3.py`: 1680 lines (YumRepo class + main() + config_command())
- `debs3.py`: 1351 lines (DebRepo class + main() + config_command())
- **Total duplication**: ~300 lines in main() and config_command()

## Proposed Architecture

```
core/
├── __init__.py          # Exports: Colors, create_repo_manager()
├── config.py            # RepoConfig (no changes)
├── backend.py           # Storage backends (no changes)
├── constants.py         # Constants (no changes)
├── yum.py               # YumRepo class (~1200 lines)
├── deb.py               # DebRepo class (~900 lines)
└── cli.py               # Generic CLI (~200 lines)

yums3.py                 # Entry point (~10 lines)
debs3.py                 # Entry point (~10 lines)
```

## Key Design Principles

### 1. Repo Classes Have Common Interface
Both `YumRepo` and `DebRepo` implement:
- `add_packages(files)` - Add packages to repo
- `remove_packages(names, **kwargs)` - Remove packages from repo
- `validate_repository(**kwargs)` - Validate repo integrity
- `get_target_info(files)` - Return display info for confirmation

### 2. Generic CLI Handles Common Logic
`core/cli.py` contains:
- Argument parsing (with repo-specific customization)
- Config loading and CLI overrides
- Confirmation prompts
- Error handling
- Backend info display

### 3. Thin Entry Points
`yums3.py` and `debs3.py` become simple wrappers:
```python
#!/usr/bin/env python3
from core.cli import main
import sys

if __name__ == '__main__':
    sys.exit(main('rpm'))  # or main('deb')
```

## Implementation Strategy

### Phase 1: Extract Repo Classes (No Behavior Change)
1. Copy `YumRepo` from `yums3.py` → `core/yum.py`
2. Copy `DebRepo` from `debs3.py` → `core/deb.py`
3. Add `REPO_TYPE` class attribute to each
4. Add `get_target_info()` method to each

### Phase 2: Create Generic CLI
1. Extract common `main()` logic → `core/cli.py`
2. Extract `config_command()` → `core/cli.py`
3. Parameterize repo-specific argument parsing
4. Use factory pattern to create repo instances

### Phase 3: Update Entry Points
1. Replace `yums3.py` with thin wrapper
2. Replace `debs3.py` with thin wrapper
3. Update `core/__init__.py` exports

### Phase 4: Verify
1. Run existing tests
2. Manual testing of both CLIs
3. Verify backward compatibility

## Benefits

### Code Quality
- **-300 lines**: Eliminate duplicated main() and config_command()
- **Single source of truth**: CLI logic in one place
- **Easier maintenance**: Fix bugs once, not twice
- **Better testability**: Test CLI logic independently

### Extensibility
- **Easy to add new repo types**: Just implement the interface
- **Consistent UX**: All repo types behave the same way
- **Shared improvements**: New CLI features benefit all repo types

### Maintainability
- **Clear separation**: Repo logic vs CLI logic
- **Smaller files**: Easier to navigate and understand
- **Better organization**: Logical module structure

## Backward Compatibility

✅ **Fully backward compatible**
- Same command-line interfaces
- Same config file formats
- Same behavior
- No breaking changes

## Risk Assessment

### Low Risk
- Repo classes are self-contained (just moving code)
- Entry points are trivial wrappers
- No changes to core logic

### Medium Risk
- CLI refactoring requires careful parameter handling
- Need to ensure all edge cases are covered

### Mitigation
- Comprehensive testing before/after
- Incremental rollout (one repo type at a time)
- Keep old files as backup during transition

## Next Steps

1. **Review this proposal** - Get feedback on approach
2. **Create core/yum.py** - Extract YumRepo class
3. **Create core/deb.py** - Extract DebRepo class
4. **Create core/cli.py** - Extract common CLI logic
5. **Update entry points** - Make them thin wrappers
6. **Test thoroughly** - Verify no regressions
7. **Clean up** - Remove old code, update docs

## Questions to Resolve

1. Should `get_target_info()` return a dict or tuple?
2. How to handle repo-specific validation args (el_version/arch vs distribution/component/arch)?
3. Should we create an abstract base class for repos?
4. How to handle repo-specific argument parsing differences?

## Recommendation

**Proceed with refactoring** - The benefits significantly outweigh the risks, and the implementation is straightforward.
