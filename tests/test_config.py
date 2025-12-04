#!/usr/bin/env python3
"""
Test RepoConfig class

Tests dot notation configuration, legacy migration, and validation.
"""

import os
import sys
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.backend import create_storage_backend
from core.config import RepoConfig


def test_type_specific_config():
    """Test type-specific configuration with fallback"""
    print("=" * 60)
    print("Test: Type-Specific Configuration")
    print("=" * 60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        config_file = f.name
        json.dump({}, f)
    
    try:
        config = RepoConfig(config_file)
        
        # Test with only shared config
        config.set('backend.s3.bucket', 'shared-bucket')
        assert config.get_for_type('backend.s3.bucket', 'rpm') == 'shared-bucket'
        assert config.get_for_type('backend.s3.bucket', 'deb') == 'shared-bucket'
        print("✓ Shared config works for both types")
        
        # Test with type-specific override
        config.set('backend.rpm.s3.bucket', 'rpm-bucket')
        assert config.get_for_type('backend.s3.bucket', 'rpm') == 'rpm-bucket'
        assert config.get_for_type('backend.s3.bucket', 'deb') == 'shared-bucket'
        print("✓ Type-specific override works")
        
        # Test with both type-specific configs
        config.set('backend.deb.s3.bucket', 'deb-bucket')
        assert config.get_for_type('backend.s3.bucket', 'rpm') == 'rpm-bucket'
        assert config.get_for_type('backend.s3.bucket', 'deb') == 'deb-bucket'
        print("✓ Both type-specific configs work independently")
        
        # Test with default value
        assert config.get_for_type('backend.s3.profile', 'rpm', 'default-profile') == 'default-profile'
        print("✓ Default value works when key not set")
        
        # Test cache_dir
        config.set('repo.rpm.cache_dir', '/var/cache/yums3')
        config.set('repo.deb.cache_dir', '/var/cache/debs3')
        assert config.get('repo.rpm.cache_dir') == '/var/cache/yums3'
        assert config.get('repo.deb.cache_dir') == '/var/cache/debs3'
        print("✓ Type-specific cache directories work")
        
        return True
    
    finally:
        os.unlink(config_file)


def test_basic_operations():
    """Test basic get/set/unset operations"""
    print()
    print("=" * 60)
    print("Test: Basic Operations")
    print("=" * 60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        config_file = f.name
        json.dump({}, f)
    
    try:
        config = RepoConfig(config_file)
        
        # Test set and get
        config.set('backend.type', 's3')
        config.set('backend.s3.bucket', 'test-bucket')
        
        assert config.get('backend.type') == 's3'
        assert config.get('backend.s3.bucket') == 'test-bucket'
        print("✓ Set and get work correctly")
        
        # Test default values
        assert config.get('validation.enabled') == True
        print("✓ Default values work correctly")
        
        # Test get with custom default
        assert config.get('nonexistent.key', 'default') == 'default'
        print("✓ Custom defaults work correctly")
        
        # Test has
        assert config.has('backend.type') == True
        assert config.has('nonexistent.key') == False
        print("✓ Has() works correctly")
        
        # Test unset
        config.unset('backend.s3.bucket')
        assert config.get('backend.s3.bucket') is None
        print("✓ Unset works correctly")
        
        # Test list_all
        all_config = config.list_all()
        assert 'backend.type' in all_config
        assert 'validation.enabled' in all_config
        print("✓ List all works correctly")
        
        # Test get_section
        config.set('backend.s3.bucket', 'test-bucket')
        config.set('backend.s3.profile', 'default')
        s3_config = config.get_section('backend.s3')
        assert 'backend.s3.bucket' in s3_config
        assert 'backend.s3.profile' in s3_config
        print("✓ Get section works correctly")
        
        return True
    
    finally:
        os.unlink(config_file)


def test_save_and_load():
    """Test saving and loading configuration"""
    print()
    print("=" * 60)
    print("Test: Save and Load")
    print("=" * 60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        config_file = f.name
        json.dump({}, f)
    
    try:
        # Create and save config
        config1 = RepoConfig(config_file)
        config1.set('backend.type', 's3')
        config1.set('backend.s3.bucket', 'my-bucket')
        config1.set('backend.s3.profile', 'production')
        config1.save()
        print("✓ Config saved")
        
        # Load in new instance
        config2 = RepoConfig(config_file)
        assert config2.get('backend.type') == 's3'
        assert config2.get('backend.s3.bucket') == 'my-bucket'
        assert config2.get('backend.s3.profile') == 'production'
        print("✓ Config loaded correctly")
        
        # Verify file format
        with open(config_file, 'r') as f:
            data = json.load(f)
        assert 'backend.type' in data
        assert 'backend.s3.bucket' in data
        print("✓ File format is correct (dot notation)")
        
        return True
    
    finally:
        os.unlink(config_file)


def test_validation():
    """Test configuration validation"""
    print()
    print("=" * 60)
    print("Test: Validation")
    print("=" * 60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        config_file = f.name
        json.dump({}, f)
    
    try:
        # Valid backend type
        config = RepoConfig(config_file)
        config.set('backend.type', 's3')
        errors = config.validate()
        assert len(errors) == 0
        print("✓ Valid backend type passes validation")
        
        # Valid backend type (local)
        config2 = RepoConfig(config_file)
        config2.set('backend.type', 'local')
        errors = config2.validate()
        assert len(errors) == 0
        print("✓ Valid local backend type passes validation")
        
        # Invalid backend type
        config5 = RepoConfig(config_file)
        config5.set('backend.type', 'invalid')
        errors = config5.validate()
        assert len(errors) > 0
        assert any('invalid' in err.lower() for err in errors)
        print("✓ Invalid backend type detected")
        
        return True
    
    finally:
        os.unlink(config_file)


def test_storage_backend_creation():
    """Test creating storage backends from config"""
    print()
    print("=" * 60)
    print("Test: Storage Backend Creation")
    print("=" * 60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        config_file = f.name
        json.dump({}, f)
    
    try:
        # Create S3 backend (shared config)
        config = RepoConfig(config_file)
        config.set('backend.type', 's3')
        config.set('backend.s3.bucket', 'test-bucket')
        config.set('backend.s3.profile', 'default')
        
        backend = create_storage_backend(config, 'rpm')
        assert backend is not None
        assert hasattr(backend, 'bucket_name')
        assert backend.bucket_name == 'test-bucket'
        print("✓ S3 backend created correctly (shared config)")
        
        # Create S3 backend (type-specific config)
        config1b = RepoConfig(config_file)
        config1b.set('backend.type', 's3')
        config1b.set('backend.rpm.s3.bucket', 'rpm-bucket')
        config1b.set('backend.deb.s3.bucket', 'deb-bucket')
        
        rpm_backend = create_storage_backend(config1b, 'rpm')
        assert rpm_backend.bucket_name == 'rpm-bucket'
        deb_backend = create_storage_backend(config1b, 'deb')
        assert deb_backend.bucket_name == 'deb-bucket'
        print("✓ S3 backend created correctly (type-specific config)")
        
        # Create local backend
        config2 = RepoConfig(config_file)
        config2.set('backend.type', 'local')
        config2.set('backend.local.path', '/tmp/test')
        
        backend2 = create_storage_backend(config2, 'rpm')
        assert backend2 is not None
        assert hasattr(backend2, 'base_path')
        print("✓ Local backend created correctly (shared config)")
        
        # Create local backend (type-specific)
        config2b = RepoConfig(config_file)
        config2b.set('backend.type', 'local')
        config2b.set('backend.rpm.local.path', '/tmp/rpm')
        config2b.set('backend.deb.local.path', '/tmp/deb')
        
        rpm_backend2 = create_storage_backend(config2b, 'rpm')
        assert rpm_backend2.base_path == '/tmp/rpm'
        deb_backend2 = create_storage_backend(config2b, 'deb')
        assert deb_backend2.base_path == '/tmp/deb'
        print("✓ Local backend created correctly (type-specific config)")
        
        return True
    
    finally:
        os.unlink(config_file)


def test_real_world_scenario():
    """Test a real-world configuration scenario"""
    print()
    print("=" * 60)
    print("Test: Real-World Scenario")
    print("=" * 60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        config_file = f.name
        # Start with a config
        test_config = {
            'backend.type': 's3',
            'backend.s3.bucket': 'my-yum-repo',
            'backend.s3.profile': 'production',
            'backend.s3.endpoint': 'https://s3.us-west-2.amazonaws.com',
            'repo.rpm.cache_dir': '/var/cache/yums3'
        }
        json.dump(test_config, f)
    
    try:
        # Load config
        config = RepoConfig(config_file)
        print(f"✓ Loaded config from {config_file}")
        
        # Verify values
        assert config.get('backend.type') == 's3'
        assert config.get('backend.s3.bucket') == 'my-yum-repo'
        print("✓ Config loaded correctly")
        
        # Validate
        errors = config.validate()
        if errors:
            print(f"✗ Validation errors: {errors}")
            return False
        print("✓ Config is valid")
        
        # Create backend (skip if AWS profile doesn't exist)
        try:
            backend = create_storage_backend(config)
            print(f"✓ Created backend: {backend.get_url()}")
        except Exception as e:
            # AWS profile might not exist in test environment
            print(f"⚠ Skipped backend creation (AWS profile not available): {e}")
        
        # Modify and save
        config.set('validation.enabled', False)
        config.save()
        print("✓ Modified and saved config")
        
        # Reload and verify
        config2 = RepoConfig(config_file)
        assert config2.get('validation.enabled') == False
        assert config2.get('backend.s3.bucket') == 'my-yum-repo'
        print("✓ Reloaded config correctly")
        
        return True
    
    finally:
        os.unlink(config_file)


if __name__ == '__main__':
    print()
    print("RepoConfig Test Suite")
    print()
    
    tests = [
        test_type_specific_config,
        test_basic_operations,
        test_save_and_load,
        test_validation,
        test_storage_backend_creation,
        test_real_world_scenario,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"✗ {test.__name__} failed")
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__} raised exception: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    sys.exit(0 if failed == 0 else 1)
