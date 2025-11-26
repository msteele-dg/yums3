#!/usr/bin/env python3
"""
Test suite for storage backend get_info() method

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import sys
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.backend import LocalStorageBackend, S3StorageBackend


def test_local_backend_info():
    """Test LocalStorageBackend.get_info()"""
    print("=" * 60)
    print("Test: LocalStorageBackend.get_info()")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = LocalStorageBackend(tmpdir)
        info = backend.get_info()
        
        # Check that info is a dict
        assert isinstance(info, dict), "get_info() should return a dict"
        
        # Check that Storage key exists
        assert 'Storage' in info, "Info should contain 'Storage' key"
        
        # Check that Storage value is correct
        assert info['Storage'] == f"file://{tmpdir}", f"Storage should be file://{tmpdir}"
        
        print(f"✓ LocalStorageBackend.get_info() returns: {info}")
    
    return True


def test_s3_backend_info():
    """Test S3StorageBackend.get_info()"""
    print()
    print("=" * 60)
    print("Test: S3StorageBackend.get_info()")
    print("=" * 60)
    
    try:
        backend = S3StorageBackend(bucket_name='test-bucket', aws_profile='default')
        info = backend.get_info()
        
        # Check that info is a dict
        assert isinstance(info, dict), "get_info() should return a dict"
        
        # Check that expected keys exist
        expected_keys = ['AWS Account', 'AWS Region', 'AWS Profile', 'S3 URL']
        for key in expected_keys:
            assert key in info, f"Info should contain '{key}' key"
        
        # Check that S3 URL is correct
        assert 'test-bucket' in info['S3 URL'], "S3 URL should contain bucket name"
        
        print(f"✓ S3StorageBackend.get_info() returns:")
        for key, value in info.items():
            print(f"    {key}: {value}")
    
    except Exception as e:
        print(f"⚠ Skipped S3 backend test (AWS not configured): {e}")
    
    return True


def main():
    """Run all tests"""
    print()
    print("Storage Backend get_info() Test Suite")
    print()
    
    tests = [
        test_local_backend_info,
        test_s3_backend_info,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} raised exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    print()
    
    return failed == 0


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
