# Dot Notation Configuration Design (Git-Style)

## Overview

Implement a git-style configuration system with dot notation keys stored in flat JSON, plus a `yums3 config` command for managing settings.

## Design Principles

1. **Flat JSON structure** with dot-notated keys
2. **Git-style interface** for setting/getting values
3. **Backward compatible** with existing configs
4. **Hierarchical organization** through naming convention
5. **Simple to read and edit** manually

## Configuration Schema

### Proposed Key Structure

```
# Repository Configuration
repo.path                    # Repository path within storage (e.g., "el9/x86_64")
repo.name                    # Optional: Named repository (alternative to auto-detection)
repo.cache_dir               # Local cache directory (default: ~/yum-repo)

# Backend Configuration
backend.type                 # "s3" or "local"

# S3 Backend
backend.s3.bucket            # S3 bucket name
backend.s3.endpoint          # S3 endpoint URL (optional)
backend.s3.profile           # AWS profile (optional, default: "default")
backend.s3.region            # AWS region (optional)

# Local Backend
backend.local.path           # Local storage base path

# Validation
validation.enabled           # Enable/disable post-operation validation (default: true)
validation.strict            # Fail on validation warnings (default: false)

# Behavior
behavior.confirm             # Require confirmation (default: true)
behavior.backup              # Create backups before operations (default: true)
```

### Example Config File

**~/.yums3.conf (JSON format):**
```json
{
  "backend.type": "s3",
  "backend.s3.bucket": "my-yum-repo",
  "backend.s3.profile": "production",
  "backend.s3.endpoint": null,
  "repo.cache_dir": "/var/cache/yums3",
  "validation.enabled": true,
  "behavior.confirm": true
}
```

**For local storage:**
```json
{
  "backend.type": "local",
  "backend.local.path": "/srv/yum-repo",
  "repo.cache_dir": "/tmp/yums3-cache"
}
```

## Config Command Interface

### Basic Usage

```bash
# Get a value
yums3 config backend.type
# Output: s3

# Set a value
yums3 config backend.s3.bucket my-bucket
# Saves to ~/.yums3.conf

# Set multiple values
yums3 config backend.type s3 backend.s3.bucket my-bucket

# Get all config
yums3 config --list
# Output:
# backend.type=s3
# backend.s3.bucket=my-bucket
# backend.s3.profile=default
# repo.cache_dir=/home/user/yum-repo

# Unset a value
yums3 config --unset backend.s3.endpoint

# Edit config in editor
yums3 config --edit
```

### Config File Selection

```bash
# Use specific config file
yums3 config --file=/etc/yums3.conf backend.type local

# Use global config (default)
yums3 config --global backend.s3.bucket my-bucket
# Saves to ~/.yums3.conf

# Use local config (current directory)
yums3 config --local backend.type local
# Saves to ./yums3.conf

# Use system config
yums3 config --system backend.s3.bucket shared-bucket
# Saves to /etc/yums3.conf
```

### Advanced Usage

```bash
# Get with default value
yums3 config --get backend.s3.profile default
# Returns value or "default" if not set

# Get all keys matching pattern
yums3 config --get-regexp "backend\.s3\..*"
# Output:
# backend.s3.bucket=my-bucket
# backend.s3.profile=production

# Show origin of each value
yums3 config --list --show-origin
# Output:
# file:/home/user/.yums3.conf  backend.type=s3
# file:/etc/yums3.conf          backend.s3.bucket=shared-bucket

# Validate config
yums3 config --validate
# Checks for required keys, valid values, etc.
```

## Implementation Design

### Config Class

```python
class YumS3Config:
    """Git-style configuration manager with dot notation"""
    
    def __init__(self, config_file=None):
        self.config_file = config_file or self._find_config_file()
        self.data = self._load_config()
    
    def get(self, key, default=None):
        """Get a config value by dot-notated key"""
        return self.data.get(key, default)
    
    def set(self, key, value):
        """Set a config value by dot-notated key"""
        self.data[key] = value
        self._save_config()
    
    def unset(self, key):
        """Remove a config key"""
        if key in self.data:
            del self.data[key]
            self._save_config()
    
    def list_all(self):
        """List all config key-value pairs"""
        return self.data.items()
    
    def get_section(self, prefix):
        """Get all keys under a prefix (e.g., 'backend.s3')"""
        return {k: v for k, v in self.data.items() if k.startswith(prefix + '.')}
    
    def validate(self):
        """Validate configuration"""
        errors = []
        
        # Check backend type
        backend_type = self.get('backend.type', 's3')
        if backend_type not in ['s3', 'local']:
            errors.append(f"Invalid backend.type: {backend_type}")
        
        # Check required keys per backend
        if backend_type == 's3':
            if not self.get('backend.s3.bucket'):
                errors.append("backend.s3.bucket is required for S3 backend")
        elif backend_type == 'local':
            if not self.get('backend.local.path'):
                errors.append("backend.local.path is required for local backend")
        
        return errors
    
    def _load_config(self):
        """Load config from JSON file"""
        if not os.path.exists(self.config_file):
            return {}
        
        with open(self.config_file, 'r') as f:
            return json.load(f)
    
    def _save_config(self):
        """Save config to JSON file"""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(self.data, f, indent=2, sort_keys=True)
    
    def _find_config_file(self):
        """Find config file in standard locations"""
        locations = [
            './yums3.conf',
            os.path.expanduser('~/.yums3.conf'),
            '/etc/yums3.conf'
        ]
        for loc in locations:
            if os.path.exists(loc):
                return loc
        return os.path.expanduser('~/.yums3.conf')  # Default
```

### Storage Backend Factory

```python
def create_storage_backend(config):
    """Create storage backend from config"""
    backend_type = config.get('backend.type', 's3')
    
    if backend_type == 's3':
        return S3StorageBackend(
            bucket_name=config.get('backend.s3.bucket'),
            aws_profile=config.get('backend.s3.profile'),
            endpoint_url=config.get('backend.s3.endpoint')
        )
    elif backend_type == 'local':
        return LocalStorageBackend(
            base_path=config.get('backend.local.path')
        )
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")
```

### YumRepo Integration

```python
class YumRepo:
    def __init__(self, config):
        """Initialize with config object"""
        self.config = config
        self.storage = create_storage_backend(config)
        self.cache_dir = config.get('repo.cache_dir', '~/yum-repo')
        self.skip_validation = not config.get('validation.enabled', True)
```

## Backward Compatibility

### Legacy Key Mapping

```python
LEGACY_KEY_MAP = {
    # Old key -> New key
    's3_bucket': 'backend.s3.bucket',
    'aws_profile': 'backend.s3.profile',
    's3_endpoint_url': 'backend.s3.endpoint',
    'local_storage_path': 'backend.local.path',
    'local_repo_base': 'repo.cache_dir',
    'storage_type': 'backend.type',
}

def migrate_legacy_config(old_config):
    """Convert old flat config to new dot notation"""
    new_config = {}
    for old_key, value in old_config.items():
        new_key = LEGACY_KEY_MAP.get(old_key, old_key)
        new_config[new_key] = value
    return new_config
```

### Auto-Migration

```python
def load_config_with_migration(config_file):
    """Load config and auto-migrate if needed"""
    with open(config_file, 'r') as f:
        data = json.load(f)
    
    # Check if it's old format (has legacy keys)
    has_legacy = any(key in data for key in LEGACY_KEY_MAP.keys())
    
    if has_legacy:
        print(f"Migrating config from old format...")
        data = migrate_legacy_config(data)
        
        # Save migrated config
        with open(config_file, 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True)
        
        print(f"Config migrated to new format")
    
    return data
```

## CLI Argument Mapping

### Map CLI args to config keys

```python
CLI_TO_CONFIG_MAP = {
    '--bucket': 'backend.s3.bucket',
    '--profile': 'backend.s3.profile',
    '--s3-endpoint-url': 'backend.s3.endpoint',
    '--repo-dir': 'repo.cache_dir',
}

def apply_cli_overrides(config, args):
    """Apply CLI arguments as config overrides"""
    if args.bucket:
        config.set('backend.s3.bucket', args.bucket)
    if args.profile:
        config.set('backend.s3.profile', args.profile)
    if args.s3_endpoint_url:
        config.set('backend.s3.endpoint', args.s3_endpoint_url)
    if args.repo_dir:
        config.set('repo.cache_dir', args.repo_dir)
```

## Benefits of This Approach

### 1. Familiarity
- Git users already understand this pattern
- `yums3 config` works like `git config`
- Intuitive for DevOps/sysadmins

### 2. Flexibility
- Easy to add new config options
- Hierarchical organization through naming
- Can query by prefix (`backend.s3.*`)

### 3. Simplicity
- Flat JSON structure (easy to read/edit)
- No nested objects to navigate
- Simple key-value pairs

### 4. Tooling
- Can use standard JSON tools
- Easy to script: `jq '.["backend.s3.bucket"]' ~/.yums3.conf`
- Can version control easily

### 5. Extensibility
- Add new backends without changing structure
- Add new options without breaking existing configs
- Can add sections for plugins, etc.

## Example Workflows

### Initial Setup (S3)

```bash
# Configure S3 backend
yums3 config backend.type s3
yums3 config backend.s3.bucket my-yum-repo
yums3 config backend.s3.profile production

# Set cache directory
yums3 config repo.cache_dir /var/cache/yums3

# Verify
yums3 config --list
```

### Initial Setup (Local)

```bash
# Configure local backend
yums3 config backend.type local
yums3 config backend.local.path /srv/yum-repo
yums3 config repo.cache_dir /tmp/yums3-cache

# Verify
yums3 config --list
```

### Switch Backends

```bash
# Switch from S3 to local
yums3 config backend.type local
yums3 config backend.local.path /tmp/test-repo

# Switch back to S3
yums3 config backend.type s3
```

### Per-Project Config

```bash
# Use local config for this project
cd /path/to/project
yums3 config --local backend.type local
yums3 config --local backend.local.path ./repo

# Now operations in this directory use local config
yums3 package.rpm
```

## Config File Examples

### Minimal S3 Config
```json
{
  "backend.s3.bucket": "my-bucket",
  "backend.type": "s3"
}
```

### Full S3 Config
```json
{
  "backend.s3.bucket": "my-yum-repo",
  "backend.s3.endpoint": "https://s3.us-west-2.amazonaws.com",
  "backend.s3.profile": "production",
  "backend.s3.region": "us-west-2",
  "backend.type": "s3",
  "behavior.backup": true,
  "behavior.confirm": false,
  "repo.cache_dir": "/var/cache/yums3",
  "validation.enabled": true,
  "validation.strict": false
}
```

### Local Config
```json
{
  "backend.local.path": "/srv/yum-repo",
  "backend.type": "local",
  "repo.cache_dir": "/tmp/yums3-cache",
  "validation.enabled": true
}
```

## Implementation Phases

### Phase 1: Config Class
1. Create `YumS3Config` class
2. Implement get/set/list methods
3. Add validation
4. Support legacy config migration

### Phase 2: Integration
1. Update `YumRepo` to use config object
2. Update main() to use config
3. Map CLI args to config keys
4. Test with both old and new configs

### Phase 3: Config Command
1. Add `yums3 config` subcommand
2. Implement get/set/list operations
3. Add --file, --global, --local, --system flags
4. Add --validate flag

### Phase 4: Documentation
1. Update README with config examples
2. Document all config keys
3. Migration guide for old configs
4. Man page for `yums3 config`

## Comparison with Alternatives

### vs Nested JSON
**Dot Notation:**
```json
{
  "backend.s3.bucket": "my-bucket"
}
```

**Nested:**
```json
{
  "backend": {
    "s3": {
      "bucket": "my-bucket"
    }
  }
}
```

**Advantages of Dot Notation:**
- Simpler to read/write programmatically
- No need to navigate nested structures
- Easier to query specific keys
- Git-style familiarity

### vs YAML
**Dot Notation JSON:**
```json
{
  "backend.s3.bucket": "my-bucket",
  "backend.s3.profile": "prod"
}
```

**YAML:**
```yaml
backend:
  s3:
    bucket: my-bucket
    profile: prod
```

**Advantages of Dot Notation JSON:**
- JSON is more universal (no YAML dependency)
- Simpler parsing (stdlib only)
- Less ambiguity (YAML has many gotchas)
- Easier to manipulate with standard tools

## Potential Issues and Solutions

### Issue 1: Key Naming Conflicts
**Problem:** What if someone wants a literal dot in a key?

**Solution:** Document that dots are reserved for hierarchy. Use underscores for word separation within a level (e.g., `backend.s3.bucket_name` not `backend.s3.bucket.name`).

### Issue 2: Type Inference
**Problem:** JSON stores everything as strings, numbers, booleans, or null. How to handle complex types?

**Solution:** 
- Use strings for most values
- Parse booleans: "true"/"false"
- Parse numbers where needed
- Use null for unset optional values

### Issue 3: Array Values
**Problem:** How to store lists (e.g., multiple buckets)?

**Solution:** 
- Use comma-separated strings: `"backend.s3.buckets": "bucket1,bucket2"`
- Or use indexed keys: `"backend.s3.bucket.0": "bucket1"`, `"backend.s3.bucket.1": "bucket2"`
- For now, we don't need arrays

### Issue 4: Comments
**Problem:** JSON doesn't support comments.

**Solution:**
- Use a `_comment` key: `"_comment.backend": "Production S3 settings"`
- Or use a separate `.yums3.conf.md` file for documentation
- Or support JSON5 format (allows comments)

## Recommendation

**Implement this design in phases:**

1. **Phase 1** (Now): Create config class, support dot notation, migrate legacy configs
2. **Phase 2** (Soon): Integrate with YumRepo, test thoroughly
3. **Phase 3** (Later): Add `yums3 config` command
4. **Phase 4** (Future): Add advanced features (--show-origin, --get-regexp, etc.)

This approach gives us:
- ✅ Clean, organized configuration
- ✅ Git-style familiarity
- ✅ Backward compatibility
- ✅ Easy to extend
- ✅ Simple to implement
- ✅ No external dependencies

The dot notation paradigm is excellent for this use case!
