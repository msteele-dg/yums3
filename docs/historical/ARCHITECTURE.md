# yums3 Architecture

## Overview

yums3 is a Python-based YUM repository manager designed for efficient package management with pluggable storage backends. It supports both S3 and local filesystem storage, with intelligent deduplication and comprehensive validation.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                            │
│  (yums3.py - Subcommands: add, remove, validate, config)   │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                    Core Components                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   YumRepo    │  │  RepoConfig  │  │   Colors     │     │
│  │   Manager    │  │   Manager    │  │   Output     │     │
│  └──────┬───────┘  └──────────────┘  └──────────────┘     │
│         │                                                    │
│  ┌──────▼───────────────────────────────────────┐          │
│  │         Storage Backend Interface            │          │
│  │  (Abstract: StorageBackend)                  │          │
│  └──────┬───────────────────────────────────────┘          │
│         │                                                    │
│  ┌──────▼──────────┐         ┌──────────────────┐          │
│  │ S3Storage       │         │ LocalStorage     │          │
│  │ Backend         │         │ Backend          │          │
│  └─────────────────┘         └──────────────────┘          │
└─────────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                  External Tools                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ createrepo_c │  │    lxml      │  │    boto3     │     │
│  │ (metadata)   │  │  (XML parse) │  │  (S3 client) │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. CLI Layer (`yums3.py`)

**Purpose:** Command-line interface and orchestration

**Subcommands:**
- `add` - Add packages to repository
- `remove` - Remove packages from repository
- `validate` - Validate repository integrity
- `config` - Manage configuration

**Responsibilities:**
- Parse command-line arguments
- Load configuration
- Initialize YumRepo with appropriate backend
- Handle user confirmation
- Display results

**Key Functions:**
- `main()` - Entry point, argument parsing
- `config_command()` - Handle config subcommand

### 2. YumRepo Class (`yums3.py`)

**Purpose:** Core repository management logic

**Key Methods:**

#### Package Operations
- `add_packages(rpm_files)` - Add packages with deduplication
- `remove_packages(rpm_filenames)` - Remove packages
- `_init_repo()` - Initialize new repository
- `_add_to_existing_repo()` - Add to existing repository

#### Metadata Operations
- `_merge_metadata()` - Merge new metadata into existing
- `_manipulate_metadata()` - Remove packages from metadata
- `_add_database_to_repomd()` - Add SQLite database entries

#### Deduplication
- `_get_existing_package_checksums()` - Extract checksums from metadata
- `_calculate_rpm_checksum()` - Calculate RPM checksum

#### Validation
- `validate_repository()` - Full validation
- `_validate_quick()` - Quick checksum validation
- `_validate_full()` - Comprehensive validation

#### Backup/Recovery
- `_backup_metadata()` - Create metadata backup
- `_restore_metadata()` - Restore from backup
- `_cleanup_backup()` - Remove backup after success

#### Utilities
- `_detect_from_rpm()` - Detect arch/version from RPM
- `_detect_from_filename()` - Detect from filename
- `_prepare_repo_dir()` - Prepare local directory
- `_repo_exists()` - Check if repo exists in storage

### 3. Storage Backend (`core/backend.py`)

**Purpose:** Abstract storage operations for different backends

**Architecture:**
```
StorageBackend (Abstract Base Class)
    ├── S3StorageBackend
    └── LocalStorageBackend
```

**Interface Methods:**
- `exists(path)` - Check if file exists
- `download_file(remote, local)` - Download single file
- `upload_file(local, remote)` - Upload single file
- `delete_file(path)` - Delete file
- `list_files(prefix, suffix)` - List files
- `sync_from_storage(remote, local)` - Sync directory from storage
- `sync_to_storage(local, remote)` - Sync directory to storage
- `get_url()` - Get display URL
- `download_file_content(path)` - Download to memory
- `copy_file(src, dst)` - Copy within storage
- `get_info()` - Get backend information for display

**S3StorageBackend:**
- Uses boto3 for S3 operations
- Supports custom endpoints (S3-compatible services)
- Efficient copy_object for internal copies
- Retrieves AWS account/region information

**LocalStorageBackend:**
- Uses filesystem operations
- Useful for testing and local development
- Simpler implementation

### 4. Configuration (`core/config.py`)

**Purpose:** Git-style configuration management

**RepoConfig Class:**

**Features:**
- Dot notation keys (e.g., `backend.s3.bucket`)
- Multiple config file locations (local, user, system)
- Default values
- Automatic legacy migration
- Validation

**Key Methods:**
- `get(key, default)` - Get config value
- `set(key, value)` - Set config value
- `unset(key)` - Remove config key
- `list_all()` - List all config
- `get_section(prefix)` - Get keys by prefix
- `validate()` - Validate configuration
- `save()` - Save to file

**Configuration Schema:**
```
backend.type                 # "s3" or "local"
backend.s3.bucket           # S3 bucket name
backend.s3.profile          # AWS profile
backend.s3.endpoint         # S3 endpoint URL
backend.local.path          # Local storage path
repo.cache_dir              # Cache directory
validation.enabled          # Enable validation
behavior.confirm            # Require confirmation
behavior.backup             # Create backups
```

### 5. SQLite Metadata (`core/sqlite_metadata.py`)

**Purpose:** Generate SQLite databases from XML metadata

**SQLiteMetadataManager Class:**

**Features:**
- Creates primary_db, filelists_db, other_db
- Proper schema matching DNF expectations
- Compression (bz2)
- Validation

**Key Methods:**
- `create_all_databases()` - Create all DB types
- `create_primary_db()` - Create primary database
- `create_filelists_db()` - Create filelists database
- `create_other_db()` - Create other database
- `compress_sqlite()` - Compress with bz2

## Data Flow

### Adding Packages

```
1. User runs: yums3 add package.rpm
                │
2. Parse args, load config
                │
3. Detect arch/version from RPM
                │
4. Check if repo exists
                │
        ┌───────┴───────┐
        │               │
    New Repo      Existing Repo
        │               │
5a. Init repo    5b. Check duplicates
    - createrepo_c      │
    - Upload RPMs   ┌───┴───┐
    - Upload metadata   │       │
                    Skip    Add
                        │
                6. Download metadata
                        │
                7. Create temp repo
                        │
                8. Merge metadata
                        │
                9. Create SQLite DBs
                        │
                10. Upload packages
                        │
                11. Upload metadata
                        │
                12. Validate (optional)
```

### Deduplication Logic

```
For each package being added:
    │
    ├─ Calculate checksum
    │
    ├─ Check if filename exists in repo
    │
    ├─ If exists:
    │   ├─ Compare checksums
    │   │
    │   ├─ If same: SKIP (duplicate)
    │   │
    │   └─ If different: ADD (update)
    │
    └─ If not exists: ADD (new)

If all packages skipped:
    └─ Return early (no metadata regeneration)
```

### Metadata Merge Process

```
1. Parse existing repomd.xml
   └─ Find primary.xml.gz, filelists.xml.gz, other.xml.gz

2. Parse new metadata (from createrepo_c)
   └─ Extract package entries

3. Merge XML trees
   ├─ Add new package elements
   ├─ Update package counts
   └─ Preserve namespaces

4. Regenerate checksums
   └─ Update repomd.xml with new checksums

5. Create SQLite databases
   └─ Add database entries to repomd.xml

6. Write all files
```

## Storage Layout

### S3 Structure
```
s3://bucket-name/
├── el9/
│   ├── x86_64/
│   │   ├── package1.rpm
│   │   ├── package2.rpm
│   │   └── repodata/
│   │       ├── repomd.xml
│   │       ├── <checksum>-primary.xml.gz
│   │       ├── <checksum>-primary_db.sqlite.bz2
│   │       ├── <checksum>-filelists.xml.gz
│   │       ├── <checksum>-filelists_db.sqlite.bz2
│   │       ├── <checksum>-other.xml.gz
│   │       └── <checksum>-other_db.sqlite.bz2
│   └── aarch64/
│       └── ...
└── el8/
    └── ...
```

### Local Cache Structure
```
~/.cache/yums3/  (or configured cache_dir)
├── el9/
│   └── x86_64/
│       └── repodata/
│           └── (downloaded metadata)
└── el8/
    └── ...
```

### Backup Structure
```
s3://bucket-name/el9/x86_64/
└── repodata.backup-YYYYMMDD-HHMMSS/
    ├── repomd.xml
    ├── <checksum>-primary.xml.gz
    └── ...
```

## Key Design Decisions

### 1. Pluggable Storage Backends

**Why:** Flexibility for different deployment scenarios
- S3 for production
- Local for testing/development
- Easy to add new backends (Azure, GCS, etc.)

**Implementation:** Abstract base class with concrete implementations

### 2. Metadata Manipulation vs Full Regeneration

**Why:** Efficiency - avoid downloading all RPMs
- Only download metadata (~few MB)
- Merge new package entries
- Much faster than full regeneration

**Trade-off:** More complex code, but significant performance gain

### 3. Automatic Deduplication

**Why:** Idempotent operations, CI/CD friendly
- Safe to re-run builds
- Reduces unnecessary uploads
- 92% faster for duplicate operations

**Implementation:** Checksum comparison before adding

### 4. Git-Style Configuration

**Why:** Familiar interface for DevOps teams
- Works like `git config`
- Dot notation for hierarchy
- Multiple config locations

**Benefits:** Easy to use, scriptable, version-controllable

### 5. Backup and Recovery

**Why:** Safety - metadata corruption can break repository
- Automatic backups before changes
- Automatic restore on failure
- Manual restore capability

**Implementation:** Timestamped backup directories

### 6. SQLite Database Generation

**Why:** DNF performance
- Faster queries than XML parsing
- Lower memory usage
- Better user experience

**Implementation:** Generate from XML, compress with bz2

## Performance Characteristics

### Time Complexity

| Operation | First Time | Duplicate | Update |
|-----------|-----------|-----------|--------|
| Add 1 package | O(n) | O(1) | O(n) |
| Add 10 packages | O(n) | O(1) | O(n) |
| Remove 1 package | O(n) | - | - |
| Validate | O(n) | - | - |

Where n = number of packages in repository

### Space Complexity

| Component | Space |
|-----------|-------|
| Local cache | ~10MB per repo |
| Metadata | ~1MB per 1000 packages |
| SQLite DBs | ~2MB per 1000 packages |
| Backup | Same as metadata |

### Network Operations

| Operation | Downloads | Uploads |
|-----------|-----------|---------|
| Add (new) | Metadata only | RPMs + Metadata |
| Add (duplicate) | Metadata only | None |
| Remove | Metadata only | Metadata only |
| Validate | Metadata only | None |

## Error Handling

### Strategy

1. **Validation First:** Validate inputs before operations
2. **Backup Before Changes:** Always backup metadata
3. **Automatic Recovery:** Restore on failure
4. **Graceful Degradation:** Continue if non-critical features fail
5. **Clear Error Messages:** Help users understand what went wrong

### Recovery Mechanisms

1. **Metadata Backup:** Automatic restore on failure
2. **Manual Restore:** Backup retained for inspection
3. **Validation:** Detect issues early
4. **Idempotent Operations:** Safe to retry

## Security Considerations

### AWS Credentials

- Uses standard AWS credential chain
- Supports profiles for multi-account
- No credentials stored in code
- IAM roles recommended for EC2

### Package Integrity

- SHA256 checksums for all packages
- Checksum validation in metadata
- Optional GPG signing (external)

### Access Control

- S3 bucket policies control access
- IAM policies for fine-grained control
- Support for private repositories

## Extensibility

### Adding New Storage Backends

1. Subclass `StorageBackend`
2. Implement all abstract methods
3. Add to `create_storage_backend_from_config()`
4. Update configuration schema

Example:
```python
class AzureBlobStorageBackend(StorageBackend):
    def __init__(self, container_name, account_name):
        # Initialize Azure client
        pass
    
    def exists(self, path):
        # Check if blob exists
        pass
    
    # Implement other methods...
```

### Adding New Commands

1. Add subparser in `main()`
2. Implement command handler
3. Add tests
4. Update documentation

### Adding Configuration Options

1. Add to `RepoConfig.DEFAULTS`
2. Add validation in `RepoConfig.validate()`
3. Use in relevant code
4. Update documentation

## Testing Strategy

### Unit Tests
- Individual methods
- Mock external dependencies
- Fast execution

### Integration Tests
- Full workflows
- LocalStorageBackend for speed
- Real RPM files

### Test Coverage
- Core functionality: 100%
- Edge cases: Comprehensive
- Error paths: Covered

## Dependencies

### Required
- Python 3.6+
- boto3 (for S3)
- lxml (for XML parsing)
- createrepo_c (for metadata generation)

### Optional
- dnf (for validation testing)

## Future Enhancements

### Planned
- Phase 2: Repodata cleanup (remove orphaned files)
- Parallel uploads for large batches
- Delta RPM support
- Repository signing

### Possible
- Web UI for repository management
- Metrics and monitoring
- Multi-region replication
- CDN integration

## References

- [YUM Repository Format](https://docs.fedoraproject.org/en-US/quick-docs/repositories/)
- [createrepo_c Documentation](https://github.com/rpm-software-management/createrepo_c)
- [DNF Documentation](https://dnf.readthedocs.io/)
- [RPM Metadata](http://yum.baseurl.org/wiki/RepoMetadata)
