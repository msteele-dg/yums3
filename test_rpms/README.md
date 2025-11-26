# Test RPM Packages

This directory contains test RPM packages used for integration testing of yums3.

## Test Packages

1. **hello-world-1.0.0-1.el9.x86_64.rpm**
   - Installs a text file at `/usr/share/hello-world/message.txt` containing "Hello World"
   - Used to test basic repository operations

2. **goodbye-forever-2.0.0-1.el9.x86_64.rpm**
   - Installs a text file at `/usr/share/goodbye-forever/message.txt` containing "Goodbye Forever"
   - Used to test multi-package repository operations

## Building Test RPMs

To rebuild the test RPMs:

```bash
cd test_rpms
./build_test_rpms.sh
```

This will create fresh RPM packages using `rpmbuild`.

## Usage in Tests

The `test_sqlite_integration.py` script automatically uses these RPMs to:
1. Create a temporary local repository
2. Generate metadata with SQLite databases
3. Test DNF compatibility
4. Verify SQLite database functionality

No S3 access or network connectivity is required for these tests.
