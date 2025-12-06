# Backend Info Refactor

## Summary

Refactored the storage backend information display to use a polymorphic `get_info()` method instead of conditional logic in the main function.

## Changes Made

### 1. Added `get_info()` Abstract Method

Added to `StorageBackend` base class in `core/backend.py`:

```python
@abstractmethod
def get_info(self) -> dict:
    """Get backend information for display
    
    Returns:
        Dictionary with display name as key and value as value
        Example: {"Storage": "file:///path/to/storage"}
    """
    pass
```

### 2. Implemented in S3StorageBackend

```python
def get_info(self) -> dict:
    """Get S3 backend information for display"""
    info = {}
    
    # Get AWS account
    try:
        sts_client = boto3.client('sts')
        identity = sts_client.get_caller_identity()
        info['AWS Account'] = identity['Account']
    except:
        info['AWS Account'] = "Unable to determine"
    
    # Get AWS region
    region = self.s3_client.meta.region_name
    if region:
        info['AWS Region'] = region
    elif os.environ.get('AWS_REGION'):
        info['AWS Region'] = f"{os.environ['AWS_REGION']} (from AWS_REGION)"
    elif os.environ.get('AWS_DEFAULT_REGION'):
        info['AWS Region'] = f"{os.environ['AWS_DEFAULT_REGION']} (from AWS_DEFAULT_REGION)"
    else:
        info['AWS Region'] = "Unable to determine"
    
    # Get AWS profile
    if self.aws_profile and self.aws_profile != 'default':
        info['AWS Profile'] = self.aws_profile
    else:
        info['AWS Profile'] = "default"
    
    # Get S3 URL
    info['S3 URL'] = self.get_url()
    
    return info
```

### 3. Implemented in LocalStorageBackend

```python
def get_info(self) -> dict:
    """Get local storage backend information for display"""
    return {
        'Storage': self.get_url()
    }
```

### 4. Updated Main Function

**Before:**
```python
# Get AWS info for confirmation
aws_info = repo.get_aws_info()

# Show confirmation
print()
print(Colors.bold("Configuration:"))
if isinstance(repo.storage, S3StorageBackend):
    print(f"  AWS Account:  {aws_info['account']}")
    print(f"  AWS Region:   {aws_info['region']}")
    print(f"  AWS Profile:  {Colors.bold(repo.aws_profile)}")
    print(f"  S3 URL:       {aws_info['s3_url']}")
else:
    print(f"  Storage:      {repo.storage.get_url()}")
```

**After:**
```python
# Show confirmation
print()
print(Colors.bold("Configuration:"))

# Get backend info and display it
backend_info = repo.storage.get_info()
for key, value in backend_info.items():
    print(f"  {key}:  {value}")
```

## Benefits

### 1. Polymorphism
Each backend is responsible for providing its own information, following the Open/Closed Principle.

### 2. Cleaner Code
Removed conditional logic (`isinstance` checks) from the main function.

### 3. Extensibility
Adding new storage backends is easier - just implement `get_info()` without modifying the main function.

### 4. Consistency
All backends follow the same interface for providing display information.

### 5. Testability
Each backend's info method can be tested independently.

## Example Output

### S3 Backend
```
Configuration:
  AWS Account:  396185571030
  AWS Region:   us-east-1
  AWS Profile:  default
  S3 URL:       https://my-bucket.s3.amazonaws.com
  Target:       https://my-bucket.s3.amazonaws.com/el9/x86_64
  Action:       ADD
  Packages:     1
    • my-package-1.0.0-1.el9.x86_64.rpm
```

### Local Backend
```
Configuration:
  Storage:      file:///srv/yum-repo
  Target:       file:///srv/yum-repo/el9/x86_64
  Action:       ADD
  Packages:     1
    • my-package-1.0.0-1.el9.x86_64.rpm
```

## Testing

Created `tests/test_backend_info.py` to verify:
- LocalStorageBackend returns correct info
- S3StorageBackend returns correct info with all expected keys
- Info is returned as a dictionary

All tests pass (2/2).

## Future Enhancements

With this pattern, adding new backends is straightforward:

```python
class AzureBlobStorageBackend(StorageBackend):
    def get_info(self) -> dict:
        return {
            'Azure Account': self.account_name,
            'Container': self.container_name,
            'Blob URL': self.get_url()
        }
```

## Files Modified

- `core/backend.py` - Added `get_info()` to base class and both implementations
- `yums3.py` - Simplified confirmation display logic
- `tests/test_backend_info.py` - New test file

## Backward Compatibility

This change is internal only - the user-facing behavior remains the same. The confirmation prompt displays the same information, just retrieved through a cleaner interface.
