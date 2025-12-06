# DNF Compatibility Fix - Complete

## Problem Summary

After the previous bug fixes, yums3 could create repositories that DNF could read when initialized fresh, but **merged repositories** (when adding packages to existing repos) were unreadable by DNF, showing 0 packages.

## Root Cause

The issue was with **XML namespace prefixes** in the merged metadata files:

### What createrepo_c generates:
```xml
<metadata xmlns="http://linux.duke.edu/metadata/common" xmlns:rpm="http://linux.duke.edu/metadata/rpm" packages="2">
<package type="rpm">
  <name>hello-world</name>
  ...
</package>
</metadata>
```

### What yums3 was generating (WRONG):
```xml
<common:metadata xmlns:common="http://linux.duke.edu/metadata/common" xmlns:rpm="http://linux.duke.edu/metadata/rpm" packages="2">
<common:package type="rpm">
  <common:name>hello-world</common:name>
  ...
</common:package>
</common:metadata>
```

The problem: **namespace prefixes on element names**. DNF and createrepo_c expect:
- Root element: `<metadata>` not `<common:metadata>`
- Child elements: `<package>` not `<common:package>`
- Namespace should be the **default namespace** (xmlns="...") not a prefixed namespace (xmlns:common="...")

## The Fix

Updated the `_merge_metadata()` method in yums3.py to strip namespace prefixes after writing XML, similar to how repomd.xml was already being handled.

### For primary.xml.gz:
```python
# Write merged primary.xml.gz (strip namespace prefixes)
import io
output = io.BytesIO()
existing_tree.write(output, encoding='utf-8', xml_declaration=True)
xml_content = output.getvalue().decode('utf-8')

# Remove namespace prefixes but keep declarations
xml_content = re.sub(r'<common:', '<', xml_content)
xml_content = re.sub(r'</common:', '</', xml_content)

# Convert xmlns:common to xmlns (default namespace)
xml_content = xml_content.replace('xmlns:common="http://linux.duke.edu/metadata/common"', 'xmlns="http://linux.duke.edu/metadata/common"')

with gzip.open(existing_primary, 'wt', encoding='utf-8') as f:
    f.write(xml_content)
```

### For filelists.xml.gz:
```python
# Remove filelists: prefix
xml_content = re.sub(r'<filelists:', '<', xml_content)
xml_content = re.sub(r'</filelists:', '</', xml_content)
xml_content = xml_content.replace('xmlns:filelists="http://linux.duke.edu/metadata/filelists"', 'xmlns="http://linux.duke.edu/metadata/filelists"')
```

### For other.xml.gz:
```python
# Remove otherdata: prefix
xml_content = re.sub(r'<otherdata:', '<', xml_content)
xml_content = re.sub(r'</otherdata:', '</', xml_content)
xml_content = xml_content.replace('xmlns:otherdata="http://linux.duke.edu/metadata/other"', 'xmlns="http://linux.duke.edu/metadata/other"')
```

## Why This Happened

Python's ElementTree library uses namespace prefixes when you call `ET.register_namespace()`. We needed to register namespaces to **find** elements with prefixes (like `common:package`), but this caused ElementTree to **write** elements with prefixes too.

The solution: Register namespaces for parsing, but strip the prefixes after writing.

## Verification

### Test 1: createrepo_c --update
Before fix:
```
C_CREATEREPOLIB: Warning: Primary XML parser: Unknown element "common:metadata"
C_CREATEREPOLIB: Warning: Primary XML parser: The target doesn't contain the expected element "<metadata>"
Loaded information about 0 packages
```

After fix:
```
Loaded information about 2 packages
```

### Test 2: DNF repoquery
Before fix:
```
$ dnf repoquery --repofrompath=test,/path/to/repo --repo=test -a
(no output - 0 packages found)
```

After fix:
```
$ dnf repoquery --repofrompath=test,/path/to/repo --repo=test -a
goodbye-forever-0:2.0.0-1.el9.x86_64
hello-world-0:1.0.0-1.el9.x86_64
```

### Test 3: Automated Test Suite
```bash
$ python3 test_dnf_compatibility.py
======================================================================
✓ All DNF compatibility tests passed!

CONCLUSION: yums3 generates DNF-compatible repositories
======================================================================
```

## Files Changed

- `yums3.py` - Updated `_merge_metadata()` to strip namespace prefixes from primary.xml, filelists.xml, and other.xml

## Complete Bug Fix Summary

This completes the DNF compatibility work. The full set of fixes was:

1. ✅ **Init repo creates SQLite databases** - Removed --no-database flag
2. ✅ **Merge doesn't try to update deleted database files** - Added skip logic for _db types
3. ✅ **Namespace declarations preserved** - Fixed repomd.xml to include required xmlns attributes
4. ✅ **Duplicate database entries prevented** - Added cleanup before adding new entries
5. ✅ **Old database files cleaned up** - Delete old .sqlite files before creating new ones
6. ✅ **Storage backend abstraction** - Created pluggable storage backends for testing
7. ✅ **Namespace prefixes removed from merged XML** - Strip prefixes to match createrepo_c format

## Testing

All repositories created by yums3 (both fresh and merged) are now fully compatible with DNF:

```bash
# Test with local storage backend
python3 test_storage_backend.py
# ✓ All tests passed!

# Test DNF compatibility
python3 test_dnf_compatibility.py
# ✓ All DNF compatibility tests passed!
```

## Next Steps

The yums3 tool now generates DNF-compatible repositories. You can:

1. Use it in production with S3 storage
2. Test locally with LocalStorageBackend
3. Compare output with createrepo_c using the comparison tools
4. Add more packages and verify merge behavior

The core functionality is working correctly!
