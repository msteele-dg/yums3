#!/usr/bin/env python3
"""
Test AWS_PROFILE environment variable handling

Tests that the S3StorageBackend correctly picks up AWS_PROFILE from environment.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.backend import S3StorageBackend


def test_aws_profile_env_var():
    """Test that AWS_PROFILE environment variable is picked up"""
    print("=" * 60)
    print("Test: AWS_PROFILE Environment Variable")
    print("=" * 60)
    
    # Save original AWS_PROFILE if it exists
    original_profile = os.environ.get('AWS_PROFILE')
    
    try:
        # Test 1: No profile set, no env var
        if 'AWS_PROFILE' in os.environ:
            del os.environ['AWS_PROFILE']
        
        backend1 = S3StorageBackend('test-bucket')
        assert backend1.aws_profile is None
        print("✓ Test 1: No profile, no env var - aws_profile=None")
        
        # Test 2: AWS_PROFILE environment variable set
        os.environ['AWS_PROFILE'] = 'test-env-profile'
        backend2 = S3StorageBackend('test-bucket')
        assert backend2.aws_profile == 'test-env-profile'
        print("✓ Test 2: AWS_PROFILE env var picked up correctly")
        
        # Test 3: Explicit profile overrides AWS_PROFILE
        backend3 = S3StorageBackend('test-bucket', aws_profile='explicit-profile')
        assert backend3.aws_profile == 'explicit-profile'
        print("✓ Test 3: Explicit profile overrides AWS_PROFILE")
        
        # Test 4: 'default' profile with AWS_PROFILE set should use env var
        backend4 = S3StorageBackend('test-bucket', aws_profile='default')
        assert backend4.aws_profile == 'test-env-profile'
        print("✓ Test 4: 'default' profile uses AWS_PROFILE env var")
        
        # Test 5: Empty string profile with AWS_PROFILE set should use env var
        backend5 = S3StorageBackend('test-bucket', aws_profile='')
        assert backend5.aws_profile == 'test-env-profile'
        print("✓ Test 5: Empty profile uses AWS_PROFILE env var")
        
        # Test 6: None profile with AWS_PROFILE set should use env var
        backend6 = S3StorageBackend('test-bucket', aws_profile=None)
        assert backend6.aws_profile == 'test-env-profile'
        print("✓ Test 6: None profile uses AWS_PROFILE env var")
        
        return True
        
    finally:
        # Restore original AWS_PROFILE
        if original_profile:
            os.environ['AWS_PROFILE'] = original_profile
        elif 'AWS_PROFILE' in os.environ:
            del os.environ['AWS_PROFILE']


if __name__ == '__main__':
    print()
    print("AWS Profile Environment Variable Test")
    print()
    
    try:
        if test_aws_profile_env_var():
            print()
            print("=" * 60)
            print("All tests passed!")
            print("=" * 60)
            sys.exit(0)
        else:
            print()
            print("=" * 60)
            print("Tests failed!")
            print("=" * 60)
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test raised exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
