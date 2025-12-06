# Refactoring Plan: debs3 and yums3

## Goal
Create a clean, elegant design that eliminates duplication between debs3.py and yums3.py by:
1. Moving repo-specific logic into `core/yum.py` and `core/deb.py`
2. Creating a generic `main()` function that can handle both repo types
3. Maintaining clean separation of concerns

## Proposed Structure

```
core/
  __init__.py          # Export Colors, create_repo_manager()
  config.py            # RepoConfig (already good)
  backend.py           # Storage backends (already good)
  constants.py         # Constants (already good)
  yum.py               # YumRepo class
  deb.py               # DebRepo class
  cli.py               # Generic CLI handling (new)

yums3.py               # Thin wrapper: calls cli.main('rpm')
debs3.py               # Thin wrapper: calls cli.main('deb')
```

## Key Design Decisions

### 1. Repo Classes (core/yum.py, core/deb.py)
- Each class implements repo-specific logic
- Common interface: `add_packages()`, `remove_packages()`, `validate_repository()`
- Each class has a `REPO_TYPE` class attribute ('rpm' or 'deb')
- Each class has a `get_target_info()` method to return display info

### 2. Generic CLI (core/cli.py)
- Single `main(repo_type)` function
- Handles argument parsing (with repo-specific customization)
- Handles config loading
- Handles confirmation prompts
- Delegates to appropriate repo class

### 3. Entry Points (yums3.py, debs3.py)
- Minimal wrappers that call `cli.main()` with appropriate repo_type
- Preserve existing command-line interfaces

## Implementation Steps

1. Create `core/yum.py` with YumRepo class
2. Create `core/deb.py` with DebRepo class  
3. Create `core/cli.py` with generic main() function
4. Update `yums3.py` to use cli.main('rpm')
5. Update `debs3.py` to use cli.main('deb')
6. Update `core/__init__.py` to export create_repo_manager()

## Benefits

- Eliminates ~90% of duplication between yums3.py and debs3.py
- Makes it easy to add new repo types in the future
- Cleaner separation of concerns
- Easier to test individual components
- Maintains backward compatibility with existing CLIs
