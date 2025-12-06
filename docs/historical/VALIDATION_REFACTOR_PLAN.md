# Validation Code Refactoring Plan

## Current State Analysis

The validation code currently has direct S3 dependencies that need to be abstracted to use the storage backend.

## Issues Identified

### 1. Direct S3 Operations in Validation

**Location:** `_validate_quick()` method (lines ~916-1145)

**S3 Operations:**
- `self.s3_client.get_object()` - Downloads repomd.xml, metadata files, SQLite databases
- `self._s3_list_objects()` - Lists RPM files

**Proposed Solution:**
Add methods to StorageBackend:
```python
def download_file_content(self, remote_path: str) -> bytes:
    """Download file content directly to memory (for small files)"""
    pass
```

### 2. Old S3 Helper Methods

**Location:** Lines ~1460-1500

**Methods to Remove:**
- `_s3_sync_from_s3()` - Already replaced by `storage.sync_from_storage()`
- `_s3_sync_to_s3()` - Already replaced by `storage.sync_to_storage()`
- `_s3_list_objects()` - Already replaced by `storage.list_files()`

**Action:** Delete these methods entirely.

### 3. Backup/Restore with S3-Specific Optimization

**Location:** `_backup_metadata()` and `_restore_metadata()` (lines ~1370-1450)

**Current Behavior:**
```python
if isinstance(self.storage, S3StorageBackend):
    # Use efficient S3 copy_object operation
    self.s3_client.copy_object(...)
else:
    # Download then upload
    self.storage.download_file(...)
    self.storage.upload_file(...)
```

**QUESTION FOR GUIDANCE:**
Should we:
- **Option A:** Add a `copy_file(src, dst)` method to StorageBackend that backends can optimize?
- **Option B:** Keep the conditional logic in YumRepo (less clean but explicit)?
- **Option C:** Always use download/upload (simpler but slower for S3)?

My recommendation: **Option A** - Add `copy_file()` to StorageBackend.

### 4. Validation Methods Need Storage Backend

**_validate_quick()** needs to:
- Download repomd.xml content
- Download metadata files for checksum verification
- Download SQLite databases for validation
- List RPM files

**_validate_full()** needs to:
- List RPM files
- (Already uses local files for most operations)

## Proposed Storage Backend Additions

### New Method: download_file_content()

```python
@abstractmethod
def download_file_content(self, remote_path: str) -> bytes:
    """Download file content directly to memory
    
    Args:
        remote_path: Path to file in storage
    
    Returns:
        File content as bytes
    
    Note: Use for small files only (metadata, not RPMs)
    """
    pass
```

**S3 Implementation:**
```python
def download_file_content(self, remote_path: str) -> bytes:
    obj = self.s3_client.get_object(Bucket=self.bucket_name, Key=remote_path)
    return obj['Body'].read()
```

**Local Implementation:**
```python
def download_file_content(self, remote_path: str) -> bytes:
    full_path = self._get_full_path(remote_path)
    with open(full_path, 'rb') as f:
        return f.read()
```

### New Method: copy_file() [OPTIONAL - NEEDS GUIDANCE]

```python
@abstractmethod
def copy_file(self, src_path: str, dst_path: str) -> None:
    """Copy a file within storage (optimized for same-backend copies)
    
    Args:
        src_path: Source path in storage
        dst_path: Destination path in storage
    """
    pass
```

**S3 Implementation (optimized):**
```python
def copy_file(self, src_path: str, dst_path: str) -> None:
    self.s3_client.copy_object(
        Bucket=self.bucket_name,
        CopySource={'Bucket': self.bucket_name, 'Key': src_path},
        Key=dst_path
    )
```

**Local Implementation (simple):**
```python
def copy_file(self, src_path: str, dst_path: str) -> None:
    src_full = self._get_full_path(src_path)
    dst_full = self._get_full_path(dst_path)
    os.makedirs(os.path.dirname(dst_full), exist_ok=True)
    shutil.copy2(src_full, dst_full)
```

## Migration Steps

1. **Add `download_file_content()` to StorageBackend**
2. **Decide on `copy_file()` approach** (needs your guidance)
3. **Update `_validate_quick()` to use storage backend**
4. **Update `_validate_full()` to use storage backend**
5. **Update backup/restore to use `copy_file()` if added**
6. **Delete old S3 helper methods**
7. **Test all validation scenarios**

## Questions for Guidance

### Question 1: copy_file() Method
Should we add a `copy_file(src, dst)` method to StorageBackend for optimized same-backend copies?

**Pros:**
- S3 can use efficient copy_object (no download/upload)
- Clean abstraction
- Backends can optimize as needed

**Cons:**
- Adds complexity to interface
- Only benefits S3 backend
- Download/upload works fine for local storage

**Your preference?**

### Question 2: Validation for Non-S3 Backends
The validation code currently assumes it can download files from storage. For LocalStorageBackend, should we:

**Option A:** Download to temp location (consistent with S3 behavior)
**Option B:** Read directly from storage path (more efficient for local)
**Option C:** Make validation backend-aware

**Your preference?**

### Question 3: Old S3 Methods
Can we safely delete `_s3_sync_from_s3()`, `_s3_sync_to_s3()`, and `_s3_list_objects()`?

They appear to only be used in validation code and backup/restore, which we're refactoring.

**Confirm deletion?**

## Expected Outcome

After refactoring:
- ✅ No direct `self.s3_client` usage in validation code
- ✅ No direct `self._s3_list_objects()` calls
- ✅ All storage operations go through `self.storage.*`
- ✅ Validation works with both S3 and Local backends
- ✅ Cleaner, more maintainable code
