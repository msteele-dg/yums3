# yums3 - S3-Backed YUM/DEB Repository Manager

A lightweight Python tool for managing YUM/DNF and DEB package repositories hosted on Amazon S3 (or S3-compatible storage). Designed for efficient package publishing without requiring full repository downloads.

## Features

- **Efficient Updates**: Add or remove packages without downloading existing RPMs/DEBs
- **Metadata Manipulation**: Direct XML manipulation for fast operations
- **SQLite Database Support**: Creates and maintains SQLite metadata for faster DNF/YUM queries
- **S3 Native**: Built for S3-backed repositories with pluggable local backend for testing
- **Auto-Detection**: Automatically detects architecture and distro version from packages
- **Validation**: Built-in repository integrity checks (XML + SQLite databases)
- **Type-Specific Config**: Separate configuration per repo type (RPM vs DEB) with shared fallbacks
- **Package Replication**: Replicate packages between distro versions (e.g., el9 to el10)
- **Automatic Backups**: Metadata is backed up before changes and restored on failure

## Setup

### Prerequisites

- Python 3.6+
- AWS credentials configured (via `~/.aws/credentials`, environment variables, or IAM role)

### Installation

```bash
make setup-venv
source ~/.venv/yums3/bin/activate
```

This installs system dependencies (`createrepo_c`, `rpm`, etc.) using the appropriate package manager for your OS (brew on macOS, apt on Debian/Ubuntu, dnf on RHEL/Rocky), then creates a Python virtual environment and installs the Python dependencies (`boto3`, `lxml`).

## Configuration

Configuration uses a flat JSON format with dot-notated keys. Files are searched in order:

1. `./dg-repos.conf` (local directory)
2. `~/.dg-repos.conf` (user home)
3. `/etc/dg-repos.conf` (system-wide)

### Setting Config Values

```bash
./yums3.py config backend.type s3
./yums3.py config backend.s3.bucket my-company-yum-repo
./yums3.py config backend.s3.profile production
./yums3.py config repo.cache_dir /tmp/yum-cache
```

### Listing Config

```bash
./yums3.py config --list
```

### Type-Specific Configuration

Config keys support per-type overrides. For a key like `backend.s3.bucket`, the lookup order is:

1. `backend.rpm.s3.bucket` (type-specific, when running yums3)
2. `backend.s3.bucket` (shared fallback)
3. Default value

This lets RPM and DEB repos use different S3 buckets, AWS profiles, cache directories, etc. while sharing a single config file:

```json
{
  "backend.type": "s3",
  "backend.s3.bucket": "shared-bucket",
  "backend.rpm.s3.bucket": "rpm-only-bucket",
  "backend.deb.s3.bucket": "deb-only-bucket",
  "backend.s3.profile": "production"
}
```

### CLI Overrides

Command-line arguments override config file values:

```bash
./yums3.py --bucket other-bucket add my-package.rpm
./yums3.py --cache-dir /tmp/custom-cache add my-package.rpm
./yums3.py --profile production add my-package.rpm
./yums3.py --s3-endpoint-url https://s3.us-west-2.amazonaws.com add my-package.rpm
```

### Default Values

| Key | Default |
|---|---|
| `backend.type` | `s3` |
| `repo.rpm.cache_dir` | `~/yum-repo` |
| `repo.deb.cache_dir` | `~/deb-repo` |
| `validation.enabled` | `true` |
| `behavior.confirm` | `true` |
| `behavior.backup` | `true` |

## Usage - YUM Repositories (yums3.py)

### Adding Packages

```bash
# Single package
./yums3.py add my-package-1.0.0-1.el9.x86_64.rpm

# Multiple packages
./yums3.py add package1.rpm package2.rpm package3.rpm

# Glob patterns
./yums3.py add /tmp/rpmbuild/RPMS/x86_64/*.rpm

# Skip confirmation (CI/CD)
./yums3.py add -y my-package.rpm
```

### Removing Packages

```bash
./yums3.py remove my-package-1.0.0-1.el9.x86_64.rpm
./yums3.py remove -y old-package1.rpm old-package2.rpm
```

### Validating a Repository

```bash
./yums3.py validate el9/x86_64
```

### Replicating Packages Between Distros

```bash
./yums3.py replicate --src el9 --dst el10 libtorch myapp
./yums3.py replicate --src el9 --dst el10 --arch aarch64 -y myapp
```

### Skip Post-Operation Validation

```bash
./yums3.py add --no-validate my-package.rpm
./yums3.py remove --no-validate old-package.rpm
```

## Usage - DEB Repositories (debs3.py)

### Adding Packages

```bash
./debs3.py add my-package_1.0.0_amd64.deb
./debs3.py add -y package1.deb package2.deb
./debs3.py add --distribution noble --component main my-package.deb
```

### Removing Packages

```bash
./debs3.py remove my-package
./debs3.py remove --distribution focal --component main --architecture amd64 my-package
```

### Validating a Repository

```bash
./debs3.py validate focal main amd64
```

### Replicating Packages Between Distributions

```bash
./debs3.py replicate --src focal --dst noble my-package
./debs3.py replicate --src focal --dst noble --component main --arch amd64 -y my-package
```

## How It Works

### YUM Repository Structure (S3)

```
s3://your-bucket/
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

### DEB Repository Structure (S3)

```
s3://your-bucket/
├── dists/
│   └── focal/
│       ├── Release
│       └── main/
│           └── binary-amd64/
│               ├── Packages
│               ├── Packages.gz
│               └── Packages.bz2
└── pool/
    └── main/
        └── m/
            └── myapp/
                └── myapp_1.0.0_amd64.deb
```

### Metadata Operations

Instead of downloading all packages to regenerate metadata, the tool directly manipulates metadata XML/control files:

**Adding**: Downloads metadata only, generates metadata for new packages in a temp dir, merges XML trees, recalculates checksums, creates SQLite databases, and uploads.

**Removing**: Downloads metadata only, parses XML, removes package entries, updates checksums and SQLite databases, uploads modified metadata, deletes packages from S3.

### Automatic Backups

Before any metadata changes, a timestamped backup is created in S3. On success the backup is cleaned up. On failure, metadata is automatically restored from the backup.

### Deduplication

When adding packages, the tool checks checksums against existing packages. Exact duplicates are skipped, same-name packages with different checksums are updated.

## Client Configuration

### Public S3 Bucket

```bash
sudo tee /etc/yum.repos.d/my-repo.repo <<EOF
[my-repo]
name=My Repository
baseurl=https://your-bucket.s3.amazonaws.com/el\$releasever/\$basearch
enabled=1
gpgcheck=0
EOF

sudo dnf makecache
```

### Private S3 Bucket (IAM Roles)

```bash
sudo dnf install python3-dnf-plugin-s3

sudo tee /etc/yum.repos.d/my-repo.repo <<EOF
[my-repo]
name=My Private Repository
baseurl=s3://your-bucket/el\$releasever/\$basearch
enabled=1
gpgcheck=0
s3_enabled=1
EOF
```

## Caveats

- **Not concurrent-safe**: Multiple simultaneous updates can corrupt metadata. Use external locking (e.g., CI/CD pipeline serialization).
- **Brief inconsistency window**: During metadata updates, clients may see transient checksum mismatches. They will retry and succeed once the update completes.
- **No repository signing**: Individual RPM signing is supported and recommended; repository metadata signing (`repomd.xml`) is not implemented.

## Project Structure

```
yums3/
├── core/
│   ├── __init__.py          # Exports and Colors utility
│   ├── backend.py           # Storage backend abstraction (S3 + local)
│   ├── cli.py               # Generic CLI interface
│   ├── config.py            # Configuration management (RepoConfig)
│   ├── constants.py         # Defaults, config file locations
│   ├── deb.py               # Debian repository manager
│   ├── sqlite_metadata.py   # SQLite database generation
│   └── yum.py               # YUM repository manager
├── scripts/                  # Utility scripts
├── tests/                    # Test suite
├── yums3.py                  # YUM CLI entry point
├── debs3.py                  # DEB CLI entry point
├── Makefile                  # setup-venv target
├── requirements.txt          # Python dependencies (boto3, lxml)
└── README.md
```

## Testing

```bash
source ~/.venv/yums3/bin/activate
python3 tests/test_config.py
python3 tests/test_storage_backend.py
python3 tests/test_sqlite_integration.py
```

## License

MIT License. See [LICENSE](LICENSE) for details.
