# yums3 User Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Configuration](#configuration)
5. [Commands](#commands)
6. [Common Workflows](#common-workflows)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

## Introduction

yums3 is a command-line tool for managing YUM/DNF repositories with support for both S3 and local filesystem storage. It provides efficient package management with intelligent deduplication and comprehensive validation.

### Key Features

- **Pluggable Storage:** S3 or local filesystem
- **Intelligent Deduplication:** Skip packages that already exist
- **Fast Operations:** Only download/upload what's needed
- **Automatic Backups:** Safe metadata operations with automatic recovery
- **Git-Style Configuration:** Familiar interface for DevOps teams
- **SQLite Support:** Fast DNF queries with database metadata
- **Comprehensive Validation:** Ensure repository integrity

## Installation

### Prerequisites

```bash
# System dependencies (Rocky/RHEL)
sudo dnf install createrepo_c rpm-build python3-pip

# System dependencies (Ubuntu/Debian)
sudo apt-get install createrepo-c rpm python3-pip
```

### Python Dependencies

```bash
pip install boto3 lxml
```

### AWS Configuration (for S3)

```bash
# Configure AWS credentials
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_DEFAULT_REGION=us-east-1
```

## Quick Start

### 1. Configure yums3

```bash
# Set backend type and bucket
./yums3.py config backend.type s3
./yums3.py config backend.s3.bucket my-yum-repo

# Or for local storage
./yums3.py config backend.type local
./yums3.py config backend.local.path /srv/yum-repo
```

### 2. Add Packages

```bash
# Add single package
./yums3.py add my-package-1.0.0-1.el9.x86_64.rpm

# Add multiple packages
./yums3.py add pkg1.rpm pkg2.rpm pkg3.rpm

# Add with glob
./yums3.py add /tmp/rpmbuild/RPMS/x86_64/*.rpm
```

### 3. Remove Packages

```bash
# Remove single package
./yums3.py remove old-package-1.0.0-1.el9.x86_64.rpm

# Remove multiple packages
./yums3.py remove pkg1.rpm pkg2.rpm
```

### 4. Validate Repository

```bash
# Validate repository
./yums3.py validate el9/x86_64
```

## Configuration

### Configuration Files

yums3 searches for configuration in this order:
1. `./yums3.conf` (current directory)
2. `~/.yums3.conf` (user home)
3. `/etc/yums3.conf` (system-wide)

### Configuration Format

Configuration uses flat JSON with dot-notated keys:

```json
{
  "backend.type": "s3",
  "backend.s3.bucket": "my-yum-repo",
  "backend.s3.profile": "production",
  "repo.cache_dir": "/var/cache/yums3",
  "validation.enabled": true,
  "behavior.confirm": true,
  "behavior.backup": true
}
```

### Configuration Keys

#### Backend Configuration

**S3 Backend:**
```bash
./yums3.py config backend.type s3
./yums3.py config backend.s3.bucket my-bucket
./yums3.py config backend.s3.profile production
./yums3.py config backend.s3.endpoint https://s3.us-west-2.amazonaws.com
```

**Local Backend:**
```bash
./yums3.py config backend.type local
./yums3.py config backend.local.path /srv/yum-repo
```

#### Repository Configuration

```bash
./yums3.py config repo.cache_dir /var/cache/yums3
```

#### Behavior Configuration

```bash
./yums3.py config validation.enabled true
./yums3.py config behavior.confirm false  # Skip confirmation
./yums3.py config behavior.backup true    # Create backups
```

### Config Command Reference

```bash
# Get value
./yums3.py config backend.type

# Set value
./yums3.py config backend.s3.bucket my-bucket

# List all config
./yums3.py config --list

# Unset value
./yums3.py config --unset backend.s3.endpoint

# Validate config
./yums3.py config --validate

# Use specific config file
./yums3.py config --file=/etc/yums3.conf backend.type s3

# Use local config (./yums3.conf)
./yums3.py config --local backend.type local

# Use global config (~/.yums3.conf)
./yums3.py config --global backend.s3.bucket my-bucket

# Use system config (/etc/yums3.conf)
./yums3.py config --system backend.s3.bucket shared-bucket
```

## Commands

### add - Add Packages

Add one or more RPM packages to the repository.

**Syntax:**
```bash
./yums3.py add [OPTIONS] RPM_FILE [RPM_FILE ...]
```

**Options:**
- `-y, --yes` - Skip confirmation prompt
- `--no-validate` - Skip post-operation validation

**Examples:**
```bash
# Add single package
./yums3.py add package.rpm

# Add multiple packages
./yums3.py add pkg1.rpm pkg2.rpm pkg3.rpm

# Add with glob
./yums3.py add /tmp/*.rpm

# Skip confirmation (CI/CD)
./yums3.py add -y package.rpm

# Skip validation (faster)
./yums3.py add --no-validate package.rpm
```

**Behavior:**
- Automatically detects architecture and EL version from RPM
- Checks for duplicates (skips if same checksum)
- Updates if same filename but different checksum
- Creates repository if it doesn't exist
- Backs up metadata before changes
- Validates after operation (unless --no-validate)

**Output:**
```
Target: el9/x86_64 (2 packages)
Checking for duplicate packages...
  ⊘ pkg1.rpm (already exists with same checksum)
  + pkg2.rpm (new package)
Skipped 1 duplicate package(s)
Updating existing repository...
✓ Published 1 package to s3://my-bucket/el9/x86_64
```

### remove - Remove Packages

Remove one or more RPM packages from the repository.

**Syntax:**
```bash
./yums3.py remove [OPTIONS] RPM_FILENAME [RPM_FILENAME ...]
```

**Options:**
- `-y, --yes` - Skip confirmation prompt
- `--no-validate` - Skip post-operation validation

**Examples:**
```bash
# Remove single package
./yums3.py remove old-package-1.0.0-1.el9.x86_64.rpm

# Remove multiple packages
./yums3.py remove pkg1.rpm pkg2.rpm

# Skip confirmation
./yums3.py remove -y old-package.rpm
```

**Note:** Use filename only, not full path.

### validate - Validate Repository

Perform comprehensive validation of repository integrity.

**Syntax:**
```bash
./yums3.py validate REPO_PATH
```

**Arguments:**
- `REPO_PATH` - Repository path (e.g., `el9/x86_64`)

**Examples:**
```bash
# Validate repository
./yums3.py validate el9/x86_64
```

**Checks:**
- Metadata checksums match actual files
- All RPMs listed in metadata exist
- No orphaned RPMs (in storage but not in metadata)
- SQLite databases are valid
- No duplicate data types in repomd.xml
- Namespace prefixes are correct

**Output:**
```
Validating repository: el9/x86_64
✓ Metadata checksums valid
✓ All packages in metadata exist
✓ No orphaned packages
✓ SQLite databases valid
✓ Repository is valid
```

### config - Manage Configuration

Manage yums3 configuration.

**Syntax:**
```bash
./yums3.py config [OPTIONS] [KEY] [VALUE]
```

**Options:**
- `--list` - List all configuration
- `--unset KEY` - Remove configuration key
- `--validate` - Validate configuration
- `--file FILE` - Use specific config file
- `--global` - Use global config (~/.yums3.conf)
- `--local` - Use local config (./yums3.conf)
- `--system` - Use system config (/etc/yums3.conf)

**Examples:** See [Configuration](#configuration) section above.

## Common Workflows

### Initial Setup (S3)

```bash
# 1. Configure S3 backend
./yums3.py config backend.type s3
./yums3.py config backend.s3.bucket my-yum-repo
./yums3.py config backend.s3.profile production

# 2. Set cache directory
./yums3.py config repo.cache_dir /var/cache/yums3

# 3. Verify configuration
./yums3.py config --list
./yums3.py config --validate

# 4. Add first packages
./yums3.py add /path/to/packages/*.rpm
```

### Initial Setup (Local)

```bash
# 1. Configure local backend
./yums3.py config backend.type local
./yums3.py config backend.local.path /srv/yum-repo

# 2. Verify configuration
./yums3.py config --validate

# 3. Add packages
./yums3.py add /path/to/packages/*.rpm
```

### CI/CD Integration

```bash
#!/bin/bash
# Build and publish RPMs

# Build RPMs
rpmbuild -ba mypackage.spec

# Publish to repository (skip confirmation)
./yums3.py add -y ~/rpmbuild/RPMS/x86_64/*.rpm

# Validate
./yums3.py validate el9/x86_64
```

### Updating Packages

```bash
# Build new version
rpmbuild -ba mypackage.spec

# Add to repository (will update if checksum changed)
./yums3.py add ~/rpmbuild/RPMS/x86_64/mypackage-*.rpm
```

### Cleaning Up Old Packages

```bash
# Remove old versions
./yums3.py remove old-package-1.0.0-1.el9.x86_64.rpm

# Or remove multiple
./yums3.py remove \
  old-package-1.0.0-1.el9.x86_64.rpm \
  old-package-1.0.1-1.el9.x86_64.rpm
```

### Switching Backends

```bash
# Switch from S3 to local for testing
./yums3.py config --local backend.type local
./yums3.py config --local backend.local.path /tmp/test-repo

# Test with local backend
./yums3.py add test-package.rpm

# Switch back to S3
./yums3.py config backend.type s3
```

### Multi-Environment Setup

```bash
# Development environment
./yums3.py config --file=dev.conf backend.s3.bucket dev-yum-repo
./yums3.py config --file=dev.conf backend.s3.profile dev

# Production environment
./yums3.py config --file=prod.conf backend.s3.bucket prod-yum-repo
./yums3.py config --file=prod.conf backend.s3.profile prod

# Use specific environment
./yums3.py --config=dev.conf add package.rpm
./yums3.py --config=prod.conf add package.rpm
```

## Troubleshooting

### Package Already Exists

**Symptom:**
```
⊘ package.rpm (already exists with same checksum)
✓ All packages already exist - nothing to do
```

**Cause:** Package with same checksum already in repository

**Solution:** This is normal behavior (deduplication). If you want to force re-add:
1. Remove the package first: `./yums3.py remove package.rpm`
2. Add it again: `./yums3.py add package.rpm`

### Configuration Errors

**Symptom:**
```
Configuration errors:
  - backend.s3.bucket is required for S3 backend
```

**Solution:**
```bash
# Check current config
./yums3.py config --list

# Set missing values
./yums3.py config backend.s3.bucket my-bucket

# Validate
./yums3.py config --validate
```

### AWS Credentials Not Found

**Symptom:**
```
Unable to locate credentials
```

**Solution:**
```bash
# Configure AWS credentials
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret

# Or specify profile
./yums3.py config backend.s3.profile my-profile
```

### Validation Failures

**Symptom:**
```
⚠ Validation found issues
```

**Solution:**
```bash
# Run full validation to see details
./yums3.py validate el9/x86_64

# Common fixes:
# 1. Regenerate metadata
./yums3.py add --no-validate existing-package.rpm

# 2. Remove and re-add problematic package
./yums3.py remove problem-package.rpm
./yums3.py add problem-package.rpm
```

### Operation Failed - Metadata Restored

**Symptom:**
```
✗ Operation failed: ...
Restoring metadata from backup...
```

**Cause:** Operation failed mid-way

**Solution:**
- Metadata was automatically restored
- Check error message for root cause
- Fix issue and retry operation
- Backup is retained for inspection if needed

### Checksum Mismatch

**Symptom:**
```
Checksum doesn't match for file
```

**Solution:**
```bash
# Clear cache and retry
rm -rf ~/.cache/yums3/

# Or specify different cache directory
./yums3.py --cache-dir=/tmp/yums3-cache add package.rpm
```

## Best Practices

### 1. Use Configuration Files

**Don't:**
```bash
./yums3.py --bucket my-bucket --profile prod add package.rpm
```

**Do:**
```bash
./yums3.py config backend.s3.bucket my-bucket
./yums3.py config backend.s3.profile prod
./yums3.py add package.rpm
```

### 2. Enable Validation in Production

```bash
# Ensure validation is enabled
./yums3.py config validation.enabled true

# Validation catches issues early
./yums3.py add package.rpm
# (automatic validation after add)
```

### 3. Use -y Flag in CI/CD

```bash
# Skip confirmation in automated scripts
./yums3.py add -y package.rpm
```

### 4. Organize by Environment

```bash
# Use different config files per environment
./yums3.py --config=dev.conf add package.rpm
./yums3.py --config=prod.conf add package.rpm
```

### 5. Regular Validation

```bash
# Validate repositories regularly
./yums3.py validate el9/x86_64
./yums3.py validate el9/aarch64
```

### 6. Keep Backups

Backups are automatic, but you can manually inspect them:

```bash
# List backups (S3)
aws s3 ls s3://my-bucket/el9/x86_64/ | grep backup

# List backups (local)
ls -la /srv/yum-repo/el9/x86_64/ | grep backup
```

### 7. Use Specific Versions

```bash
# Don't use wildcards that might match multiple versions
# Bad:
./yums3.py add mypackage-*.rpm

# Good:
./yums3.py add mypackage-1.2.3-1.el9.x86_64.rpm
```

### 8. Test Locally First

```bash
# Test with local backend before S3
./yums3.py config --local backend.type local
./yums3.py config --local backend.local.path /tmp/test-repo
./yums3.py add test-package.rpm
./yums3.py validate el9/x86_64
```

### 9. Monitor Operations

```bash
# Watch for warnings
./yums3.py add package.rpm 2>&1 | tee add.log

# Check validation results
./yums3.py validate el9/x86_64 | tee validate.log
```

### 10. Document Your Setup

```bash
# Save your configuration
./yums3.py config --list > yums3-config.txt

# Document your workflow
cat > REPO_WORKFLOW.md <<EOF
# Repository Workflow

## Adding Packages
./yums3.py add -y /path/to/packages/*.rpm

## Validation
./yums3.py validate el9/x86_64
EOF
```

## Global Options

These options can be used with any command:

```bash
--config CONFIG       # Path to config file
--bucket BUCKET       # S3 bucket (overrides config)
--cache-dir DIR       # Cache directory (overrides config)
--profile PROFILE     # AWS profile (overrides config)
--s3-endpoint-url URL # S3 endpoint (overrides config)
```

**Example:**
```bash
# Override bucket for single operation
./yums3.py --bucket test-bucket add package.rpm

# Use different cache directory
./yums3.py --cache-dir=/tmp/cache add package.rpm
```

## Exit Codes

- `0` - Success
- `1` - Error (validation failed, operation failed, etc.)
- `130` - Cancelled by user (Ctrl+C)

## Getting Help

```bash
# General help
./yums3.py --help

# Command-specific help
./yums3.py add --help
./yums3.py remove --help
./yums3.py validate --help
./yums3.py config --help
```

## See Also

- [Architecture Documentation](ARCHITECTURE.md)
- [Developer Guide](DEVELOPER_GUIDE.md)
- [API Reference](API_REFERENCE.md)
- [Configuration Reference](CONFIG_COMMAND_REFERENCE.md)
- [CLI Migration Guide](CLI_MIGRATION_GUIDE.md)
