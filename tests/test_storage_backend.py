#!/usr/bin/env python3
"""
Test storage backend integration

This test creates a local repository using LocalStorageBackend
to verify the refactoring works correctly.
"""

import os
import sys
import tempfile
import shutil
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.backend import LocalStorageBackend
from core.config import YumConfig
from yums3 import YumRepo


def create_test_config(storage_path, cache_path):
    """Helper to create a test config"""
    config_file = os.path.join(tempfile.gettempdir(), f'test_config_{os.getpid()}.conf')
    with open(config_file, 'w') as f:
        json.dump({
            'backend.type': 'local',
            'backend.local.path': storage_path,
            'repo.cache_dir': cache_path,
            'validation.enabled': False
        }, f)
    return YumConfig(config_file)


def test_local_storage_init():
    """Test initializing a repository with LocalStorageBackend"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup paths
        storage_path = os.path.join(tmpdir, 'storage')
        cache_path = os.path.join(tmpdir, 'cache')
        
        # Create config and repo manager
        config = create_test_config(storage_path, cache_path)
        repo = YumRepo(config)
        
        # Copy test RPMs to temp location
        test_rpms_dir = 'test_rpms'
        rpm_files = [
            os.path.join(test_rpms_dir, 'hello-world-1.0.0-1.el9.x86_64.rpm'),
            os.path.join(test_rpms_dir, 'goodbye-forever-2.0.0-1.el9.x86_64.rpm')
        ]
        
        # Verify test RPMs exist
        for rpm in rpm_files:
            if not os.path.exists(rpm):
                print(f"ERROR: Test RPM not found: {rpm}")
                return False
        
        print("Testing LocalStorageBackend integration...")
        print(f"  Storage: {repo.storage.get_url()}")
        print(f"  Cache: {cache_path}")
        print()
        
        # Add packages
        try:
            repo.add_packages(rpm_files)
            print()
            print("✓ Successfully added packages to local storage")
            
            # Verify files exist in storage
            el9_x86_64_path = os.path.join(storage_path, 'el9', 'x86_64')
            if not os.path.exists(el9_x86_64_path):
                print("✗ ERROR: Repository directory not created")
                return False
            
            # Check RPMs
            for rpm in rpm_files:
                rpm_name = os.path.basename(rpm)
                rpm_path = os.path.join(el9_x86_64_path, rpm_name)
                if not os.path.exists(rpm_path):
                    print(f"✗ ERROR: RPM not found in storage: {rpm_name}")
                    return False
                print(f"  ✓ Found: {rpm_name}")
            
            # Check repodata
            repodata_path = os.path.join(el9_x86_64_path, 'repodata')
            if not os.path.exists(repodata_path):
                print("✗ ERROR: repodata directory not created")
                return False
            
            repomd_path = os.path.join(repodata_path, 'repomd.xml')
            if not os.path.exists(repomd_path):
                print("✗ ERROR: repomd.xml not created")
                return False
            
            print(f"  ✓ Found: repodata/repomd.xml")
            
            # List all repodata files
            repodata_files = os.listdir(repodata_path)
            print(f"  ✓ Repodata contains {len(repodata_files)} files")
            
            # Check for SQLite databases
            sqlite_files = [f for f in repodata_files if f.endswith('.sqlite.bz2')]
            print(f"  ✓ Found {len(sqlite_files)} SQLite databases")
            
            return True
            
        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_local_storage_merge():
    """Test merging packages with LocalStorageBackend"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup paths
        storage_path = os.path.join(tmpdir, 'storage')
        cache_path = os.path.join(tmpdir, 'cache')
        
        # Create config and repo manager
        config = create_test_config(storage_path, cache_path)
        repo = YumRepo(config)
        
        test_rpms_dir = 'test_rpms'
        
        print("\nTesting merge with LocalStorageBackend...")
        print(f"  Storage: {repo.storage.get_url()}")
        print()
        
        try:
            # Add first package
            rpm1 = [os.path.join(test_rpms_dir, 'hello-world-1.0.0-1.el9.x86_64.rpm')]
            print("Adding first package...")
            repo.add_packages(rpm1)
            print("  ✓ First package added")
            
            # Add second package (should trigger merge)
            rpm2 = [os.path.join(test_rpms_dir, 'goodbye-forever-2.0.0-1.el9.x86_64.rpm')]
            print("\nAdding second package (merge)...")
            repo.add_packages(rpm2)
            print("  ✓ Second package merged")
            
            # Verify both RPMs exist
            el9_x86_64_path = os.path.join(storage_path, 'el9', 'x86_64')
            rpms_in_storage = [f for f in os.listdir(el9_x86_64_path) if f.endswith('.rpm')]
            
            if len(rpms_in_storage) != 2:
                print(f"✗ ERROR: Expected 2 RPMs, found {len(rpms_in_storage)}")
                return False
            
            print(f"  ✓ Both RPMs present in storage")
            
            return True
            
        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == '__main__':
    print("=" * 60)
    print("Storage Backend Integration Tests")
    print("=" * 60)
    print()
    
    success = True
    
    # Test 1: Init
    if not test_local_storage_init():
        success = False
    
    # Test 2: Merge
    if not test_local_storage_merge():
        success = False
    
    print()
    print("=" * 60)
    if success:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)
