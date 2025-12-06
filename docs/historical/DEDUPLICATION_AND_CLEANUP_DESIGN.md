# Deduplication and Cleanup Design

## Overview

Two improvements to make yums3 more efficient and reliable:

1. **Deduplication**: Skip adding packages that already exist (same checksum)
2. **Cleanup**: Remove orphaned files from repodata that shouldn't be there

## Problem 1: Duplicate Package Detection

### Current Behavior

When adding packages, yums3 always:
1. Uploads the RPM file
2. Regenerates metadata
3. Uploads new metadata

This happens even if the exact same package (same checksum) already exists in the repository.

### Proposed Solution

**Before adding packages:**
1. Download existing primary.xml.gz
2. Extract checksums of all existing packages
3. Calculate checksums of packages being added
4. Filter out packages that already exist (matching checksum)
5. If no new packages remain, skip metadata regeneration entirely

**Benefits:**
- Faster operations (no unnecessary uploads/metadata regeneration)
- Reduced S3 costs (fewer PUT operations)
- Idempotent operations (running twice has no effect)
- Better CI/CD integration (can safely re-run)

### Implementation Plan

#### Step 1: Add checksum extraction method

```python
def _get_existing_package_checksums(self, repo_path):
    """Get checksums of all packages in repository
    
    Returns:
        dict: {rpm_filename: checksum}
    """
    try:
        # Download primary.xml.gz
        primary_content = self.storage.download_file_content(
            f"{repo_path}/repodata/primary.xml.gz"
        )
        
        # Parse and extract checksums
        with gzip.open(io.BytesIO(primary_content), 'rt') as f:
            tree = ET.parse(f)
            root = tree.getroot()
        
        checksums = {}
        NS = {'common': 'http://linux.duke.edu/metadata/common'}
        
        for package in root.findall('.//common:package', NS):
            name_elem = package.find('common:name', NS)
            checksum_elem = package.find('common:checksum', NS)
            location_elem = package.find('common:location', NS)
            
            if location_elem is not None:
                filename = os.path.basename(location_elem.get('href'))
                if checksum_elem is not None:
                    checksums[filename] = checksum_elem.text
        
        return checksums
        
    except Exception as e:
        # If we can't get checksums, assume no duplicates
        return {}
```

#### Step 2: Add RPM checksum calculation

```python
def _calculate_rpm_checksum(self, rpm_file):
    """Calculate SHA256 checksum of RPM file
    
    Args:
        rpm_file: Path to RPM file
    
    Returns:
        str: SHA256 checksum
    """
    return self.calculate_checksum(rpm_file)
```

#### Step 3: Filter duplicates in add_packages

```python
def add_packages(self, rpm_files):
    """Add one or more RPM packages to the repository"""
    # ... existing validation ...
    
    # Check if repo exists
    if not self._repo_exists(repo_path):
        self._init_repo(rpm_files, repo_dir, repo_path)
    else:
        # Get existing package checksums
        print("Checking for duplicate packages...")
        existing_checksums = self._get_existing_package_checksums(repo_path)
        
        # Filter out duplicates
        new_packages = []
        skipped_packages = []
        
        for rpm_file in rpm_files:
            rpm_basename = os.path.basename(rpm_file)
            rpm_checksum = self._calculate_rpm_checksum(rpm_file)
            
            if rpm_basename in existing_checksums:
                if existing_checksums[rpm_basename] == rpm_checksum:
                    skipped_packages.append(rpm_basename)
                    print(f"  ⊘ {rpm_basename} (already exists with same checksum)")
                else:
                    # Same filename, different checksum - this is an update
                    new_packages.append(rpm_file)
                    print(f"  ↻ {rpm_basename} (updating - checksum changed)")
            else:
                new_packages.append(rpm_file)
                print(f"  + {rpm_basename} (new package)")
        
        # If no new packages, skip metadata regeneration
        if not new_packages:
            print(Colors.success("✓ All packages already exist - nothing to do"))
            return
        
        # Only add new/updated packages
        self._add_to_existing_repo(new_packages, repo_dir, repo_path)
```

## Problem 2: Orphaned Files in Repodata

### Current Behavior

The repodata directory can accumulate orphaned files:
- Old metadata files from previous operations
- Temporary files from failed operations
- Files from manual interventions

### Proposed Solution

**After metadata regeneration:**
1. Identify expected files (from repomd.xml)
2. List all files in repodata directory
3. Delete any files not referenced in repomd.xml

**Benefits:**
- Clean repository structure
- Reduced storage costs
- Prevents confusion from stale files
- Better validation results

### Implementation Plan

#### Step 1: Add method to get expected files

```python
def _get_expected_repodata_files(self, repomd_path):
    """Get list of files that should exist in repodata
    
    Args:
        repomd_path: Path to repomd.xml
    
    Returns:
        set: Set of expected filenames (including repomd.xml)
    """
    expected = {'repomd.xml', 'repomd.xml.asc'}  # Always keep these
    
    tree = ET.parse(repomd_path)
    root = tree.getroot()
    
    NS = {'repo': 'http://linux.duke.edu/metadata/repo'}
    
    # Try with namespace
    data_elements = root.findall('repo:data', NS)
    if not data_elements:
        # Try without namespace
        data_elements = root.findall('data')
    
    for data in data_elements:
        # Get location
        location = data.find('repo:location', NS)
        if location is None:
            location = data.find('location')
        
        if location is not None:
            href = location.get('href')
            if href:
                # Extract filename from href (e.g., "repodata/abc-primary.xml.gz")
                filename = os.path.basename(href)
                expected.add(filename)
    
    return expected
```

#### Step 2: Add cleanup method

```python
def _cleanup_repodata(self, repo_dir, repo_path):
    """Remove orphaned files from repodata directory
    
    Args:
        repo_dir: Local repository directory
        repo_path: Remote repository path
    """
    repodata_dir = os.path.join(repo_dir, 'repodata')
    repomd_path = os.path.join(repodata_dir, 'repomd.xml')
    
    # Get expected files
    expected_files = self._get_expected_repodata_files(repomd_path)
    
    # Get actual files in local repodata
    actual_files = set(os.listdir(repodata_dir))
    
    # Find orphaned files
    orphaned = actual_files - expected_files
    
    if orphaned:
        print(f"  Cleaning up {len(orphaned)} orphaned file(s) from repodata...")
        for filename in orphaned:
            # Delete from local
            local_path = os.path.join(repodata_dir, filename)
            os.remove(local_path)
            print(f"    ✗ {filename}")
            
            # Delete from storage
            try:
                self.storage.delete_file(f"{repo_path}/repodata/{filename}")
            except:
                pass  # File might not exist in storage
```

#### Step 3: Integrate cleanup into workflow

```python
def _add_to_existing_repo(self, rpm_files, repo_dir, repo_path):
    """Add packages to existing repository"""
    # ... existing code ...
    
    print("Merging metadata...")
    self._merge_metadata(repo_dir, temp_repo, rpm_files)
    
    # NEW: Clean up orphaned files
    print("Cleaning up repodata...")
    self._cleanup_repodata(repo_dir, repo_path)
    
    # ... rest of existing code ...
```

## Testing Strategy

### Test 1: Duplicate Detection

```python
def test_duplicate_detection():
    """Test that duplicate packages are skipped"""
    # Add package first time
    repo.add_packages(['test.rpm'])
    
    # Add same package again
    repo.add_packages(['test.rpm'])
    
    # Verify:
    # - Second add should skip
    # - Metadata should not be regenerated
    # - No upload should occur
```

### Test 2: Checksum Change Detection

```python
def test_checksum_change():
    """Test that packages with same name but different checksum are updated"""
    # Add package v1
    repo.add_packages(['test-1.0.rpm'])
    
    # Rebuild package with same name but different content
    # Add package v2 (same filename, different checksum)
    repo.add_packages(['test-1.0.rpm'])  # Different content
    
    # Verify:
    # - Package should be updated
    # - Metadata should be regenerated
```

### Test 3: Orphaned File Cleanup

```python
def test_orphaned_cleanup():
    """Test that orphaned files are removed"""
    # Add packages
    repo.add_packages(['test.rpm'])
    
    # Manually add orphaned file to repodata
    storage.upload_file('orphan.xml', 'el9/x86_64/repodata/orphan.xml')
    
    # Add another package (triggers cleanup)
    repo.add_packages(['test2.rpm'])
    
    # Verify:
    # - orphan.xml should be deleted
    # - Only expected files remain
```

## Edge Cases

### Edge Case 1: Partial Duplicates

**Scenario:** Adding 3 packages, 2 are duplicates, 1 is new

**Behavior:**
- Skip 2 duplicates
- Add 1 new package
- Regenerate metadata (because there's 1 new package)

### Edge Case 2: All Duplicates

**Scenario:** Adding 5 packages, all are duplicates

**Behavior:**
- Skip all 5 packages
- Do NOT regenerate metadata
- Print success message
- Return early

### Edge Case 3: Checksum Mismatch

**Scenario:** Same filename, different checksum

**Behavior:**
- Treat as update (not duplicate)
- Replace old package
- Regenerate metadata

### Edge Case 4: Empty Repository

**Scenario:** First time adding packages

**Behavior:**
- No existing checksums to check
- Add all packages normally
- Initialize repository

## Performance Impact

### Before Optimization

Adding 10 duplicate packages:
1. Upload 10 RPMs (unnecessary)
2. Download metadata
3. Regenerate metadata
4. Upload metadata
5. Total: ~30 seconds + 10 RPM uploads

### After Optimization

Adding 10 duplicate packages:
1. Download primary.xml.gz
2. Calculate checksums
3. Detect all duplicates
4. Skip everything
5. Total: ~2 seconds

**Improvement: 93% faster for duplicate operations**

## Configuration

Add optional config to control behavior:

```json
{
  "behavior.skip_duplicates": true,
  "behavior.cleanup_repodata": true
}
```

## Migration

These changes are backward compatible:
- No config changes required
- Existing workflows continue to work
- New behavior is automatic
- Can be disabled via config if needed

## Implementation Order

1. **Phase 1**: Implement duplicate detection
   - Add checksum extraction
   - Add filtering logic
   - Test with various scenarios

2. **Phase 2**: Implement cleanup
   - Add expected files detection
   - Add cleanup logic
   - Test with orphaned files

3. **Phase 3**: Integration
   - Integrate both features
   - Add configuration options
   - Update documentation

## Success Criteria

- ✅ Duplicate packages are detected and skipped
- ✅ Metadata regeneration is skipped when no new packages
- ✅ Orphaned files are removed from repodata
- ✅ All existing tests still pass
- ✅ New tests cover edge cases
- ✅ Performance improvement measurable
- ✅ No breaking changes to existing workflows
