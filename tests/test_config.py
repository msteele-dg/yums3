#!/usr/bin/env python3
"""
Test YumConfig class

Tests dot notation configuration, legacy migration, and validation.
"""

import os
import sys
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.config import YumConfig, create_storage_backend_from_config


def test_basic_operations():
    """Test basic get/set/unset operations"""
    print("=" * 60)
    print("Test: Basic Operations")
    print("=" * 60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        config_file = f.name
        json.dump({}, f)
    
    try:
        config = YumConfig(config_file)
        
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
        config1 = YumConfig(config_file)
        config1.set('backend.type', 's3')
        config1.set('backend.s3.bucket', 'my-bucket')
        config1.set('backend.s3.profile', 'production')
        config1.save()
        print("✓ Config saved")
        
        # Load in new instance
        config2 = YumConfig(config_file)
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


def test_legacy_migration():
    """Test automatic migration from legacy config format"""
    print()
    print("=" * 60)
    print("Test: Legacy Migration")
    print("=" * 60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        config_file = f.name
        # Write old format config
        legacy_config = {
            'storage_type': 's3',
            's3_bucket': 'old-bucket',
            'aws_profile': 'old-profile',
            'local_repo_base': '/old/cache'
        }
        json.dump(legacy_config, f)
    
    try:
        # Load with auto-migration
        config = YumConfig(config_file, auto_migrate=True)
        
        # Check migrated values
        assert config.get('backend.type') == 's3'
        assert config.get('backend.s3.bucket') == 'old-bucket'
        assert config.get('backend.s3.profile') == 'old-profile'
        assert config.get('repo.cache_dir') == '/old/cache'
        print("✓ Legacy config migrated correctly")
        
        # Verify file was updated
        with open(config_file, 'r') as f:
            data = json.load(f)
        assert 'backend.type' in data
        assert 's3_bucket' not in data  # Old key should be gone
        print("✓ Config file updated to new format")
        
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
        # Valid S3 config
        config = YumConfig(config_file)
        config.set('backend.type', 's3')
        config.set('backend.s3.bucket', 'test-bucket')
        errors = config.validate()
        assert len(errors) == 0
        print("✓ Valid S3 config passes validation")
        
        # Invalid: missing bucket
        config2 = YumConfig(config_file)
        config2.set('backend.type', 's3')
        errors = config2.validate()
        assert len(errors) > 0
        assert any('bucket' in err.lower() for err in errors)
        print("✓ Missing bucket detected")
        
        # Valid local config
        config3 = YumConfig(config_file)
        config3.set('backend.type', 'local')
        config3.set('backend.local.path', '/tmp/test')
        errors = config3.validate()
        assert len(errors) == 0
        print("✓ Valid local config passes validation")
        
        # Invalid: missing path
        config4 = YumConfig(config_file)
        config4.set('backend.type', 'local')
        errors = config4.validate()
        assert len(errors) > 0
        assert any('path' in err.lower() for err in errors)
        print("✓ Missing path detected")
        
        # Invalid backend type
        config5 = YumConfig(config_file)
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
        # Create S3 backend
        config = YumConfig(config_file)
        config.set('backend.type', 's3')
        config.set('backend.s3.bucket', 'test-bucket')
        config.set('backend.s3.profile', 'default')
        
        backend = create_storage_backend_from_config(config)
        assert backend is not None
        assert hasattr(backend, 'bucket_name')
        assert backend.bucket_name == 'test-bucket'
        print("✓ S3 backend created correctly")
        
        # Create local backend
        config2 = YumConfig(config_file)
        config2.set('backend.type', 'local')
        config2.set('backend.local.path', '/tmp/test')
        
        backend2 = create_storage_backend_from_config(config2)
        assert backend2 is not None
        assert hasattr(backend2, 'base_path')
        print("✓ Local backend created correctly")
        
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
        # Start with legacy config
        legacy_config = {
            'storage_type': 's3',
            's3_bucket': 'my-yum-repo',
            'aws_profile': 'production',
            's3_endpoint_url': 'https://s3.us-west-2.amazonaws.com',
            'local_repo_base': '/var/cache/yums3'
        }
        json.dump(legacy_config, f)
    
    try:
        # Load and migrate
        config = YumConfig(config_file)
        print(f"✓ Loaded config from {config_file}")
        
        # Verify migration
        assert config.get('backend.type') == 's3'
        assert config.get('backend.s3.bucket') == 'my-yum-repo'
        print("✓ Legacy config migrated")
        
        # Validate
        errors = config.validate()
        if errors:
            print(f"✗ Validation errors: {errors}")
            return False
        print("✓ Config is valid")
        
        # Create backend (skip if AWS profile doesn't exist)
        try:
            backend = create_storage_backend_from_config(config)
            print(f"✓ Created backend: {backend.get_url()}")
        except Exception as e:
            # AWS profile might not exist in test environment
            print(f"⚠ Skipped backend creation (AWS profile not available): {e}")
        
        # Modify and save
        config.set('validation.enabled', False)
        config.save()
        print("✓ Modified and saved config")
        
        # Reload and verify
        config2 = YumConfig(config_file)
        assert config2.get('validation.enabled') == False
        assert config2.get('backend.s3.bucket') == 'my-yum-repo'
        print("✓ Reloaded config correctly")
        
        return True
    
    finally:
        os.unlink(config_file)


if __name__ == '__main__':
    print()
    print("YumConfig Test Suite")
    print()
    
    tests = [
        test_basic_operations,
        test_save_and_load,
        test_legacy_migration,
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
