# Configuration Namespace Analysis

## Problem Statement

Currently, both `yums3.py` (RPM) and `debs3.py` (Debian) share the same configuration structure, but some keys need to be repository-type-specific. The key `repo.cache_dir` is used by both but may need different values for RPM vs Debian repositories.

## Current Configuration Structure

### Shared Keys (Backend - Partially Shared)
Some backend keys are truly shared, others may need differentiation:

**Truly Shared (No Change Needed):**
- `backend.type` - Storage backend type (s3/local) - applies to both repo types

**May Need Differentiation:**
- `backend.s3.bucket` - S3 bucket name - **could be different per repo type**
- `backend.s3.profile` - AWS profile - **could be different per repo type**
- `backend.s3.endpoint` - S3 endpoint URL - **could be different per repo type**
- `backend.local.path` - Local storage path - **could be different per repo type**

**Rationale**: Organizations may want to:
- Use separate S3 buckets for RPM vs Debian repos
- Use different AWS profiles with different permissions
- Store repos in different local paths
- Use different S3 endpoints (regions) for different repo types

### Shared Keys (Behavior - No Change Needed)
These apply to both repository types:
- `validation.enabled` - Enable/disable validation
- `behavior.confirm` - Confirmation prompts
- `behavior.backup` - Backup before operations

### Keys That Need Differentiation

#### Currently Shared (Need Splitting)

1. **`backend.s3.bucket`** - S3 bucket name
   - Used by: `yums3.py` and `debs3.py`
   - **Issue**: Organizations may want separate buckets for RPM and Debian repos
   - **Example**: `rpm-packages` vs `deb-packages`

2. **`backend.s3.profile`** - AWS profile
   - Used by: `yums3.py` and `debs3.py`
   - **Issue**: Different profiles may have different permissions for different repo types
   - **Example**: `rpm-publisher` vs `deb-publisher`

3. **`backend.s3.endpoint`** - S3 endpoint URL
   - Used by: `yums3.py` and `debs3.py`
   - **Issue**: Different repos might be in different regions or S3-compatible services
   - **Example**: `https://s3.us-east-1.amazonaws.com` vs `https://s3.eu-west-1.amazonaws.com`

4. **`backend.local.path`** - Local storage path
   - Used by: `yums3.py` and `debs3.py`
   - **Issue**: Different local paths for different repo types
   - **Example**: `/srv/rpm-repo` vs `/srv/deb-repo`

5. **`repo.cache_dir`** - Cache directory for repository operations
   - Used by: `yums3.py` (default: `~/yum-repo`)
   - Used by: `debs3.py` (default: `~/deb-repo`)
   - **Issue**: Both tools may need different cache directories

#### Debian-Specific (Already Namespaced)
These are already properly namespaced under `debian.*`:
- `debian.default_distribution` - Default distribution (e.g., 'focal')
- `debian.default_component` - Default component (e.g., 'main')
- `debian.architectures` - Supported architectures (e.g., 'amd64 arm64')
- `debian.origin` - Repository origin
- `debian.label` - Repository label
- `debian.gpg_key` - GPG signing key path

#### RPM-Specific (Currently Not Namespaced)
Currently there are no RPM-specific config keys, but future additions might include:
- GPG signing configuration
- Repository metadata options
- Compression settings

## Proposed Solutions

### Option 1: Type-Prefixed Keys (Recommended)
Namespace repository-specific settings under the repo type:

```json
{
  "backend.type": "s3",
  "backend.rpm.s3.bucket": "rpm-packages",
  "backend.rpm.s3.profile": "rpm-publisher",
  "backend.deb.s3.bucket": "deb-packages",
  "backend.deb.s3.profile": "deb-publisher",
  
  "repo.rpm.cache_dir": "/var/cache/yums3",
  "repo.deb.cache_dir": "/var/cache/debs3",
  
  "debian.default_distribution": "focal",
  "debian.default_component": "main",
  "debian.architectures": "amd64 arm64"
}
```

**Alternative with shared defaults:**
```json
{
  "backend.type": "s3",
  "backend.s3.bucket": "shared-repo",        # Shared default
  "backend.rpm.s3.bucket": "rpm-packages",   # RPM override
  "backend.deb.s3.bucket": "deb-packages",   # Deb override
  
  "repo.rpm.cache_dir": "/var/cache/yums3",
  "repo.deb.cache_dir": "/var/cache/debs3"
}
```

**Pros:**
- Clear semantic grouping (repo.rpm.*, repo.deb.*)
- Allows for future repo-type-specific settings
- Maintains backward compatibility with fallback logic
- Consistent with existing `debian.*` namespace

**Cons:**
- Slightly longer key names

### Option 2: Top-Level Type Namespaces
Create top-level namespaces for each repo type:

```json
{
  "rpm.backend.type": "s3",
  "rpm.backend.s3.bucket": "rpm-packages",
  "rpm.backend.s3.profile": "rpm-publisher",
  "rpm.cache_dir": "/var/cache/yums3",
  
  "deb.backend.type": "s3",
  "deb.backend.s3.bucket": "deb-packages",
  "deb.backend.s3.profile": "deb-publisher",
  "deb.cache_dir": "/var/cache/debs3",
  "deb.default_distribution": "focal",
  "deb.default_component": "main",
  "deb.architectures": "amd64 arm64"
}
```

**Pros:**
- Shorter key names
- Clear separation at top level

**Cons:**
- Breaks existing `debian.*` namespace convention
- Less semantic (cache_dir is a repo property, not a type property)
- Would require migrating existing `debian.*` keys

### Option 3: Separate Config Files
Use completely separate config files for each repo type:

**yums3.conf:**
```json
{
  "backend.type": "s3",
  "backend.s3.bucket": "rpm-packages",
  "backend.s3.profile": "rpm-publisher",
  "repo.cache_dir": "/var/cache/yums3"
}
```

**debs3.conf:**
```json
{
  "backend.type": "s3",
  "backend.s3.bucket": "deb-packages",
  "backend.s3.profile": "deb-publisher",
  "repo.cache_dir": "/var/cache/debs3",
  "debian.default_distribution": "focal",
  "debian.default_component": "main"
}
```

**Pros:**
- Simplest approach - no namespace changes needed
- Clear separation of concerns
- Each tool has its own config

**Cons:**
- Duplicate configuration for shared settings
- Can't easily share backend configuration
- More files to manage

## Recommendation: Hybrid of Option 1 and Option 3

**Use namespaced keys with fallback to shared defaults**, allowing both shared and separate configurations:

```json
{
  "backend.type": "s3",
  
  # Shared backend (used if type-specific not set)
  "backend.s3.bucket": "shared-repo",
  "backend.s3.profile": "default",
  
  # Type-specific backend overrides
  "backend.rpm.s3.bucket": "rpm-packages",
  "backend.deb.s3.bucket": "deb-packages",
  
  # Type-specific repo settings
  "repo.rpm.cache_dir": "/var/cache/yums3",
  "repo.deb.cache_dir": "/var/cache/debs3",
  
  # Debian-specific settings
  "debian.default_distribution": "focal"
}
```

**Lookup order** (for yums3.py):
1. `backend.rpm.s3.bucket` (most specific)
2. `backend.s3.bucket` (shared fallback)
3. Default value

This approach provides maximum flexibility:
- **Shared config**: Set only `backend.s3.bucket` for both tools
- **Separate config**: Set `backend.rpm.s3.bucket` and `backend.deb.s3.bucket`
- **Mixed**: Share some settings, separate others

### Migration Strategy

1. **Add new namespaced keys** while maintaining backward compatibility:
   - `repo.cache_dir` → `repo.rpm.cache_dir` and `repo.deb.cache_dir`

2. **Lookup order** (for backward compatibility):
   ```python
   # For yums3.py - backend settings
   bucket = (config.get('backend.rpm.s3.bucket') or 
             config.get('backend.s3.bucket'))
   profile = (config.get('backend.rpm.s3.profile') or 
              config.get('backend.s3.profile'))
   endpoint = (config.get('backend.rpm.s3.endpoint') or 
               config.get('backend.s3.endpoint'))
   local_path = (config.get('backend.rpm.local.path') or 
                 config.get('backend.local.path'))
   
   # For yums3.py - repo settings
   cache_dir = (config.get('repo.rpm.cache_dir') or 
                config.get('repo.cache_dir', '~/yum-repo'))
   
   # For debs3.py - backend settings
   bucket = (config.get('backend.deb.s3.bucket') or 
             config.get('backend.s3.bucket'))
   profile = (config.get('backend.deb.s3.profile') or 
              config.get('backend.s3.profile'))
   endpoint = (config.get('backend.deb.s3.endpoint') or 
               config.get('backend.s3.endpoint'))
   local_path = (config.get('backend.deb.local.path') or 
                 config.get('backend.local.path'))
   
   # For debs3.py - repo settings
   cache_dir = (config.get('repo.deb.cache_dir') or 
                config.get('repo.cache_dir', '~/deb-repo'))
   ```

3. **Update defaults**:
   ```python
   DEFAULTS = {
       'backend.type': 's3',
       # Shared defaults (used if type-specific not set)
       'backend.s3.bucket': None,  # Must be configured
       'backend.s3.profile': None,
       'backend.s3.endpoint': None,
       'backend.local.path': None,
       # Type-specific defaults
       'repo.rpm.cache_dir': '~/yum-repo',
       'repo.deb.cache_dir': '~/deb-repo',
       # Behavior defaults
       'validation.enabled': True,
       'behavior.confirm': True,
       'behavior.backup': True,
   }
   ```

4. **Legacy migration** (add to LEGACY_KEY_MAP):
   ```python
   LEGACY_KEY_MAP = {
       # ... existing mappings ...
       'repo.cache_dir': 'repo.rpm.cache_dir',  # Default to RPM for backward compat
   }
   ```

## Affected Files

### Code Files
1. **`core/config.py`**
   - Update `DEFAULTS` dictionary
   - Update `LEGACY_KEY_MAP` for migration
   - Update validation logic if needed

2. **`yums3.py`**
   - Line 55: Change `config.get('repo.cache_dir')` to `config.get('repo.rpm.cache_dir')`
   - Add fallback logic for backward compatibility

3. **`debs3.py`**
   - Line 42: Change `config.get('repo.cache_dir')` to `config.get('repo.deb.cache_dir')`
   - Add fallback logic for backward compatibility

### Documentation Files
1. **`docs/USER_GUIDE.md`**
   - Update all `repo.cache_dir` references
   - Add examples for both `repo.rpm.cache_dir` and `repo.deb.cache_dir`

2. **`docs/CONFIG_COMMAND_REFERENCE.md`**
   - Update configuration key documentation
   - Add migration notes

3. **`docs/DEBIAN_SUPPORT_DESIGN.md`**
   - Update configuration examples
   - Change `repo.cache_dir` to `repo.deb.cache_dir`

4. **`docs/ARCHITECTURE.md`**
   - Update configuration structure documentation

### Test Files
1. **`tests/test_config.py`**
   - Update test cases to use new namespaced keys
   - Add tests for backward compatibility

2. **`tests/test_deb_repo.py`**
   - Update config setup to use `repo.deb.cache_dir`

3. **`tests/test_deduplication.py`**
   - Update config setup to use `repo.rpm.cache_dir`

4. **`tests/test_storage_backend.py`**
   - Update config setup if needed

## Future Considerations

### Potential Future RPM-Specific Keys
- `repo.rpm.gpg_key` - GPG signing key for RPM repos
- `repo.rpm.compression` - Compression type for metadata
- `repo.rpm.checksum_type` - Checksum algorithm (sha256, sha512)
- `repo.rpm.metadata_expire` - Metadata expiration time

### Potential Future Debian-Specific Keys
Already well-namespaced under `debian.*`:
- `debian.gpg_key` - GPG signing key
- `debian.compression` - Compression type
- `debian.suite` - Suite name

## Summary

**Keys requiring namespace changes:**
1. `backend.s3.bucket` → `backend.rpm.s3.bucket` / `backend.deb.s3.bucket` (with shared fallback)
2. `backend.s3.profile` → `backend.rpm.s3.profile` / `backend.deb.s3.profile` (with shared fallback)
3. `backend.s3.endpoint` → `backend.rpm.s3.endpoint` / `backend.deb.s3.endpoint` (with shared fallback)
4. `backend.local.path` → `backend.rpm.local.path` / `backend.deb.local.path` (with shared fallback)
5. `repo.cache_dir` → `repo.rpm.cache_dir` / `repo.deb.cache_dir` (with shared fallback)

**Keys that are fine as-is:**
- `backend.type` (truly shared - applies to both repo types)
- All `validation.*` keys (truly shared)
- All `behavior.*` keys (truly shared)
- All `debian.*` keys (already namespaced)

**Backward Compatibility:**
All existing configs will continue to work. The shared keys (e.g., `backend.s3.bucket`) will be used as fallbacks if type-specific keys are not set.

**Total impact:**
- 5 config keys need type-specific variants (with fallback support)
- 2 code files need updates (yums3.py, debs3.py)
- 1 core file needs updates (core/config.py)
- 1 helper function needs updates (create_storage_backend_from_config)
- 4+ documentation files need updates
- 4+ test files need updates

## Use Cases

### Use Case 1: Shared Backend
Both RPM and Debian repos in the same bucket:
```json
{
  "backend.type": "s3",
  "backend.s3.bucket": "my-packages",
  "repo.rpm.cache_dir": "/var/cache/yums3",
  "repo.deb.cache_dir": "/var/cache/debs3"
}
```

### Use Case 2: Separate Buckets
Different buckets for different repo types:
```json
{
  "backend.type": "s3",
  "backend.rpm.s3.bucket": "rpm-packages",
  "backend.deb.s3.bucket": "deb-packages",
  "repo.rpm.cache_dir": "/var/cache/yums3",
  "repo.deb.cache_dir": "/var/cache/debs3"
}
```

### Use Case 3: Different Regions
RPM in US, Debian in EU:
```json
{
  "backend.type": "s3",
  "backend.rpm.s3.bucket": "us-rpm-packages",
  "backend.rpm.s3.endpoint": "https://s3.us-east-1.amazonaws.com",
  "backend.deb.s3.bucket": "eu-deb-packages",
  "backend.deb.s3.endpoint": "https://s3.eu-west-1.amazonaws.com"
}
```

### Use Case 4: Different Profiles
Different AWS credentials for different repo types:
```json
{
  "backend.type": "s3",
  "backend.rpm.s3.bucket": "rpm-packages",
  "backend.rpm.s3.profile": "rpm-publisher",
  "backend.deb.s3.bucket": "deb-packages",
  "backend.deb.s3.profile": "deb-publisher"
}
```
