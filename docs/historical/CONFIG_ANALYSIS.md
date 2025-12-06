# Configuration Analysis and Formalization Proposal

## Current State Analysis

### 1. Naming Inconsistencies

**Problem:** The codebase uses S3-specific terminology even though it now supports multiple backends.

**Current Usage:**
- `s3_prefix` - Used throughout code to mean "repository path" (e.g., "el9/x86_64")
- `s3_bucket` - S3-specific, but concept applies to all storage
- `s3_rpms` - Variable name for RPMs from storage
- Method names still reference S3 in comments

**What it Actually Represents:**
- `s3_prefix` = Repository path within storage (el_version/arch)
- `s3_bucket` = Storage container/root
- `s3_rpms` = RPMs from any storage backend

### 2. Current Configuration Options

#### Config File Options (JSON)

**Storage Backend Selection:**
```json
{
  "storage_type": "s3" | "local"
}
```

**S3 Backend Options:**
```json
{
  "storage_type": "s3",
  "s3_bucket": "bucket-name",           // Required for S3
  "s3_endpoint_url": "https://...",     // Optional (for S3-compatible services)
  "aws_profile": "profile-name"         // Optional (defaults to 'default')
}
```

**Local Backend Options:**
```json
{
  "storage_type": "local",
  "local_storage_path": "/path/to/storage"  // Required for local
}
```

**Common Options:**
```json
{
  "local_repo_base": "/path/to/cache"  // Optional (defaults to ~/yum-repo)
}
```

#### Command-Line Arguments

**S3-Specific:**
- `-b, --bucket` - Override S3 bucket
- `--s3-endpoint-url` - Override S3 endpoint
- `--profile` - Override AWS profile

**Common:**
- `-d, --repo-dir` - Override local_repo_base
- `--config` - Specify config file
- `-y, --yes` - Skip confirmation
- `--remove` - Remove packages
- `--validate` - Validate repository
- `--no-validate` - Skip validation

### 3. Path Structure

**Current Pattern:**
```
{storage_root}/{el_version}/{arch}/
  ├── package1.rpm
  ├── package2.rpm
  └── repodata/
      ├── repomd.xml
      ├── *-primary.xml.gz
      ├── *-primary.sqlite.bz2
      └── ...
```

**Examples:**
- S3: `s3://my-bucket/el9/x86_64/`
- Local: `/tmp/storage/el9/x86_64/`

**The "prefix" concept:**
- Currently called `s3_prefix`
- Value: `"el9/x86_64"` (el_version/arch)
- Used to construct full paths

### 4. Configuration Precedence

**Current Order (highest to lowest):**
1. Command-line arguments
2. Config file (first found)
3. Default values

**Config File Search Order:**
1. `--config` argument path
2. `./yums3.conf`
3. `~/.yums3.conf`
4. `/etc/yums3.conf`

## Issues to Address

### 1. Terminology Mismatch
- Code uses `s3_prefix` but it's not S3-specific
- Variables named `s3_rpms` but they're from any storage
- Comments reference S3 when they mean storage

### 2. Configuration Complexity
- S3-specific CLI args (`--bucket`, `--s3-endpoint-url`)
- No generic way to specify storage backend from CLI
- Config structure is flat, not organized by backend

### 3. Missing Configuration Options
- No way to specify repository name/prefix from config
- No way to override storage backend from CLI
- No validation of required config per backend

### 4. Inconsistent Naming
- `local_repo_base` vs `local_storage_path` (both "local")
- `s3_bucket` vs `local_storage_path` (different concepts)

## Proposed Solutions

### Option 1: Minimal Renaming (Conservative)

**Rename variables/parameters:**
- `s3_prefix` → `repo_path` or `repo_prefix`
- `s3_rpms` → `storage_rpms` or just `rpms`
- `s3_bucket` → Keep for S3, but conceptually it's `storage_root`

**Pros:**
- Minimal code changes
- Backward compatible config format
- Easy to implement

**Cons:**
- Still has some S3-specific terminology
- Config structure remains flat

### Option 2: Structured Configuration (Moderate)

**Introduce a Config class:**
```python
class YumS3Config:
    def __init__(self, config_dict):
        self.storage_type = config_dict.get('storage_type', 's3')
        self.local_repo_base = config_dict.get('local_repo_base', '~/yum-repo')
        
        # Storage backend config
        if self.storage_type == 's3':
            self.storage_config = {
                'bucket_name': config_dict['s3_bucket'],
                'aws_profile': config_dict.get('aws_profile'),
                'endpoint_url': config_dict.get('s3_endpoint_url')
            }
        elif self.storage_type == 'local':
            self.storage_config = {
                'base_path': config_dict['local_storage_path']
            }
```

**Config file format (backward compatible):**
```json
{
  "storage_type": "s3",
  "s3_bucket": "my-bucket",
  "aws_profile": "default",
  "local_repo_base": "/tmp/cache"
}
```

**Pros:**
- Centralizes config logic
- Easier to validate
- Backward compatible

**Cons:**
- Still uses S3-specific keys in config file
- Doesn't fully solve naming issues

### Option 3: Fully Restructured Configuration (Comprehensive)

**New Config class with nested structure:**
```python
class YumS3Config:
    def __init__(self, config_dict):
        self.storage_type = config_dict.get('storage_type', 's3')
        self.cache_dir = config_dict.get('cache_dir', '~/yum-repo')
        
        # Parse storage backend config
        if 'storage' in config_dict:
            self.storage_config = config_dict['storage']
        else:
            # Backward compatibility
            self.storage_config = self._parse_legacy_config(config_dict)
    
    def _parse_legacy_config(self, config_dict):
        """Support old flat config format"""
        if self.storage_type == 's3':
            return {
                'bucket': config_dict.get('s3_bucket'),
                'profile': config_dict.get('aws_profile'),
                'endpoint': config_dict.get('s3_endpoint_url')
            }
        elif self.storage_type == 'local':
            return {
                'path': config_dict.get('local_storage_path')
            }
```

**New config file format:**
```json
{
  "storage_type": "s3",
  "cache_dir": "/tmp/cache",
  "storage": {
    "bucket": "my-bucket",
    "profile": "default",
    "endpoint": null
  }
}
```

**Or for local:**
```json
{
  "storage_type": "local",
  "cache_dir": "/tmp/cache",
  "storage": {
    "path": "/tmp/storage"
  }
}
```

**Backward compatible (old format still works):**
```json
{
  "storage_type": "s3",
  "s3_bucket": "my-bucket",
  "aws_profile": "default",
  "local_repo_base": "/tmp/cache"
}
```

**Pros:**
- Clean, organized structure
- Backend-specific config is nested
- Backward compatible
- Easier to extend

**Cons:**
- More complex implementation
- Two config formats to support

## Recommended Approach

### Phase 1: Rename Variables (Immediate)
- `s3_prefix` → `repo_path`
- `s3_rpms` → `rpms` or `storage_rpms`
- Update comments to be storage-agnostic

### Phase 2: Introduce Config Class (Next)
- Create `YumS3Config` class
- Support both old and new config formats
- Centralize validation

### Phase 3: Update CLI (Future)
- Add generic `--storage-path` argument
- Keep `--bucket` as alias for backward compatibility
- Add `--storage-type` argument

## Specific Naming Proposals

### Variables/Parameters
| Current | Proposed | Reason |
|---------|----------|--------|
| `s3_prefix` | `repo_path` | Not S3-specific, represents path in storage |
| `s3_rpms` | `rpms` | Simpler, context is clear |
| `s3_bucket_name` | Keep in S3Backend | It's backend-specific |
| `local_repo_base` | `cache_dir` | Clearer purpose |

### Config Keys
| Current | Proposed | Backward Compatible |
|---------|----------|---------------------|
| `s3_bucket` | `storage.bucket` | Yes (via legacy parser) |
| `local_storage_path` | `storage.path` | Yes (via legacy parser) |
| `local_repo_base` | `cache_dir` | Yes (check both) |
| `s3_endpoint_url` | `storage.endpoint` | Yes (via legacy parser) |
| `aws_profile` | `storage.profile` | Yes (via legacy parser) |

### Method Names
| Current | Proposed | Notes |
|---------|----------|-------|
| `_validate_quick(s3_prefix)` | `_validate_quick(repo_path)` | Parameter rename |
| `_validate_full(repo_dir, s3_prefix)` | `_validate_full(repo_dir, repo_path)` | Parameter rename |
| `_backup_metadata(repo_dir, s3_prefix)` | `_backup_metadata(repo_dir, repo_path)` | Parameter rename |
| `_restore_metadata(s3_prefix)` | `_restore_metadata(repo_path)` | Parameter rename |

## Questions for Discussion

1. **Naming preference for "s3_prefix":**
   - `repo_path` (my recommendation)
   - `repo_prefix`
   - `storage_path`
   - `repository_path`

2. **Config class approach:**
   - Option 1: Minimal (just rename variables)
   - Option 2: Config class with flat structure
   - Option 3: Config class with nested structure

3. **Backward compatibility:**
   - Must support old config format? (I recommend yes)
   - For how long? (I recommend indefinitely with deprecation warning)

4. **CLI arguments:**
   - Keep S3-specific args (`--bucket`)? (I recommend yes as aliases)
   - Add generic args (`--storage-path`)? (I recommend yes)

5. **Cache directory naming:**
   - Keep `local_repo_base`?
   - Rename to `cache_dir`?
   - Rename to `work_dir`?

## Implementation Priority

**High Priority (Do Now):**
1. Rename `s3_prefix` → `repo_path` throughout code
2. Update variable names (`s3_rpms` → `rpms`)
3. Update comments to be storage-agnostic

**Medium Priority (Do Soon):**
4. Create Config class
5. Support nested config format
6. Add validation

**Low Priority (Future):**
7. Add generic CLI arguments
8. Deprecation warnings for old config keys
9. Update documentation

## Example: Before and After

### Before (Current)
```python
def _validate_quick(self, s3_prefix):
    repomd_path = f"{s3_prefix}/repodata/repomd.xml"
    s3_rpms = set(self.storage.list_files(s3_prefix, suffix='.rpm'))
```

### After (Proposed)
```python
def _validate_quick(self, repo_path):
    repomd_path = f"{repo_path}/repodata/repomd.xml"
    rpms = set(self.storage.list_files(repo_path, suffix='.rpm'))
```

Much clearer and storage-agnostic!
