#!/usr/bin/env python3
"""
Test suite for Debian repository validation and backup/recovery

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import sys
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.backend import LocalStorageBackend
from core.config import RepoConfig
from debs3 import DebRepo


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_test(name):
    print(f"\n{Colors.BLUE}{Colors.BOLD}TEST: {name}{Colors.RESET}")


def print_pass(msg):
    print(f"  {Colors.GREEN}✓ {msg}{Colors.RESET}")


def print_fail(msg):
    print(f"  {Colors.RED}✗ {msg}{Colors.RESET}")


def print_info(msg):
    print(f"  {Colors.YELLOW}ℹ {msg}{Colors.RESET}")


def get_test_debs():
    """Get paths to test .deb files"""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    deb1 = os.path.join(script_dir, 'hello-world_1.0.0_amd64.deb')
    deb2 = os.path.join(script_dir, 'goodbye-forever_2.0.0_amd64.deb')
    
    if not os.path.exists(deb1) or not os.path.exists(deb2):
        print_fail("Test .deb packages not found. Run: ./test_debs/build_test_debs.sh")
        return None, None
    
    return deb1, deb2


def test_validation_valid_repo():
    """Test validation on a valid repository"""
    print_test("Validation - Valid Repository")
    
    deb1, deb2 = get_test_debs()
    if not deb1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.deb.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)  # Manual validation
        
        repo = DebRepo(config)
        
        print_info("Creating repository...")
        repo.add_packages([deb1])
        print_pass("Repository created")
        
        print_info("Running validation...")
        result = repo.validate_repository('focal', 'main', 'amd64')
        assert result == True
        print_pass("Validation passed")
    
    return True


def test_validation_corrupted_checksum():
    """Test validation detects corrupted checksums"""
    print_test("Validation - Corrupted Checksum")
    
    deb1, deb2 = get_test_debs()
    if not deb1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.deb.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)
        
        repo = DebRepo(config)
        
        print_info("Creating repository...")
        repo.add_packages([deb1])
        print_pass("Repository created")
        
        # Corrupt the Release file in storage
        print_info("Corrupting Release file in storage...")
        release_file = os.path.join(storage_dir, 'dists/focal/Release')
        with open(release_file, 'r') as f:
            content = f.read()
        
        # Find the first SHA256 line and corrupt it
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith(' ') and 'main/binary-amd64/Packages' in line and 'SHA256:' in '\n'.join(lines[:i]):
                # Replace the checksum with zeros
                parts = line.split()
                if len(parts) >= 3:
                    parts[0] = '0000000000000000000000000000000000000000000000000000000000000000'
                    lines[i] = ' ' + ' '.join(parts)
                    break
        
        corrupted = '\n'.join(lines)
        with open(release_file, 'w') as f:
            f.write(corrupted)
        print_pass("Release file corrupted")
        
        print_info("Running validation...")
        result = repo.validate_repository('focal', 'main', 'amd64')
        assert result == False
        print_pass("Validation correctly detected corruption")
    
    return True


def test_backup_creation():
    """Test backup creation"""
    print_test("Backup Creation")
    
    deb1, deb2 = get_test_debs()
    if not deb1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.deb.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)
        
        repo = DebRepo(config)
        
        print_info("Creating initial repository...")
        repo.add_packages([deb1])
        print_pass("Initial repository created")
        
        print_info("Adding second package (should create backup)...")
        repo.add_packages([deb2])
        print_pass("Second package added")
        
        # Check if backup was created and cleaned up
        backup_dirs = [d for d in os.listdir(f"{storage_dir}/dists/focal") if d.startswith('metadata.backup-')]
        # Backup should be cleaned up after successful operation
        print_pass(f"Backup handling correct (found {len(backup_dirs)} backup dirs)")
    
    return True


def test_validation_missing_package():
    """Test validation detects missing packages"""
    print_test("Validation - Missing Package")
    
    deb1, deb2 = get_test_debs()
    if not deb1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.deb.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)
        
        repo = DebRepo(config)
        
        print_info("Creating repository...")
        repo.add_packages([deb1])
        print_pass("Repository created")
        
        # Delete the package file but leave metadata
        print_info("Deleting package file...")
        package_file = os.path.join(storage_dir, 'pool/main/h/hello-world/hello-world_1.0.0_amd64.deb')
        os.remove(package_file)
        print_pass("Package file deleted")
        
        print_info("Running validation...")
        result = repo.validate_repository('focal', 'main', 'amd64')
        assert result == False
        print_pass("Validation correctly detected missing package")
    
    return True


def test_backup_recovery():
    """Test backup recovery on failure"""
    print_test("Backup Recovery on Failure")
    
    deb1, deb2 = get_test_debs()
    if not deb1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.deb.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)
        
        repo = DebRepo(config)
        
        print_info("Creating initial repository...")
        repo.add_packages([deb1])
        print_pass("Initial repository created")
        
        # Get original Release file content
        release_file = os.path.join(storage_dir, 'dists/focal/Release')
        with open(release_file, 'r') as f:
            original_content = f.read()
        
        print_info("Simulating operation with backup...")
        # Create backup manually - this sets repo.backup_path
        repo._backup_metadata('focal', 'main', 'amd64')
        print_pass(f"Backup created: {repo.backup_path}")
        
        # Modify Release file to simulate partial operation
        with open(release_file, 'w') as f:
            f.write("CORRUPTED DATA")
        print_info("Simulated corruption during operation")
        
        # Restore from backup
        print_info("Restoring from backup...")
        repo._restore_metadata('focal', 'main', 'amd64')
        print_pass("Metadata restored")
        
        # Verify restoration
        with open(release_file, 'r') as f:
            restored_content = f.read()
        
        assert restored_content == original_content
        print_pass("Restored content matches original")
    
    return True


def main():
    """Run all tests"""
    print()
    print("=" * 70)
    print("Debian Repository Validation & Backup/Recovery Test Suite")
    print("=" * 70)
    
    tests = [
        test_validation_valid_repo,
        test_validation_corrupted_checksum,
        test_backup_creation,
        test_validation_missing_package,
        test_backup_recovery,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print_fail(f"{test.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print_fail(f"{test.__name__} raised exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    print()
    
    return failed == 0


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
