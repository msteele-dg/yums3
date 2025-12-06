# CLI Migration Guide

This guide helps you migrate from the old CLI syntax to the new subcommand-based syntax.

## Overview

The yums3 CLI has been refactored to use explicit subcommands (`add`, `remove`, `validate`, `config`) instead of implicit operations with flags. This makes the interface more consistent and easier to understand.

## What Changed

### Old Syntax (Deprecated)
```bash
# Adding packages (implicit)
./yums3.py package.rpm
./yums3.py -y package.rpm

# Removing packages (with flag)
./yums3.py --remove package.rpm
./yums3.py -y --remove package.rpm

# Validating (with flag)
./yums3.py --validate el9/x86_64

# Config (subcommand - unchanged)
./yums3.py config --list
```

### New Syntax (Current)
```bash
# Adding packages (explicit subcommand)
./yums3.py add package.rpm
./yums3.py add -y package.rpm

# Removing packages (explicit subcommand)
./yums3.py remove package.rpm
./yums3.py remove -y package.rpm

# Validating (explicit subcommand)
./yums3.py validate el9/x86_64

# Config (subcommand - unchanged)
./yums3.py config --list
```

## Migration Examples

### Adding Packages

**Old:**
```bash
./yums3.py my-package.rpm
./yums3.py pkg1.rpm pkg2.rpm pkg3.rpm
./yums3.py -y my-package.rpm
./yums3.py -b my-bucket my-package.rpm
```

**New:**
```bash
./yums3.py add my-package.rpm
./yums3.py add pkg1.rpm pkg2.rpm pkg3.rpm
./yums3.py add -y my-package.rpm
./yums3.py --bucket my-bucket add my-package.rpm
```

### Removing Packages

**Old:**
```bash
./yums3.py --remove my-package.rpm
./yums3.py --remove pkg1.rpm pkg2.rpm
./yums3.py -y --remove my-package.rpm
```

**New:**
```bash
./yums3.py remove my-package.rpm
./yums3.py remove pkg1.rpm pkg2.rpm
./yums3.py remove -y my-package.rpm
```

### Validating Repository

**Old:**
```bash
./yums3.py --validate el9/x86_64
```

**New:**
```bash
./yums3.py validate el9/x86_64
```

### Skipping Validation

**Old:**
```bash
./yums3.py --no-validate my-package.rpm
./yums3.py --no-validate --remove my-package.rpm
```

**New:**
```bash
./yums3.py add --no-validate my-package.rpm
./yums3.py remove --no-validate my-package.rpm
```

### Global Options

Global options (like `--bucket`, `--profile`, `--config`) now come **before** the subcommand:

**Old:**
```bash
./yums3.py -b my-bucket my-package.rpm
./yums3.py --profile prod my-package.rpm
```

**New:**
```bash
./yums3.py --bucket my-bucket add my-package.rpm
./yums3.py --profile prod add my-package.rpm
```

## CI/CD Migration

### GitHub Actions

**Old:**
```yaml
- name: Publish to YUM repo
  run: |
    ./yums3.py -y dist/*.rpm
```

**New:**
```yaml
- name: Publish to YUM repo
  run: |
    ./yums3.py add -y dist/*.rpm
```

### Jenkins

**Old:**
```groovy
sh './yums3.py -y ${WORKSPACE}/rpmbuild/RPMS/x86_64/*.rpm'
```

**New:**
```groovy
sh './yums3.py add -y ${WORKSPACE}/rpmbuild/RPMS/x86_64/*.rpm'
```

### GitLab CI

**Old:**
```yaml
script:
  - ./yums3.py -y dist/*.rpm
```

**New:**
```yaml
script:
  - ./yums3.py add -y dist/*.rpm
```

## Script Migration

### Bash Scripts

**Old:**
```bash
#!/bin/bash
RPMS=$(find /tmp/rpmbuild -name "*.rpm")
./yums3.py -y $RPMS
```

**New:**
```bash
#!/bin/bash
RPMS=$(find /tmp/rpmbuild -name "*.rpm")
./yums3.py add -y $RPMS
```

### Python Scripts

**Old:**
```python
import subprocess

subprocess.run(['./yums3.py', '-y', 'package.rpm'])
subprocess.run(['./yums3.py', '--remove', 'old-package.rpm'])
```

**New:**
```python
import subprocess

subprocess.run(['./yums3.py', 'add', '-y', 'package.rpm'])
subprocess.run(['./yums3.py', 'remove', 'old-package.rpm'])
```

## Benefits of New Syntax

1. **Explicit Operations**: Clear what action is being performed
2. **Consistent Interface**: All operations use subcommands
3. **Better Help**: Each subcommand has its own help text
4. **Future Extensibility**: Easy to add new commands
5. **Standard Pattern**: Follows git/docker/kubectl conventions

## Quick Reference

| Operation | Old Syntax | New Syntax |
|-----------|-----------|------------|
| Add package | `./yums3.py pkg.rpm` | `./yums3.py add pkg.rpm` |
| Add with -y | `./yums3.py -y pkg.rpm` | `./yums3.py add -y pkg.rpm` |
| Remove package | `./yums3.py --remove pkg.rpm` | `./yums3.py remove pkg.rpm` |
| Remove with -y | `./yums3.py -y --remove pkg.rpm` | `./yums3.py remove -y pkg.rpm` |
| Validate | `./yums3.py --validate el9/x86_64` | `./yums3.py validate el9/x86_64` |
| Skip validation | `./yums3.py --no-validate pkg.rpm` | `./yums3.py add --no-validate pkg.rpm` |
| Config list | `./yums3.py config --list` | `./yums3.py config --list` (unchanged) |
| With bucket | `./yums3.py -b bucket pkg.rpm` | `./yums3.py --bucket bucket add pkg.rpm` |
| With profile | `./yums3.py --profile prod pkg.rpm` | `./yums3.py --profile prod add pkg.rpm` |

## Getting Help

```bash
# General help
./yums3.py --help

# Add command help
./yums3.py add --help

# Remove command help
./yums3.py remove --help

# Validate command help
./yums3.py validate --help

# Config command help
./yums3.py config --help
```

## Troubleshooting

### "error: the following arguments are required: rpm_files"

You're using the old syntax. Add the `add` subcommand:

```bash
# Old (fails)
./yums3.py package.rpm

# New (works)
./yums3.py add package.rpm
```

### "error: unrecognized arguments: --remove"

The `--remove` flag has been replaced with the `remove` subcommand:

```bash
# Old (fails)
./yums3.py --remove package.rpm

# New (works)
./yums3.py remove package.rpm
```

### "error: argument --bucket: expected one argument"

Global options must come before the subcommand:

```bash
# Wrong order (fails)
./yums3.py add --bucket my-bucket package.rpm

# Correct order (works)
./yums3.py --bucket my-bucket add package.rpm
```

## Need Help?

If you encounter issues during migration:

1. Check the help text: `./yums3.py --help`
2. Check subcommand help: `./yums3.py add --help`
3. Review the examples in README.md
4. Check the test suite in `tests/test_cli_commands.py`
