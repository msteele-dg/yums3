# Debian Repository Support Design

## Overview

Extend the yums3 architecture to support Debian/Ubuntu repositories using the same storage backends, configuration system, and CLI patterns.

## Goals

1. **Reuse Infrastructure**: Same storage backends (S3/Local), configuration, CLI patterns
2. **No Duplication**: Share .deb files across distributions, only metadata differs
3. **Consistent UX**: Same commands and workflows as yums3
4. **Debian Standards**: Follow Debian repository format specifications

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Layer                             │
│  debs3.py - Subcommands: add, remove, validate, config │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                 Core Components                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  DebRepo     │  │  RepoConfig  │  │   Colors     │ │
│  │  Manager     │  │  (shared)    │  │  (shared)    │ │
│  └──────┬───────┘  └──────────────┘  └──────────────┘ │
│         │                                                │
│  ┌──────▼───────────────────────────────────────┐      │
│  │    Storage Backend (shared)                  │      │
│  │  S3StorageBackend / LocalStorageBackend      │      │
│  └──────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              External Tools                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  dpkg-deb    │  │  apt-ftparch │  │    boto3     │ │
│  │  (metadata)  │  │  (optional)  │  │  (S3 client) │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Debian Repository Format

### Repository Structure

```
s3://bucket/
├── dists/
│   ├── focal/                    # Ubuntu 20.04
│   │   ├── main/
│   │   │   ├── binary-amd64/
│   │   │   │   ├── Packages
│   │   │   │   ├── Packages.gz
│   │   │   │   └── Packages.bz2
│   │   │   └── binary-arm64/
│   │   │       └── ...
│   │   ├── InRelease
│   │   ├── Release
│   │   └── Release.gpg
│   ├── jammy/                    # Ubuntu 22.04
│   │   └── ...
│   └── noble/                    # Ubuntu 24.04
│       └── ...
└── pool/
    └── main/
        ├── a/
        │   └── app-name/
        │       ├── app-name_1.0.0_amd64.deb
        │       └── app-name_1.0.1_amd64.deb
        └── b/
            └── ...
```

### Key Differences from YUM

| Aspect | YUM/RPM | Debian/APT |
|--------|---------|------------|
| Package location | Flat in repo dir | Pool structure |
| Metadata location | repodata/ | dists/codename/component/binary-arch/ |
| Metadata format | XML (primary, filelists, other) | RFC 822 (Packages) |
| Signing | Optional | Strongly recommended (Release.gpg) |
| Architecture | In filename | Separate directories |
| Compression | .gz, .bz2 | .gz, .bz2, .xz |

## Implementation Plan

### Phase 1: Core DebRepo Class

Create `debs3.py` with `DebRepo` class similar to `YumRepo`:

```python
class DebRepo:
    """Debian repository manager"""
    
    def __init__(self, config: RepoConfig):
        """Initialize with shared config"""
        self.config = config
        self.storage = create_storage_backend_from_config(config)
        self.cache_dir = config.get('repo.cache_dir')
    
    def add_packages(self, deb_files):
        """Add .deb packages to repository"""
        # 1. Detect distribution/component/arch from .deb
        # 2. Check for duplicates (same checksum)
        # 3. Copy to pool structure
        # 4. Update Packages file
        # 5. Update Release files
        pass
    
    def remove_packages(self, deb_names):
        """Remove packages from repository"""
        # 1. Find packages in pool
        # 2. Remove from Packages file
        # 3. Delete from pool
        # 4. Update Release files
        pass
    
    def validate_repository(self, distribution, component, arch):
        """Validate repository integrity"""
        # 1. Verify checksums in Release
        # 2. Verify packages in Packages exist
        # 3. Verify no orphaned packages
        pass
```

### Phase 2: Package Detection

Extract metadata from .deb files:

```python
def _detect_from_deb(self, deb_file):
    """Extract distribution, component, architecture from .deb
    
    Returns:
        tuple: (distribution, component, architecture)
    """
    # Use dpkg-deb to extract control file
    result = subprocess.run(
        ['dpkg-deb', '-f', deb_file, 'Architecture', 'Distribution', 'Component'],
        capture_output=True, text=True
    )
    
    # Parse output
    arch = extract_field(result.stdout, 'Architecture')
    distribution = extract_field(result.stdout, 'Distribution') or 'focal'
    component = extract_field(result.stdout, 'Component') or 'main'
    
    return distribution, component, arch
```

### Phase 3: Pool Management

Organize packages in pool structure:

```python
def _get_pool_path(self, package_name, deb_file):
    """Get pool path for package
    
    Args:
        package_name: Name of package (e.g., 'myapp')
        deb_file: Path to .deb file
    
    Returns:
        str: Pool path (e.g., 'pool/main/m/myapp/myapp_1.0.0_amd64.deb')
    """
    # Get first letter of package name
    prefix = package_name[0].lower()
    
    # Special case for lib* packages
    if package_name.startswith('lib'):
        prefix = f"lib{package_name[3]}" if len(package_name) > 3 else 'lib'
    
    component = 'main'  # Could be extracted from package
    filename = os.path.basename(deb_file)
    
    return f"pool/{component}/{prefix}/{package_name}/{filename}"
```

### Phase 4: Metadata Generation

Generate Packages file:

```python
def _generate_packages_file(self, distribution, component, arch):
    """Generate Packages file for distribution/component/arch
    
    Returns:
        str: Path to generated Packages file
    """
    packages_content = []
    
    # List all .deb files in pool for this arch
    pool_files = self._list_pool_packages(component, arch)
    
    for deb_file in pool_files:
        # Extract package metadata
        control = self._extract_control(deb_file)
        
        # Calculate checksums
        md5sum = self._calculate_md5(deb_file)
        sha1sum = self._calculate_sha1(deb_file)
        sha256sum = self._calculate_sha256(deb_file)
        size = os.path.getsize(deb_file)
        
        # Build package entry
        entry = f"""Package: {control['Package']}
Version: {control['Version']}
Architecture: {control['Architecture']}
Maintainer: {control['Maintainer']}
Installed-Size: {control.get('Installed-Size', '0')}
Depends: {control.get('Depends', '')}
Filename: {self._get_pool_path(control['Package'], deb_file)}
Size: {size}
MD5sum: {md5sum}
SHA1: {sha1sum}
SHA256: {sha256sum}
Description: {control.get('Description', '')}

"""
        packages_content.append(entry)
    
    # Write Packages file
    packages_file = f"dists/{distribution}/{component}/binary-{arch}/Packages"
    with open(packages_file, 'w') as f:
        f.write(''.join(packages_content))
    
    # Compress
    self._compress_file(packages_file, 'gz')
    self._compress_file(packages_file, 'bz2')
    
    return packages_file
```

### Phase 5: Release File Generation

Generate Release and InRelease files:

```python
def _generate_release_file(self, distribution):
    """Generate Release file for distribution
    
    Args:
        distribution: Distribution name (e.g., 'focal')
    """
    # Collect all Packages files
    packages_files = self._find_packages_files(distribution)
    
    # Calculate checksums for each
    md5sums = []
    sha1sums = []
    sha256sums = []
    
    for pkg_file in packages_files:
        relative_path = pkg_file.replace(f"dists/{distribution}/", "")
        size = os.path.getsize(pkg_file)
        
        md5sums.append(f" {self._calculate_md5(pkg_file)} {size:8d} {relative_path}")
        sha1sums.append(f" {self._calculate_sha1(pkg_file)} {size:8d} {relative_path}")
        sha256sums.append(f" {self._calculate_sha256(pkg_file)} {size:8d} {relative_path}")
    
    # Build Release file
    release_content = f"""Origin: MyRepo
Label: MyRepo
Suite: {distribution}
Codename: {distribution}
Date: {datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S UTC')}
Architectures: amd64 arm64
Components: main
Description: My Debian Repository
MD5Sum:
{chr(10).join(md5sums)}
SHA1:
{chr(10).join(sha1sums)}
SHA256:
{chr(10).join(sha256sums)}
"""
    
    # Write Release file
    release_file = f"dists/{distribution}/Release"
    with open(release_file, 'w') as f:
        f.write(release_content)
    
    # Generate InRelease (signed inline)
    # This would use GPG signing if configured
    
    return release_file
```

## Configuration

### Shared Configuration Keys

Reuse existing RepoConfig with Debian-specific additions:

```json
{
  "backend.type": "s3",
  "backend.s3.bucket": "my-repo",
  "backend.s3.profile": "default",
  "repo.cache_dir": "/var/cache/debs3",
  
  "debian.default_distribution": "focal",
  "debian.default_component": "main",
  "debian.architectures": ["amd64", "arm64"],
  "debian.origin": "MyRepo",
  "debian.label": "MyRepo",
  "debian.gpg_key": "/path/to/key.gpg"
}
```

### Configuration Commands

```bash
# Configure Debian-specific options
./debs3.py config debian.default_distribution focal
./debs3.py config debian.default_component main
./debs3.py config debian.architectures "amd64 arm64"
```

## CLI Interface

### Commands

```bash
# Add packages
./debs3.py add package.deb
./debs3.py add pkg1.deb pkg2.deb pkg3.deb
./debs3.py add --distribution focal --component main package.deb

# Remove packages
./debs3.py remove package-name
./debs3.py remove package-name_1.0.0_amd64

# Validate repository
./debs3.py validate focal main amd64

# Configuration
./debs3.py config --list
./debs3.py config debian.default_distribution jammy
```

### Global Options

Same as yums3:
```bash
--config CONFIG       # Path to config file
--bucket BUCKET       # S3 bucket (overrides config)
--cache-dir DIR       # Cache directory (overrides config)
--profile PROFILE     # AWS profile (overrides config)
```

## Deduplication Strategy

### Same as YUM

1. Calculate checksum of .deb file
2. Check if package with same checksum exists in pool
3. If exists, skip upload
4. If different checksum, update

### Pool Structure Benefits

- Packages stored once in pool
- Multiple distributions can reference same package
- Deduplication happens naturally

Example:
```
pool/main/m/myapp/
├── myapp_1.0.0_amd64.deb  # Used by focal, jammy, noble
└── myapp_1.0.1_amd64.deb  # Used by jammy, noble only
```

## Metadata Merging

### Adding Packages

1. Download existing Packages file
2. Parse existing entries
3. Add new package entries
4. Sort by package name
5. Write updated Packages file
6. Compress (gz, bz2)
7. Update Release file with new checksums

### Removing Packages

1. Download existing Packages file
2. Parse and remove matching entries
3. Write updated Packages file
4. Compress
5. Update Release file
6. Delete from pool if not referenced by other distributions

## Validation

### Checks

1. **Release File Integrity**
   - Verify checksums in Release match actual files
   - Verify all referenced files exist

2. **Packages File Integrity**
   - Verify all packages in Packages exist in pool
   - Verify checksums match

3. **Pool Integrity**
   - No orphaned packages (in pool but not in any Packages file)
   - All packages have valid metadata

4. **Signature Validation** (if GPG configured)
   - Verify Release.gpg signature
   - Verify InRelease signature

## Client Configuration

### APT Sources

```bash
# /etc/apt/sources.list.d/myrepo.list
deb https://my-bucket.s3.amazonaws.com/ focal main
deb https://my-bucket.s3.amazonaws.com/ jammy main
```

### With GPG Key

```bash
# Add GPG key
curl https://my-bucket.s3.amazonaws.com/key.gpg | sudo apt-key add -

# Or with signed-by
deb [signed-by=/usr/share/keyrings/myrepo.gpg] https://my-bucket.s3.amazonaws.com/ focal main
```

## Implementation Checklist

### Phase 1: Core Structure
- [ ] Create debs3.py
- [ ] Create DebRepo class
- [ ] Implement package detection
- [ ] Implement pool path calculation

### Phase 2: Basic Operations
- [ ] Implement add_packages()
- [ ] Implement remove_packages()
- [ ] Implement Packages file generation
- [ ] Implement Release file generation

### Phase 3: Advanced Features
- [ ] Implement deduplication
- [ ] Implement validation
- [ ] Implement backup/recovery
- [ ] Add GPG signing support

### Phase 4: Testing
- [ ] Create test .deb packages
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Test with real APT clients

### Phase 5: Documentation
- [ ] User guide for debs3
- [ ] Configuration reference
- [ ] Migration guide
- [ ] Architecture documentation

## Code Reuse

### Shared Components

1. **Storage Backends** (`core/backend.py`)
   - S3StorageBackend
   - LocalStorageBackend
   - No changes needed

2. **Configuration** (`core/config.py`)
   - RepoConfig class
   - Just add Debian-specific keys
   - Same config command

3. **Colors** (`core/__init__.py`)
   - Terminal output formatting
   - No changes needed

4. **CLI Patterns**
   - Same subcommand structure
   - Same global options
   - Same confirmation flow

### New Components

1. **DebRepo Class** (`debs3.py`)
   - Debian-specific logic
   - Similar structure to YumRepo

2. **Debian Metadata** (in debs3.py)
   - Packages file generation
   - Release file generation
   - Control file parsing

## Testing Strategy

### Test Packages

Create simple test .deb packages:

```bash
# Create test package structure
mkdir -p test-package/DEBIAN
cat > test-package/DEBIAN/control <<EOF
Package: test-package
Version: 1.0.0
Architecture: amd64
Maintainer: Test <test@example.com>
Description: Test package
EOF

# Build .deb
dpkg-deb --build test-package
```

### Test Suite

```python
# tests/test_deb_repo.py
def test_add_package():
    """Test adding Debian package"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.local.path', tmpdir)
        
        repo = DebRepo(config)
        repo.add_packages(['test-package_1.0.0_amd64.deb'])
        
        # Verify package in pool
        assert os.path.exists(f"{tmpdir}/pool/main/t/test-package/test-package_1.0.0_amd64.deb")
        
        # Verify Packages file
        assert os.path.exists(f"{tmpdir}/dists/focal/main/binary-amd64/Packages")
```

## Migration Path

### For Existing Users

1. Install debs3.py alongside yums3.py
2. Use same configuration file
3. Same storage backend
4. Different repository paths (no conflict)

### Unified Tool (Future)

Could create unified `repos3.py`:

```bash
# Auto-detect package type
./repos3.py add package.rpm    # Uses YumRepo
./repos3.py add package.deb    # Uses DebRepo

# Or explicit
./repos3.py yum add package.rpm
./repos3.py deb add package.deb
```

## Benefits

1. **Code Reuse**: 60%+ code shared with yums3
2. **Consistent UX**: Same commands, same workflows
3. **Unified Storage**: One S3 bucket for both RPM and DEB
4. **Proven Architecture**: Leverage tested storage/config layers
5. **Easy Maintenance**: Changes to storage benefit both

## Challenges

1. **Debian Complexity**: More complex metadata format
2. **Pool Structure**: Different file organization
3. **GPG Signing**: More important for Debian repos
4. **Multiple Distributions**: Need to handle focal, jammy, noble, etc.

## Success Criteria

- [ ] Can add .deb packages to repository
- [ ] Can remove .deb packages from repository
- [ ] Can validate repository integrity
- [ ] Deduplication works correctly
- [ ] APT clients can install packages
- [ ] All tests pass
- [ ] Documentation complete

## Timeline Estimate

- **Phase 1** (Core Structure): 2-3 days
- **Phase 2** (Basic Operations): 3-4 days
- **Phase 3** (Advanced Features): 2-3 days
- **Phase 4** (Testing): 2-3 days
- **Phase 5** (Documentation): 1-2 days

**Total**: 10-15 days for complete implementation

## Next Steps

1. Review this design
2. Create debs3.py skeleton
3. Implement Phase 1 (core structure)
4. Create test .deb packages
5. Implement Phase 2 (basic operations)
6. Test with real APT client

Would you like me to start implementing Phase 1?
