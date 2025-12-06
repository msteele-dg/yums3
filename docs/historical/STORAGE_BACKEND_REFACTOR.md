# Storage Backend Refactoring Plan

## Overview
Separate storage operations from repository logic by creating an abstract `StorageBackend` class with concrete implementations for S3 and local file systems.

## Goals
1. Make yums3 testable with local file storage
2. Decouple storage operations from YUM repository logic
3. Track file changes explicitly (added vs existing files)
4. Enable future storage backends (Azure, GCS, etc.)

## Architecture

### StorageBackend Abstract Class

```python
class StorageBackend(ABC):
    """Abstract base class for storage backends"""
    
    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a file exists at the given path"""
        pass
    
    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a single file from storage to local path"""
        pass
    
    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a single file from local path to storage"""
        pass
    
    @abstractmethod
    def delete_file(self, path: str) -> None:
        """Delete a file from storage"""
        pass
    
    @abstractmethod
    def list_files(self, prefix: str, suffix: str = None) -> List[str]:
        """List files with optional prefix and suffix filters
        Returns: List of relative filenames (not full paths)
        """
        pass
    
    @abstractmethod
    def sync_from_storage(self, remote_prefix: str, local_dir: str) -> List[str]:
        """Sync directory from storage to local
        Returns: List of files downloaded
        """
        pass
    
    @abstractmethod
    def sync_to_storage(self, local_dir: str, remote_prefix: str) -> List[str]:
        """Sync directory from local to storage
        Returns: List of files uploaded
        """
        pass
    
    @abstractmethod
    def get_url(self) -> str:
        """Get human-readable URL for display purposes"""
        pass
```

### S3StorageBackend Implementation

```python
class S3StorageBackend(StorageBackend):
    """S3-based storage backend"""
    
    def __init__(self, bucket_name: str, aws_profile: str = None, 
                 endpoint_url: str = None):
        self.bucket_name = bucket_name
        self.aws_profile = aws_profile
        self.endpoint_url = endpoint_url
        
        # Initialize boto3 client
        session = boto3.Session(profile_name=aws_profile if aws_profile != 'default' else None)
        s3_config = {}
        if endpoint_url:
            s3_config['endpoint_url'] = endpoint_url
        self.s3_client = session.client('s3', **s3_config)
    
    def exists(self, path: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=path)
            return True
        except ClientError:
            return False
    
    def download_file(self, remote_path: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.s3_client.download_file(self.bucket_name, remote_path, local_path)
    
    def upload_file(self, local_path: str, remote_path: str) -> None:
        self.s3_client.upload_file(local_path, self.bucket_name, remote_path)
    
    def delete_file(self, path: str) -> None:
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=path)
    
    def list_files(self, prefix: str, suffix: str = None) -> List[str]:
        objects = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    filename = key.split('/')[-1]
                    if suffix is None or filename.endswith(suffix):
                        objects.append(filename)
        return objects
    
    def sync_from_storage(self, remote_prefix: str, local_dir: str) -> List[str]:
        os.makedirs(local_dir, exist_ok=True)
        downloaded = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=remote_prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    relative_path = key[len(remote_prefix):].lstrip('/')
                    if not relative_path:
                        continue
                    local_file = os.path.join(local_dir, relative_path)
                    os.makedirs(os.path.dirname(local_file), exist_ok=True)
                    self.s3_client.download_file(self.bucket_name, key, local_file)
                    downloaded.append(relative_path)
        return downloaded
    
    def sync_to_storage(self, local_dir: str, remote_prefix: str) -> List[str]:
        uploaded = []
        for root, dirs, files in os.walk(local_dir):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_dir)
                s3_key = f"{remote_prefix}/{relative_path}".replace('//', '/')
                self.s3_client.upload_file(local_path, self.bucket_name, s3_key)
                uploaded.append(relative_path)
        return uploaded
    
    def get_url(self) -> str:
        if self.endpoint_url:
            return f"{self.endpoint_url}/{self.bucket_name}"
        return f"https://{self.bucket_name}.s3.amazonaws.com"
```

### LocalStorageBackend Implementation

```python
class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend for testing"""
    
    def __init__(self, base_path: str):
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)
    
    def _get_full_path(self, path: str) -> str:
        """Convert relative path to full path"""
        return os.path.join(self.base_path, path.lstrip('/'))
    
    def exists(self, path: str) -> bool:
        return os.path.exists(self._get_full_path(path))
    
    def download_file(self, remote_path: str, local_path: str) -> None:
        """Copy from 'remote' (base_path) to local working directory"""
        src = self._get_full_path(remote_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        subprocess.run(['cp', src, local_path], check=True)
    
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Copy from local working directory to 'remote' (base_path)"""
        dst = self._get_full_path(remote_path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        subprocess.run(['cp', local_path, dst], check=True)
    
    def delete_file(self, path: str) -> None:
        full_path = self._get_full_path(path)
        if os.path.exists(full_path):
            os.remove(full_path)
    
    def list_files(self, prefix: str, suffix: str = None) -> List[str]:
        prefix_path = self._get_full_path(prefix)
        if not os.path.exists(prefix_path):
            return []
        
        files = []
        if os.path.isfile(prefix_path):
            filename = os.path.basename(prefix_path)
            if suffix is None or filename.endswith(suffix):
                files.append(filename)
        else:
            for item in os.listdir(prefix_path):
                if suffix is None or item.endswith(suffix):
                    files.append(item)
        return files
    
    def sync_from_storage(self, remote_prefix: str, local_dir: str) -> List[str]:
        """Copy directory from base_path to local working directory"""
        src = self._get_full_path(remote_prefix)
        os.makedirs(local_dir, exist_ok=True)
        
        if not os.path.exists(src):
            return []
        
        downloaded = []
        for root, dirs, files in os.walk(src):
            for file in files:
                src_file = os.path.join(root, file)
                relative_path = os.path.relpath(src_file, src)
                dst_file = os.path.join(local_dir, relative_path)
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                subprocess.run(['cp', src_file, dst_file], check=True)
                downloaded.append(relative_path)
        return downloaded
    
    def sync_to_storage(self, local_dir: str, remote_prefix: str) -> List[str]:
        """Copy directory from local working directory to base_path"""
        dst = self._get_full_path(remote_prefix)
        os.makedirs(dst, exist_ok=True)
        
        uploaded = []
        for root, dirs, files in os.walk(local_dir):
            for file in files:
                src_file = os.path.join(root, file)
                relative_path = os.path.relpath(src_file, local_dir)
                dst_file = os.path.join(dst, relative_path)
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                subprocess.run(['cp', src_file, dst_file], check=True)
                uploaded.append(relative_path)
        return uploaded
    
    def get_url(self) -> str:
        return f"file://{self.base_path}"
```

## YumRepo Changes

### Constructor Changes

```python
class YumRepo:
    def __init__(self, storage_backend: StorageBackend, local_repo_base=None, 
                 skip_validation=False):
        """
        Initialize YUM repository manager
        
        Args:
            storage_backend: StorageBackend instance (S3, Local, etc.)
            local_repo_base: Base directory for local repo cache
            skip_validation: Skip post-operation validation
        """
        self.storage = storage_backend
        self.local_repo_base = local_repo_base or os.path.expanduser("~/yum-repo")
        self.skip_validation = skip_validation
```

### Method Refactoring

Replace all direct S3 operations:

**Before:**
```python
def _s3_repo_exists(self, s3_prefix):
    try:
        self.s3_client.head_object(
            Bucket=self.s3_bucket_name,
            Key=f"{s3_prefix}/repodata/repomd.xml"
        )
        return True
    except ClientError:
        return False
```

**After:**
```python
def _repo_exists(self, prefix):
    return self.storage.exists(f"{prefix}/repodata/repomd.xml")
```

**Before:**
```python
def _s3_sync_from_s3(self, s3_prefix, local_dir):
    # ... S3-specific code
```

**After:**
```python
def _download_metadata(self, prefix, local_dir):
    return self.storage.sync_from_storage(prefix, local_dir)
```

### File Tracking

Track files explicitly during operations:

```python
class FileTracker:
    """Track file changes during repository operations"""
    
    def __init__(self):
        self.added_files = []      # New files added in this operation
        self.existing_files = []   # Files that existed before
        self.modified_files = []   # Existing files that were modified
        self.deleted_files = []    # Files that were deleted
    
    def mark_added(self, filename: str):
        self.added_files.append(filename)
    
    def mark_existing(self, filename: str):
        self.existing_files.append(filename)
    
    def mark_modified(self, filename: str):
        if filename not in self.modified_files:
            self.modified_files.append(filename)
    
    def mark_deleted(self, filename: str):
        self.deleted_files.append(filename)
    
    def get_all_current_files(self) -> List[str]:
        """Get all files that should exist after operation"""
        current = set(self.existing_files + self.added_files)
        current -= set(self.deleted_files)
        return list(current)
```

Use in operations:

```python
def _add_to_existing_repo(self, rpm_files, repo_dir, prefix):
    tracker = FileTracker()
    
    # Download existing metadata
    self._download_metadata(f"{prefix}/repodata", f"{repo_dir}/repodata")
    
    # List existing RPMs
    existing_rpms = self.storage.list_files(prefix, suffix='.rpm')
    for rpm in existing_rpms:
        tracker.mark_existing(rpm)
    
    # Add new RPMs
    for rpm_file in rpm_files:
        rpm_basename = os.path.basename(rpm_file)
        tracker.mark_added(rpm_basename)
        self.storage.upload_file(rpm_file, f"{prefix}/{rpm_basename}")
    
    # ... merge metadata ...
    
    # Upload only changed metadata files
    metadata_files = self._upload_metadata(f"{repo_dir}/repodata", f"{prefix}/repodata")
    for mf in metadata_files:
        tracker.mark_modified(mf)
    
    return tracker
```

## Configuration Changes

### Config File Format

```json
{
  "storage_type": "s3",
  "s3_bucket": "your-bucket-name",
  "aws_profile": "your-profile",
  "s3_endpoint_url": "https://s3.amazonaws.com",
  "local_repo_base": "/path/to/cache"
}
```

Or for local testing:

```json
{
  "storage_type": "local",
  "local_storage_path": "/tmp/test-repo",
  "local_repo_base": "/tmp/test-cache"
}
```

### Factory Function

```python
def create_storage_backend(config: dict) -> StorageBackend:
    """Create storage backend from configuration"""
    storage_type = config.get('storage_type', 's3')
    
    if storage_type == 's3':
        return S3StorageBackend(
            bucket_name=config['s3_bucket'],
            aws_profile=config.get('aws_profile'),
            endpoint_url=config.get('s3_endpoint_url')
        )
    elif storage_type == 'local':
        return LocalStorageBackend(
            base_path=config['local_storage_path']
        )
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")
```

## Migration Strategy

1. **Phase 1**: Create storage backend classes in new file `storage_backends.py`
2. **Phase 2**: Add storage backend to YumRepo constructor (keep old S3 code)
3. **Phase 3**: Replace S3 operations one method at a time
4. **Phase 4**: Remove old S3-specific code
5. **Phase 5**: Update tests to use LocalStorageBackend

## Benefits

1. **Testability**: Can test full workflow without S3 credentials
2. **Clarity**: Storage operations are explicit and tracked
3. **Flexibility**: Easy to add new storage backends
4. **Debugging**: File tracking makes it clear what changed
5. **Performance**: Can optimize storage operations independently

## Testing Strategy

```python
def test_add_package_local():
    # Create local storage backend
    storage = LocalStorageBackend('/tmp/test-repo')
    repo = YumRepo(storage, local_repo_base='/tmp/test-cache')
    
    # Add package
    tracker = repo.add_packages(['test.rpm'])
    
    # Verify tracking
    assert 'test.rpm' in tracker.added_files
    assert storage.exists('el9/x86_64/test.rpm')
    assert storage.exists('el9/x86_64/repodata/repomd.xml')
```
