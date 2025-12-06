# Debian Repository Signing Guide

## Overview

Debian repositories use GPG (GNU Privacy Guard) signing to ensure the integrity and authenticity of repository metadata. This guide explains how signing works and how to implement it in debs3.

## Two Levels of Signing

### 1. Package Signing (Individual .deb files)

**What it is:**
- Each .deb file is signed with a GPG key
- Signature is embedded in the .deb file itself
- Done during package build process

**How it works:**
```bash
# Sign a package
dpkg-sig --sign builder package.deb

# Verify package signature
dpkg-sig --verify package.deb
```

**Verification:**
- APT verifies package signatures when installing
- Independent of repository signing
- Provides end-to-end integrity

**Note:** Package signing is done separately before adding to repository. debs3 preserves these signatures.

### 2. Repository Signing (Metadata)

**What it is:**
- The Release file is signed with a GPG key
- Creates Release.gpg (detached signature) and InRelease (inline signature)
- Ensures repository metadata hasn't been tampered with

**How it works:**
- Repository manager signs the Release file
- APT verifies signature before trusting repository
- Protects against man-in-the-middle attacks

**This is what debs3 will implement.**

## Repository Signing Architecture

### Files Involved

```
dists/focal/
├── Release              # Contains checksums of all metadata
├── Release.gpg          # Detached signature of Release
├── InRelease            # Inline-signed Release (preferred)
└── main/
    └── binary-amd64/
        ├── Packages
        ├── Packages.gz
        └── Packages.bz2
```

### Signing Flow

```
1. Generate metadata (Packages files)
   ↓
2. Calculate checksums of all metadata files
   ↓
3. Create Release file with checksums
   ↓
4. Sign Release file with GPG key
   ↓
5. Create Release.gpg (detached signature)
   ↓
6. Create InRelease (inline signature)
   ↓
7. Upload all files to repository
```

## Release File Format

The Release file contains:

```
Origin: MyRepo
Label: MyRepo
Suite: focal
Codename: focal
Date: Mon, 01 Dec 2025 21:37:36 UTC
Architectures: amd64 arm64
Components: main
Description: MyRepo Debian Repository
MD5Sum:
 4fc6fa36f986626d131a43e2b699037e      356 main/binary-amd64/Packages.gz
 40a8fccea27c494c54af5d4dad4899c9      379 main/binary-amd64/Packages.bz2
SHA1:
 b68194757feabac81f55d41202c6d4633b0add13      356 main/binary-amd64/Packages.gz
 3ba6b98cf9623f38c7ab78619586a6949fcd2ecb      379 main/binary-amd64/Packages.bz2
SHA256:
 6cf14e918f252c5d630f0e3218af603d3b0e4eefab6be77471d72b3b2c694f51      356 main/binary-amd64/Packages.gz
 651354258622f0252ac55dcdfb80c166be56f8fc35b8093182260b787eedb20e      379 main/binary-amd64/Packages.bz2
```

## GPG Signing Process

### 1. Generate GPG Key

```bash
# Generate a new GPG key
gpg --full-generate-key

# Choose:
# - RSA and RSA (default)
# - 4096 bits
# - Key does not expire (or set expiration)
# - Real name: "MyRepo Repository"
# - Email: "repo@example.com"

# List keys
gpg --list-keys

# Export public key
gpg --armor --export repo@example.com > repo-key.gpg
```

### 2. Sign Release File

**Create Release.gpg (detached signature):**
```bash
gpg --armor --detach-sign --sign -o Release.gpg Release
```

**Create InRelease (inline signature):**
```bash
gpg --clearsign --armor -o InRelease Release
```

### 3. Verify Signatures

```bash
# Verify Release.gpg
gpg --verify Release.gpg Release

# Verify InRelease
gpg --verify InRelease
```

## InRelease vs Release.gpg

### InRelease (Preferred)

**Format:**
```
-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA512

Origin: MyRepo
Label: MyRepo
...
-----BEGIN PGP SIGNATURE-----

iQIzBAEBCgAdFiEE...
...
-----END PGP SIGNATURE-----
```

**Advantages:**
- Single file (atomic operation)
- Preferred by modern APT
- Prevents certain attack vectors

**Disadvantages:**
- Slightly larger file size

### Release.gpg (Legacy)

**Format:**
- Separate file containing just the signature
- References the Release file

**Advantages:**
- Smaller files
- Backward compatible

**Disadvantages:**
- Two files (non-atomic)
- Vulnerable to certain attacks

**Best Practice:** Generate both InRelease and Release.gpg for maximum compatibility.

## Client Configuration

### 1. Add Repository Key

**Method 1: apt-key (deprecated but still works):**
```bash
curl https://repo.example.com/repo-key.gpg | sudo apt-key add -
```

**Method 2: signed-by (modern, recommended):**
```bash
# Download key
curl https://repo.example.com/repo-key.gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/myrepo.gpg

# Add repository with signed-by
echo "deb [signed-by=/usr/share/keyrings/myrepo.gpg] https://repo.example.com focal main" | \
  sudo tee /etc/apt/sources.list.d/myrepo.list
```

### 2. Update and Install

```bash
sudo apt update
sudo apt install package-name
```

## Implementation in debs3

### Configuration

Add GPG configuration keys:

```json
{
  "debian.gpg.enabled": true,
  "debian.gpg.key_id": "ABCD1234",
  "debian.gpg.passphrase": null,
  "debian.gpg.public_key_path": "/path/to/repo-key.gpg"
}
```

### Signing Function

```python
def _sign_release_file(self, release_file):
    """
    Sign Release file with GPG
    
    Args:
        release_file: Path to Release file
    
    Creates:
        - Release.gpg (detached signature)
        - InRelease (inline signature)
    """
    if not self.config.get('debian.gpg.enabled', False):
        return
    
    key_id = self.config.get('debian.gpg.key_id')
    if not key_id:
        print(Colors.warning("  ⚠ GPG signing enabled but no key_id configured"))
        return
    
    # Create Release.gpg (detached signature)
    gpg_cmd = [
        'gpg',
        '--armor',
        '--detach-sign',
        '--sign',
        '-u', key_id,
        '-o', release_file + '.gpg',
        release_file
    ]
    
    result = subprocess.run(gpg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(Colors.warning(f"  ⚠ Failed to create Release.gpg: {result.stderr}"))
    else:
        print("  ✓ Created Release.gpg")
    
    # Create InRelease (inline signature)
    inrelease_cmd = [
        'gpg',
        '--clearsign',
        '--armor',
        '-u', key_id,
        '-o', os.path.join(os.path.dirname(release_file), 'InRelease'),
        release_file
    ]
    
    result = subprocess.run(inrelease_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(Colors.warning(f"  ⚠ Failed to create InRelease: {result.stderr}"))
    else:
        print("  ✓ Created InRelease")
```

### Upload Function

```python
def _upload_metadata(self, distribution, component, arch, local_dir):
    """Upload metadata files including signatures"""
    # Upload Packages files
    for filename in ['Packages', 'Packages.gz', 'Packages.bz2']:
        local_file = os.path.join(local_dir, filename)
        if os.path.exists(local_file):
            remote_path = f"dists/{distribution}/{component}/binary-{arch}/{filename}"
            self.storage.upload_file(local_file, remote_path)
    
    # Upload Release file
    release_dir = os.path.dirname(local_dir)
    release_file = os.path.join(release_dir, 'Release')
    if os.path.exists(release_file):
        self.storage.upload_file(release_file, f"dists/{distribution}/Release")
    
    # Upload signatures if they exist
    if os.path.exists(release_file + '.gpg'):
        self.storage.upload_file(
            release_file + '.gpg',
            f"dists/{distribution}/Release.gpg"
        )
    
    inrelease_file = os.path.join(release_dir, 'InRelease')
    if os.path.exists(inrelease_file):
        self.storage.upload_file(
            inrelease_file,
            f"dists/{distribution}/InRelease"
        )
    
    # Upload public key if configured
    public_key = self.config.get('debian.gpg.public_key_path')
    if public_key and os.path.exists(public_key):
        self.storage.upload_file(public_key, 'repo-key.gpg')
```

## Security Considerations

### Key Management

**Best Practices:**
1. **Separate Keys:** Use different keys for different purposes
2. **Key Rotation:** Rotate keys periodically (e.g., annually)
3. **Secure Storage:** Store private keys securely (HSM, encrypted)
4. **Passphrase:** Use strong passphrase for private key
5. **Backup:** Keep secure backups of private keys

**Key Storage Options:**
- Local filesystem (encrypted)
- Hardware Security Module (HSM)
- AWS KMS (for S3 repositories)
- HashiCorp Vault
- GPG agent with passphrase caching

### Passphrase Handling

**Option 1: GPG Agent (Recommended)**
```bash
# Configure GPG agent to cache passphrase
echo "default-cache-ttl 3600" >> ~/.gnupg/gpg-agent.conf
gpgconf --reload gpg-agent
```

**Option 2: Environment Variable (CI/CD)**
```bash
# Set passphrase in environment
export GPG_PASSPHRASE="your-passphrase"

# Use in GPG command
echo "$GPG_PASSPHRASE" | gpg --passphrase-fd 0 --sign ...
```

**Option 3: Passphrase File (Less Secure)**
```bash
# Store in file (restrict permissions)
echo "your-passphrase" > ~/.gnupg/passphrase
chmod 600 ~/.gnupg/passphrase

# Use in GPG command
gpg --passphrase-file ~/.gnupg/passphrase --sign ...
```

### Attack Vectors

**Without Signing:**
- Man-in-the-middle attacks
- Repository metadata tampering
- Package substitution attacks

**With Signing:**
- Protects against metadata tampering
- Ensures repository authenticity
- Provides non-repudiation

**Note:** Repository signing does NOT protect against:
- Compromised signing key
- Malicious packages signed with valid key
- Attacks on package build process

## Validation

### Verify Repository Signature

```python
def _verify_release_signature(self, distribution):
    """
    Verify Release file signature
    
    Args:
        distribution: Distribution name
    
    Returns:
        bool: True if signature is valid
    """
    # Download Release and InRelease
    release_path = f"dists/{distribution}/Release"
    inrelease_path = f"dists/{distribution}/InRelease"
    
    try:
        # Try InRelease first (preferred)
        inrelease_content = self.storage.download_file_content(inrelease_path)
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(inrelease_content)
            temp_file = f.name
        
        # Verify signature
        result = subprocess.run(
            ['gpg', '--verify', temp_file],
            capture_output=True, text=True
        )
        
        os.unlink(temp_file)
        
        if result.returncode == 0:
            print(Colors.success("  ✓ InRelease signature valid"))
            return True
        else:
            print(Colors.error(f"  ✗ InRelease signature invalid: {result.stderr}"))
            return False
    
    except Exception as e:
        print(Colors.warning(f"  ⚠ Could not verify signature: {e}"))
        return False
```

## Testing

### Test Signing

```bash
# Generate test key
gpg --batch --gen-key <<EOF
Key-Type: RSA
Key-Length: 2048
Name-Real: Test Repository
Name-Email: test@example.com
Expire-Date: 0
%no-protection
%commit
EOF

# Get key ID
KEY_ID=$(gpg --list-keys test@example.com | grep -A 1 pub | tail -1 | tr -d ' ')

# Configure debs3
./debs3.py config debian.gpg.enabled true
./debs3.py config debian.gpg.key_id $KEY_ID

# Add package (will sign Release)
./debs3.py add package.deb

# Verify signature
gpg --verify dists/focal/InRelease
```

## Troubleshooting

### "gpg: signing failed: Inappropriate ioctl for device"

**Solution:**
```bash
export GPG_TTY=$(tty)
```

### "gpg: signing failed: No secret key"

**Solution:**
```bash
# List keys
gpg --list-secret-keys

# Verify key ID is correct
./debs3.py config debian.gpg.key_id
```

### "gpg: signing failed: Operation cancelled"

**Cause:** Passphrase required but not provided

**Solution:**
- Use GPG agent
- Provide passphrase via environment variable
- Remove passphrase from key (not recommended)

## Best Practices Summary

1. **Always sign repositories** in production
2. **Use InRelease** (preferred) and Release.gpg (compatibility)
3. **Rotate keys** periodically
4. **Secure private keys** with strong passphrases
5. **Use GPG agent** for passphrase caching
6. **Backup keys** securely
7. **Document key management** procedures
8. **Test signature verification** before deploying
9. **Monitor key expiration** dates
10. **Have key revocation** plan

## References

- [Debian Repository Format](https://wiki.debian.org/DebianRepository/Format)
- [Secure APT](https://wiki.debian.org/SecureApt)
- [GPG Documentation](https://www.gnupg.org/documentation/)
- [APT Signing](https://help.ubuntu.com/community/CreateAuthenticatedRepository)

## Implementation Checklist

Phase 3 GPG Signing:
- [ ] Add GPG configuration keys
- [ ] Implement `_sign_release_file()` method
- [ ] Create Release.gpg (detached signature)
- [ ] Create InRelease (inline signature)
- [ ] Upload signatures to storage
- [ ] Upload public key to repository root
- [ ] Add signature verification to validation
- [ ] Handle passphrase securely
- [ ] Add tests for signing
- [ ] Document key management procedures
