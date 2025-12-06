# yums3 config Command Reference

Quick reference guide for the `yums3 config` command.

## Basic Usage

### Get a config value
```bash
yums3 config backend.type
# Output: s3
```

### Set a config value
```bash
yums3 config backend.s3.bucket my-bucket
# Output: Set backend.s3.bucket = my-bucket
```

### List all config values
```bash
yums3 config --list
# Output:
# backend.type=s3
# backend.s3.bucket=my-bucket
# backend.s3.profile=default
# repo.cache_dir=/home/user/yum-repo
# validation.enabled=True
# behavior.confirm=True
# behavior.backup=True
```

### Remove a config value
```bash
yums3 config --unset backend.s3.endpoint
# Output: Unset backend.s3.endpoint
```

### Validate configuration
```bash
yums3 config --validate
# Output: Configuration is valid
# (or lists errors if invalid)
```

## Config File Locations

### Use specific file
```bash
yums3 config --file=/path/to/config.conf backend.type s3
```

### Use global config (default)
```bash
yums3 config --global backend.s3.bucket my-bucket
# Saves to: ~/.yums3.conf
```

### Use local config
```bash
yums3 config --local backend.type local
# Saves to: ./yums3.conf
```

### Use system config
```bash
yums3 config --system backend.s3.bucket shared-bucket
# Saves to: /etc/yums3.conf
```

## Configuration Keys

### Backend Configuration

**S3 Backend:**
```bash
yums3 config backend.type s3
yums3 config backend.s3.bucket my-yum-repo
yums3 config backend.s3.profile production
yums3 config backend.s3.endpoint https://s3.us-west-2.amazonaws.com
```

**Local Backend:**
```bash
yums3 config backend.type local
yums3 config backend.local.path /srv/yum-repo
```

### Repository Configuration
```bash
yums3 config repo.cache_dir /var/cache/yums3
```

### Behavior Configuration
```bash
yums3 config validation.enabled true
yums3 config behavior.confirm false
yums3 config behavior.backup true
```

## Common Workflows

### Initial S3 Setup
```bash
yums3 config backend.type s3
yums3 config backend.s3.bucket my-yum-repo
yums3 config backend.s3.profile production
yums3 config repo.cache_dir /var/cache/yums3
yums3 config --validate
```

### Initial Local Setup
```bash
yums3 config backend.type local
yums3 config backend.local.path /srv/yum-repo
yums3 config repo.cache_dir /tmp/yums3-cache
yums3 config --validate
```

### Switch from S3 to Local
```bash
yums3 config backend.type local
yums3 config backend.local.path /tmp/test-repo
yums3 config --validate
```

### Per-Project Configuration
```bash
cd /path/to/project
yums3 config --local backend.type local
yums3 config --local backend.local.path ./repo
yums3 config --local --list
```

### Check Current Configuration
```bash
# List all settings
yums3 config --list

# Check specific value
yums3 config backend.type

# Validate
yums3 config --validate
```

## Config File Format

Config files use flat JSON with dot-notated keys:

```json
{
  "backend.s3.bucket": "my-yum-repo",
  "backend.s3.profile": "production",
  "backend.type": "s3",
  "behavior.backup": true,
  "behavior.confirm": false,
  "repo.cache_dir": "/var/cache/yums3",
  "validation.enabled": true
}
```

## Default Values

If not set in config file, these defaults are used:

- `backend.type`: `s3`
- `repo.cache_dir`: `~/yum-repo`
- `validation.enabled`: `true`
- `behavior.confirm`: `true`
- `behavior.backup`: `true`

## Required Keys

**For S3 backend:**
- `backend.type` must be `s3`
- `backend.s3.bucket` must be set

**For local backend:**
- `backend.type` must be `local`
- `backend.local.path` must be set

## Validation Errors

Common validation errors and fixes:

### Missing S3 bucket
```bash
$ yums3 config --validate
Configuration errors:
  - backend.s3.bucket is required for S3 backend

# Fix:
$ yums3 config backend.s3.bucket my-bucket
```

### Missing local path
```bash
$ yums3 config --validate
Configuration errors:
  - backend.local.path is required for local backend

# Fix:
$ yums3 config backend.local.path /srv/yum-repo
```

### Invalid backend type
```bash
$ yums3 config backend.type invalid
$ yums3 config --validate
Configuration errors:
  - Invalid backend.type: 'invalid' (must be 's3' or 'local')

# Fix:
$ yums3 config backend.type s3
```

## Tips

1. **Check before changing**: Use `yums3 config --list` to see current settings
2. **Validate after changes**: Always run `yums3 config --validate` after making changes
3. **Use local configs for testing**: Use `--local` flag for project-specific settings
4. **Keep backups**: Config files are small, keep backups before major changes
5. **Use specific files for CI/CD**: Use `--file` flag to specify exact config location

## Examples

### Complete S3 Setup
```bash
# Set all S3 options
yums3 config backend.type s3
yums3 config backend.s3.bucket my-yum-repo
yums3 config backend.s3.profile production
yums3 config backend.s3.endpoint https://s3.us-west-2.amazonaws.com
yums3 config repo.cache_dir /var/cache/yums3

# Verify
yums3 config --list
yums3 config --validate
```

### Complete Local Setup
```bash
# Set all local options
yums3 config backend.type local
yums3 config backend.local.path /srv/yum-repo
yums3 config repo.cache_dir /tmp/yums3-cache
yums3 config validation.enabled true

# Verify
yums3 config --list
yums3 config --validate
```

### Testing Configuration
```bash
# Create test config in current directory
yums3 config --local backend.type local
yums3 config --local backend.local.path ./test-repo
yums3 config --local behavior.confirm false

# Test with it
yums3 test-package.rpm

# Clean up
rm yums3.conf
```

## See Also

- `yums3 --help` - Main command help
- `yums3 config --help` - Config command help
- `REPOCONFIG_COMPLETE.md` - Complete implementation documentation
- `DOT_NOTATION_CONFIG_DESIGN.md` - Design documentation
