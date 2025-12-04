#!/usr/bin/env python3
"""
Test suite for Debian repository management

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import sys
import tempfile
import shutil

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


def test_init_repo():
    """Test initializing a new repository"""
    print_test("Initialize New Repository")
    
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
        
        print_info("Adding first package...")
        repo.add_packages([deb1])
        print_pass("Package added")
        
        # Verify structure
        assert os.path.exists(f"{storage_dir}/pool/main/h/hello-world/hello-world_1.0.0_amd64.deb")
        print_pass("Package in pool")
        
        assert os.path.exists(f"{storage_dir}/dists/focal/main/binary-amd64/Packages")
        print_pass("Packages file created")
        
        assert os.path.exists(f"{storage_dir}/dists/focal/Release")
        print_pass("Release file created")
    
    return True


def test_add_to_existing():
    """Test adding to existing repository"""
    print_test("Add to Existing Repository")
    
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
        
        print_info("Adding first package...")
        repo.add_packages([deb1])
        print_pass("First package added")
        
        print_info("Adding second package...")
        repo.add_packages([deb2])
        print_pass("Second package added")
        
        # Verify both packages exist
        assert os.path.exists(f"{storage_dir}/pool/main/h/hello-world/hello-world_1.0.0_amd64.deb")
        assert os.path.exists(f"{storage_dir}/pool/main/g/goodbye-forever/goodbye-forever_2.0.0_amd64.deb")
        print_pass("Both packages in pool")
        
        # Check Packages file
        with open(f"{storage_dir}/dists/focal/main/binary-amd64/Packages", 'r') as f:
            content = f.read()
        
        assert 'Package: hello-world' in content
        assert 'Package: goodbye-forever' in content
        print_pass("Both packages in Packages file")
    
    return True


def test_deduplication():
    """Test package deduplication"""
    print_test("Package Deduplication")
    
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
        
        print_info("Adding package first time...")
        repo.add_packages([deb1])
        print_pass("First add completed")
        
        print_info("Adding same package again...")
        repo.add_packages([deb1])
        print_pass("Second add completed (should skip)")
        
        # Verify only one package in pool
        pool_files = []
        for root, dirs, files in os.walk(f"{storage_dir}/pool"):
            pool_files.extend(files)
        
        assert len(pool_files) == 1
        print_pass("No duplicate in pool")
    
    return True


def test_remove_package():
    """Test package removal"""
    print_test("Package Removal")
    
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
        
        print_info("Adding two packages...")
        repo.add_packages([deb1, deb2])
        print_pass("Packages added")
        
        print_info("Removing one package...")
        repo.remove_packages(['hello-world'])
        print_pass("Package removed")
        
        # Verify package removed from pool
        assert not os.path.exists(f"{storage_dir}/pool/main/h/hello-world/hello-world_1.0.0_amd64.deb")
        print_pass("Package removed from pool")
        
        # Verify package removed from Packages file
        with open(f"{storage_dir}/dists/focal/main/binary-amd64/Packages", 'r') as f:
            content = f.read()
        
        assert 'Package: hello-world' not in content
        assert 'Package: goodbye-forever' in content
        print_pass("Package removed from metadata")
    
    return True


def test_mixed_operations():
    """Test mixed add/remove operations"""
    print_test("Mixed Operations")
    
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
        
        # Add both packages
        print_info("Adding both packages...")
        repo.add_packages([deb1, deb2])
        print_pass("Both added")
        
        # Try to add duplicate (should skip)
        print_info("Adding duplicate...")
        repo.add_packages([deb1])
        print_pass("Duplicate skipped")
        
        # Remove one
        print_info("Removing one...")
        repo.remove_packages(['goodbye-forever'])
        print_pass("One removed")
        
        # Add it back
        print_info("Adding it back...")
        repo.add_packages([deb2])
        print_pass("Added back")
        
        # Verify final state
        assert os.path.exists(f"{storage_dir}/pool/main/h/hello-world/hello-world_1.0.0_amd64.deb")
        assert os.path.exists(f"{storage_dir}/pool/main/g/goodbye-forever/goodbye-forever_2.0.0_amd64.deb")
        print_pass("Final state correct")
    
    return True


def main():
    """Run all tests"""
    print()
    print("=" * 70)
    print("Debian Repository Test Suite")
    print("=" * 70)
    
    tests = [
        test_init_repo,
        test_add_to_existing,
        test_deduplication,
        test_remove_package,
        test_mixed_operations,
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
