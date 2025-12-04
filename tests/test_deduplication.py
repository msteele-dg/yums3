#!/usr/bin/env python3
"""
Test suite for package deduplication

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import sys
import tempfile
import shutil
import subprocess

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.backend import LocalStorageBackend
from core.config import RepoConfig
from yums3 import YumRepo


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


def get_test_rpms():
    """Get paths to test RPM files"""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_rpms_dir = os.path.join(script_dir, 'test_rpms')
    
    rpm1 = os.path.join(test_rpms_dir, 'hello-world-1.0.0-1.el9.x86_64.rpm')
    rpm2 = os.path.join(test_rpms_dir, 'goodbye-forever-2.0.0-1.el9.x86_64.rpm')
    
    if not os.path.exists(rpm1) or not os.path.exists(rpm2):
        print_fail("Test RPMs not found. Run: cd test_rpms && ./build_test_rpms.sh")
        return None, None
    
    return rpm1, rpm2


def test_duplicate_detection():
    """Test that duplicate packages are skipped"""
    print_test("Duplicate Detection - Skip Exact Duplicates")
    
    rpm1, rpm2 = get_test_rpms()
    if not rpm1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        # Create config
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.rpm.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)  # Skip validation for speed
        
        # Create repo
        repo = YumRepo(config)
        
        # Add package first time
        print_info("Adding package first time...")
        repo.add_packages([rpm1])
        print_pass("First add completed")
        
        # Verify package exists
        storage = LocalStorageBackend(storage_dir)
        rpms = storage.list_files('el9/x86_64', suffix='.rpm')
        assert 'hello-world-1.0.0-1.el9.x86_64.rpm' in rpms
        print_pass("Package exists in storage")
        
        # Add same package again
        print_info("Adding same package again...")
        repo.add_packages([rpm1])
        print_pass("Second add completed (should skip)")
        
        # Verify still only one package
        rpms = storage.list_files('el9/x86_64', suffix='.rpm')
        assert rpms.count('hello-world-1.0.0-1.el9.x86_64.rpm') == 1
        print_pass("No duplicate package in storage")
    
    return True


def test_multiple_duplicates():
    """Test adding multiple packages where some are duplicates"""
    print_test("Multiple Packages - Mixed Duplicates and New")
    
    rpm1, rpm2 = get_test_rpms()
    if not rpm1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        # Create config
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.rpm.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)
        
        # Create repo
        repo = YumRepo(config)
        
        # Add first package
        print_info("Adding first package...")
        repo.add_packages([rpm1])
        print_pass("First package added")
        
        # Add both packages (one duplicate, one new)
        print_info("Adding both packages (one duplicate, one new)...")
        repo.add_packages([rpm1, rpm2])
        print_pass("Second add completed")
        
        # Verify both packages exist
        storage = LocalStorageBackend(storage_dir)
        rpms = storage.list_files('el9/x86_64', suffix='.rpm')
        assert 'hello-world-1.0.0-1.el9.x86_64.rpm' in rpms
        assert 'goodbye-forever-2.0.0-1.el9.x86_64.rpm' in rpms
        assert len(rpms) == 2
        print_pass("Both packages exist (no duplicates)")
    
    return True


def test_all_duplicates():
    """Test adding multiple packages where all are duplicates"""
    print_test("All Duplicates - Skip Metadata Regeneration")
    
    rpm1, rpm2 = get_test_rpms()
    if not rpm1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        # Create config
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.rpm.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)
        
        # Create repo
        repo = YumRepo(config)
        
        # Add both packages
        print_info("Adding both packages...")
        repo.add_packages([rpm1, rpm2])
        print_pass("Both packages added")
        
        # Get metadata timestamp
        storage = LocalStorageBackend(storage_dir)
        repomd_path = os.path.join(storage_dir, 'el9/x86_64/repodata/repomd.xml')
        first_mtime = os.path.getmtime(repomd_path)
        print_info(f"First metadata timestamp: {first_mtime}")
        
        # Add both packages again (all duplicates)
        print_info("Adding both packages again (all duplicates)...")
        import time
        time.sleep(0.1)  # Ensure timestamp would change if regenerated
        repo.add_packages([rpm1, rpm2])
        print_pass("Second add completed (should skip)")
        
        # Verify metadata was NOT regenerated
        second_mtime = os.path.getmtime(repomd_path)
        print_info(f"Second metadata timestamp: {second_mtime}")
        assert first_mtime == second_mtime, "Metadata should not be regenerated for all duplicates"
        print_pass("Metadata was not regenerated (as expected)")
    
    return True


def test_checksum_change():
    """Test that packages with same name but different checksum are updated"""
    print_test("Checksum Change - Update Package")
    
    rpm1, rpm2 = get_test_rpms()
    if not rpm1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        # Create config
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.rpm.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)
        
        # Create repo
        repo = YumRepo(config)
        
        # Add first package
        print_info("Adding original package...")
        repo.add_packages([rpm1])
        
        # Get original checksum
        storage = LocalStorageBackend(storage_dir)
        original_checksum = repo._calculate_rpm_checksum(rpm1)
        print_info(f"Original checksum: {original_checksum[:16]}...")
        print_pass("Original package added")
        
        # Create modified version with same name
        modified_rpm = os.path.join(tmpdir, 'hello-world-1.0.0-1.el9.x86_64.rpm')
        shutil.copy(rpm2, modified_rpm)  # Copy different RPM with same name
        
        # Verify checksum is different
        modified_checksum = repo._calculate_rpm_checksum(modified_rpm)
        print_info(f"Modified checksum: {modified_checksum[:16]}...")
        assert original_checksum != modified_checksum
        print_pass("Modified package has different checksum")
        
        # Add modified package (should update, not skip)
        print_info("Adding modified package with same name...")
        repo.add_packages([modified_rpm])
        print_pass("Modified package added (updated)")
        
        # Verify package was updated
        rpms = storage.list_files('el9/x86_64', suffix='.rpm')
        assert len(rpms) == 1  # Still only one package
        print_pass("Only one package exists (updated, not duplicated)")
    
    return True


def test_empty_repository():
    """Test that first add to empty repository works normally"""
    print_test("Empty Repository - First Add")
    
    rpm1, rpm2 = get_test_rpms()
    if not rpm1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        # Create config
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.rpm.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)
        
        # Create repo
        repo = YumRepo(config)
        
        # Add to empty repository
        print_info("Adding to empty repository...")
        repo.add_packages([rpm1])
        print_pass("Package added to empty repository")
        
        # Verify package exists
        storage = LocalStorageBackend(storage_dir)
        rpms = storage.list_files('el9/x86_64', suffix='.rpm')
        assert 'hello-world-1.0.0-1.el9.x86_64.rpm' in rpms
        print_pass("Package exists in storage")
    
    return True


def test_get_existing_checksums():
    """Test the _get_existing_package_checksums method"""
    print_test("Get Existing Checksums - Method Test")
    
    rpm1, rpm2 = get_test_rpms()
    if not rpm1:
        return False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = os.path.join(tmpdir, 'storage')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        # Create config
        config = RepoConfig()
        config.set('backend.type', 'local')
        config.set('backend.rpm.local.path', storage_dir)
        config.set('repo.cache_dir', cache_dir)
        config.set('validation.enabled', False)
        
        # Create repo
        repo = YumRepo(config)
        
        # Add packages
        print_info("Adding packages...")
        repo.add_packages([rpm1, rpm2])
        print_pass("Packages added")
        
        # Get checksums
        print_info("Getting existing checksums...")
        checksums = repo._get_existing_package_checksums('el9/x86_64')
        print_pass(f"Retrieved {len(checksums)} checksums")
        
        # Verify checksums
        assert 'hello-world-1.0.0-1.el9.x86_64.rpm' in checksums
        assert 'goodbye-forever-2.0.0-1.el9.x86_64.rpm' in checksums
        assert len(checksums) == 2
        print_pass("All package checksums retrieved correctly")
        
        # Verify checksum values are correct
        rpm1_checksum = repo._calculate_rpm_checksum(rpm1)
        assert checksums['hello-world-1.0.0-1.el9.x86_64.rpm'] == rpm1_checksum
        print_pass("Checksum values are correct")
    
    return True


def main():
    """Run all tests"""
    print()
    print("=" * 70)
    print("Package Deduplication Test Suite")
    print("=" * 70)
    
    tests = [
        test_empty_repository,
        test_duplicate_detection,
        test_multiple_duplicates,
        test_all_duplicates,
        test_checksum_change,
        test_get_existing_checksums,
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
