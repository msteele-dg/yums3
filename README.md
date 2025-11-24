# yums3 - S3-Backed YUM Repository Manager

A lightweight Python tool for managing YUM/DNF repositories hosted on Amazon S3. Designed for efficient package publishing without requiring full repository downloads.

## Features

- **Efficient Updates**: Add or remove packages without downloading existing RPMs
- **Metadata Manipulation**: Direct XML manipulation for fast operations
- **S3 Native**: Built specifically for S3-backed repositories
- **Auto-Detection**: Automatically detects architecture and EL version from RPMs

## Requirements

- Python 3.6+
- `boto3` - AWS SDK for Python
- `createrepo_c` - YUM repository metadata creation tool
- AWS credentials configured (via `~/.aws/credentials` or environment variables)
- `rpm` command-line tool

### Installation

```bash
# Install Python dependencies
pip install boto3

# Install system dependencies (Rocky/RHEL)
dnf install createrepo_c rpm-build

# Install system dependencies (Ubuntu/Debian)
apt-get install createrepo-c rpm
```

## Quick Start

### Adding Packages

Add one or more RPM packages to your repository:

```bash
./yums3.py my-package-1.0.0-1.el9.x86_64.rpm
```

Add multiple packages at once:

```bash
./yums3.py package1.rpm package2.rpm package3.rpm
```

Skip confirmation prompt (useful for CI/CD):

```bash
./yums3.py -y my-package.rpm
```

### Removing Packages

Remove packages by filename:

```bash
./yums3.py --remove my-package-1.0.0-1.el9.x86_64.rpm
```

Remove multiple packages:

```bash
./yums3.py --remove old-package1.rpm old-package2.rpm
```

### Custom Repository Location

Use a custom local cache directory:

```bash
./yums3.py -d /tmp/my-repo-cache my-package.rpm
```

### Validating Repository

Perform full validation of a repository:

```bash
./yums3.py --validate el9/x86_64
```

This checks:
- Metadata integrity (checksums, sizes, XML validity)
- Repository consistency (all packages exist, no orphans)
- Client compatibility (DNF requirements)

Skip post-operation validation (for speed):

```bash
./yums3.py --no-validate my-package.rpm
```

**Note**: Quick validation runs automatically after add/remove operations unless `--no-validate` is specified.

## How It Works

### Repository Structure

The tool organizes packages in S3 by EL version and architecture:

```
s3://your-bucket/
├── el9/
│   ├── x86_64/
│   │   ├── package1.rpm
│   │   ├── package2.rpm
│   │   └── repodata/
│   │       ├── repomd.xml
│   │       ├── <checksum>-primary.xml.gz
│   │       ├── <checksum>-filelists.xml.gz
│   │       └── <checksum>-other.xml.gz
│   └── aarch64/
│       └── ...
└── el8/
    └── ...
```

### Automatic Backups

Before making any changes, the tool automatically creates a timestamped backup of the metadata in S3:

```
s3://your-bucket/el9/x86_64/repodata.backup-20250121-143022/
```

**On success**: Backup is automatically cleaned up
**On failure**: Metadata is automatically restored from backup, and backup is retained for inspection

This ensures you can always recover from failed operations without manual intervention.

### Metadata Manipulation

Instead of downloading all RPMs to regenerate metadata, this tool directly manipulates the YUM metadata XML files:

#### Adding Packages

1. **Download metadata only** - Fetches `repodata/` directory from S3
2. **Generate new metadata** - Creates metadata for new packages in a temporary location
3. **Merge XML** - Parses both metadata sets and merges package entries
4. **Update checksums** - Recalculates checksums and renames files accordingly
5. **Upload** - Uploads new packages and updated metadata to S3

#### Removing Packages

1. **Download metadata only** - Fetches `repodata/` directory from S3
2. **Parse XML** - Reads primary, filelists, and other metadata files
3. **Remove entries** - Deletes package entries from XML trees
4. **Update checksums** - Recalculates checksums for modified files
5. **Upload** - Uploads updated metadata and deletes RPMs from S3

### Namespace Handling

YUM metadata uses XML namespaces, but different tools have different expectations:

- `createrepo_c` generates metadata **with** namespace prefixes (`<repo:data>`)
- `dnf`/`yum` clients expect `repomd.xml` **without** namespace prefixes (`<data>`)
- Other metadata files (primary.xml.gz, etc.) can have namespaces

This tool handles this by:
- Preserving namespaces in primary/filelists/other metadata
- Stripping namespace prefixes from `repomd.xml` for DNF compatibility
- Supporting both formats when reading metadata

## Configuration

### S3 Bucket

By default, the tool uses the bucket `deepgram-yum-repo`. To use a different bucket, modify the `YumRepo` initialization in the script:

```python
repo = YumRepo(
    s3_bucket_name="your-bucket-name",
    local_repo_base=args.repo_dir
)
```

### AWS Credentials

The tool uses standard AWS credential resolution:

1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
2. AWS credentials file (`~/.aws/credentials`)
3. IAM role (when running on EC2)

Required S3 permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name/*",
        "arn:aws:s3:::your-bucket-name"
      ]
    }
  ]
}
```

## Client Configuration

### Public S3 Bucket (Recommended for Open Source)

If your S3 bucket allows public read access:

```bash
# Create repo configuration (works for all EL versions and architectures)
sudo tee /etc/yum.repos.d/my-repo.repo <<EOF
[my-repo]
name=My Repository
baseurl=https://your-bucket.s3.amazonaws.com/el\$releasever/\$basearch
enabled=1
gpgcheck=0
repo_gpgcheck=0
EOF

# Update cache and install packages
sudo dnf makecache
sudo dnf install my-package
```

**YUM Variables Explained:**
- `$releasever` - Automatically expands to `9` on Rocky/RHEL 9, `8` on Rocky/RHEL 8, etc.
- `$basearch` - Automatically expands to `x86_64`, `aarch64`, etc.
- Use `\$` to prevent shell expansion when writing the config file

**Result:** On Rocky Linux 9 x86_64, the baseurl becomes:
```
https://your-bucket.s3.amazonaws.com/el9/x86_64
```

### Private S3 Bucket (IAM Roles)

For private buckets, use IAM roles on EC2 instances:

**1. Create IAM policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket/*",
        "arn:aws:s3:::your-bucket"
      ]
    }
  ]
}
```

**2. Attach policy to EC2 instance role**

**3. Install S3 plugin for YUM:**
```bash
# Rocky/RHEL 9
sudo dnf install python3-dnf-plugin-s3

# Rocky/RHEL 8
sudo dnf install python3-dnf-plugin-s3

# Ubuntu (requires custom setup)
# S3 plugin not officially supported, use presigned URLs instead
```

**4. Configure repo:**
```bash
sudo tee /etc/yum.repos.d/my-repo.repo <<EOF
[my-repo]
name=My Private Repository
baseurl=s3://your-bucket/el\$releasever/\$basearch
enabled=1
gpgcheck=0
repo_gpgcheck=0
s3_enabled=1
EOF
```

### Private S3 Bucket (Presigned URLs)

For temporary access without IAM roles:

**1. Generate presigned URL (valid for 7 days):**
```bash
aws s3 presign s3://your-bucket/el9/x86_64/repodata/repomd.xml --expires-in 604800
```

**2. Use CloudFront or API Gateway** for permanent URLs with authentication

**3. Or use a simple proxy script:**
```bash
# Install nginx
sudo dnf install nginx

# Configure nginx to proxy S3 with credentials
sudo tee /etc/nginx/conf.d/yum-proxy.conf <<EOF
server {
    listen 8080;
    location / {
        proxy_pass https://your-bucket.s3.amazonaws.com;
        proxy_set_header Authorization "AWS4-HMAC-SHA256 ...";
    }
}
EOF

# Configure repo to use local proxy
sudo tee /etc/yum.repos.d/my-repo.repo <<EOF
[my-repo]
name=My Repository
baseurl=http://localhost:8080/el\$releasever/\$basearch
enabled=1
gpgcheck=0
repo_gpgcheck=0
EOF
```

### With GPG Package Signing

If you signed your RPMs:

```bash
# Import GPG public key
sudo rpm --import https://your-bucket.s3.amazonaws.com/RPM-GPG-KEY-your-repo

# Configure repo with GPG check enabled
sudo tee /etc/yum.repos.d/my-repo.repo <<EOF
[my-repo]
name=My Repository
baseurl=https://your-bucket.s3.amazonaws.com/el\$releasever/\$basearch
enabled=1
gpgcheck=1
repo_gpgcheck=0
gpgkey=https://your-bucket.s3.amazonaws.com/RPM-GPG-KEY-your-repo
EOF
```

### Testing Your Configuration

```bash
# Clear cache
sudo dnf clean all

# Verify repo is accessible
sudo dnf repolist

# List available packages
sudo dnf list available --repo=my-repo

# Install a package
sudo dnf install --repo=my-repo my-package
```

### Troubleshooting Client Issues

**"Cannot retrieve repository metadata"**
```bash
# Check what variables expand to on your system
echo "Release: $(rpm -E %{rhel}), Arch: $(uname -m)"

# Check S3 bucket permissions (adjust el9/x86_64 to match your system)
aws s3 ls s3://your-bucket/el9/x86_64/repodata/

# Test direct access
curl -I https://your-bucket.s3.amazonaws.com/el9/x86_64/repodata/repomd.xml

# Check repo configuration and variable expansion
sudo dnf repolist -v
```

**"Checksum doesn't match"**
```bash
# Clear DNF cache
sudo dnf clean all
sudo dnf makecache
```

**"404 Not Found"**
- Verify the EL version and architecture match your system
- Check that packages were uploaded successfully
- Ensure S3 bucket allows public read (or IAM role is configured)

## Caveats and Limitations

### Concurrency

**⚠️ This tool is NOT safe for concurrent operations.**

- Multiple simultaneous updates can corrupt metadata
- No locking mechanism is implemented
- Use external coordination (e.g., CI/CD pipeline serialization) if needed

**Recommendation**: Run operations sequentially, especially in CI/CD pipelines.

**Note**: While backups protect against operation failures, they don't prevent corruption from concurrent modifications.

### Client Behavior During Updates

When metadata is being updated:

- **Clients mid-download**: May see inconsistent state if they cached old `repomd.xml` but fetch new metadata files
- **Checksum mismatches**: Clients will fail with checksum errors if they fetch metadata during an update
- **Retry behavior**: Most clients will retry and succeed once the update completes

**Best practices**:
- Perform updates during low-traffic periods
- Consider using a staging repository for testing
- Monitor for failed client requests after updates

### Metadata Consistency

The tool updates metadata in this order:
1. Upload new RPM files
2. Delete old metadata files
3. Upload new metadata files

There's a brief window where:
- Old metadata may reference non-existent files (if clients cached `repomd.xml`)
- New files exist but aren't in metadata yet

This is generally acceptable for most use cases, but be aware of the window.

### Large Repositories

For repositories with many packages:
- Metadata files can become large (100s of MB)
- XML parsing and manipulation takes time
- Consider splitting into multiple repositories by purpose/version

### No Repository Signature Support

This tool does not sign repository metadata (`repomd.xml`). This is intentional - repository signing adds complexity and is often unnecessary for internal/private repositories.

**If you need signed packages:**
- Sign individual RPMs before adding them to the repository (recommended)
- RPM signatures are preserved and verified by clients independently of repository signatures
- Use `rpm --addsign` or `rpmsign` to sign RPMs at build time

**Repository vs Package Signing:**
- **Package signing** (recommended): Verifies the RPM itself hasn't been tampered with
- **Repository signing** (optional): Verifies the repository metadata hasn't been tampered with
- For most use cases, package signing alone is sufficient

**To use signed RPMs:**
```bash
# Sign RPM at build time
rpmsign --addsign --key-id=YOUR_KEY_ID package.rpm

# Add to repository (signature is preserved)
./yums3.py package.rpm

# Clients verify RPM signatures automatically
dnf install package  # Verifies RPM signature
```

## Troubleshooting

### "Package 'X' not found in repository"

The package doesn't exist in S3. List packages to verify:

```bash
aws s3 ls s3://your-bucket/el9/x86_64/ | grep '\.rpm$'
```

### Operation failed and metadata was corrupted

The tool automatically restores from backup on failure. If manual restoration is needed:

```bash
# List available backups
aws s3 ls s3://your-bucket/el9/x86_64/ | grep backup

# Manually restore from a specific backup
aws s3 sync s3://your-bucket/el9/x86_64/repodata.backup-20250121-143022/ \
             s3://your-bucket/el9/x86_64/repodata/
```

### Validation failures

Run full validation to diagnose issues:

```bash
./yums3.py --validate el9/x86_64
```

Common issues:
- **Checksum mismatches**: Metadata was corrupted, restore from backup
- **Missing RPMs**: Referenced in metadata but not in S3, remove and re-add
- **Orphaned RPMs**: In S3 but not in metadata, remove manually or re-add to repo
- **Namespace prefixes**: Run the tool again to fix (it strips namespaces automatically)

### "Checksum doesn't match" errors on clients

Metadata was updated while client was downloading. Client should retry automatically. If persistent:

```bash
# Clear client cache
dnf clean all
dnf makecache
```

### "Unknown element" warnings from createrepo_c

These are usually harmless warnings about XML namespaces. The tool handles them correctly.

### AWS credentials errors

Ensure your AWS credentials are configured:

```bash
aws configure
# or
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_DEFAULT_REGION=us-east-1
```

## Contributing

This tool is designed for specific use cases. If you need additional features:

- **GPG signing**: Consider using `createrepo_c` directly with signing options
- **Concurrent updates**: Implement external locking (e.g., DynamoDB, Redis)
- **Delta RPMs**: Use `createrepo_c` with `--deltas` option
- **Multiple architectures**: Run the tool separately for each architecture

## License

This tool is provided as-is for managing YUM repositories on S3. Modify as needed for your use case.

## See Also

- [createrepo_c documentation](https://github.com/rpm-software-management/createrepo_c)
- [YUM repository format](https://docs.fedoraproject.org/en-US/quick-docs/repositories/)
- [DNF documentation](https://dnf.readthedocs.io/)
