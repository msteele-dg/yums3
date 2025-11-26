#!/usr/bin/env python3
"""
Test suite for yums3 config command

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import sys
import json
import tempfile
import subprocess


def run_command(args, cwd=None):
    """Run yums3 config command and return output"""
    # Get absolute path to yums3.py (in parent directory)
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yums3_path = os.path.join(script_dir, 'yums3.py')
    
    cmd = ['python3', yums3_path] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def test_config_list():
    """Test config --list"""
    print("=" * 60)
    print("Test: config --list")
    print("=" * 60)
    
    returncode, stdout, stderr = run_command(['config', '--list'])
    
    assert returncode == 0, f"Command failed: {stderr}"
    assert 'backend.type' in stdout, "Missing backend.type in output"
    assert 'repo.cache_dir' in stdout, "Missing repo.cache_dir in output"
    print("✓ config --list works")
    return True


def test_config_get():
    """Test config get"""
    print()
    print("=" * 60)
    print("Test: config get")
    print("=" * 60)
    
    returncode, stdout, stderr = run_command(['config', 'backend.type'])
    
    assert returncode == 0, f"Command failed: {stderr}"
    assert stdout in ['s3', 'local'], f"Unexpected backend.type: {stdout}"
    print(f"✓ config get works (backend.type = {stdout})")
    return True


def test_config_set_and_get():
    """Test config set and get with local config"""
    print()
    print("=" * 60)
    print("Test: config set and get")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, 'test.conf')
        
        # Set a value
        returncode, stdout, stderr = run_command([
            'config', '--file', config_file,
            'backend.type', 'local'
        ])
        assert returncode == 0, f"Set failed: {stderr}"
        assert 'Set backend.type = local' in stdout, f"Unexpected output: {stdout}"
        print("✓ config set works")
        
        # Get the value
        returncode, stdout, stderr = run_command([
            'config', '--file', config_file,
            'backend.type'
        ])
        assert returncode == 0, f"Get failed: {stderr}"
        assert stdout == 'local', f"Expected 'local', got '{stdout}'"
        print("✓ config get works")
        
        # Verify file was created
        assert os.path.exists(config_file), "Config file not created"
        with open(config_file, 'r') as f:
            data = json.load(f)
        assert data['backend.type'] == 'local', "Config file has wrong value"
        print("✓ config file created correctly")
    
    return True


def test_config_unset():
    """Test config --unset"""
    print()
    print("=" * 60)
    print("Test: config --unset")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, 'test.conf')
        
        # Set a value
        run_command(['config', '--file', config_file, 'test.key', 'test-value'])
        
        # Verify it exists
        returncode, stdout, stderr = run_command(['config', '--file', config_file, 'test.key'])
        assert stdout == 'test-value', "Value not set"
        print("✓ Value set")
        
        # Unset it
        returncode, stdout, stderr = run_command(['config', '--file', config_file, '--unset', 'test.key'])
        assert returncode == 0, f"Unset failed: {stderr}"
        assert 'Unset test.key' in stdout, f"Unexpected output: {stdout}"
        print("✓ config --unset works")
        
        # Verify it's gone
        returncode, stdout, stderr = run_command(['config', '--file', config_file, 'test.key'])
        assert returncode == 1, "Key should not exist"
        print("✓ Key removed")
    
    return True


def test_config_validate():
    """Test config --validate"""
    print()
    print("=" * 60)
    print("Test: config --validate")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, 'test.conf')
        
        # Create invalid config (S3 without bucket)
        run_command(['config', '--file', config_file, 'backend.type', 's3'])
        
        # Validate should fail
        returncode, stdout, stderr = run_command(['config', '--file', config_file, '--validate'])
        assert returncode == 1, "Validation should fail"
        assert 'backend.s3.bucket is required' in stdout, f"Wrong error: {stdout}"
        print("✓ Invalid config detected")
        
        # Add bucket
        run_command(['config', '--file', config_file, 'backend.s3.bucket', 'test-bucket'])
        
        # Validate should pass
        returncode, stdout, stderr = run_command(['config', '--file', config_file, '--validate'])
        assert returncode == 0, f"Validation should pass: {stdout}"
        assert 'Configuration is valid' in stdout, f"Unexpected output: {stdout}"
        print("✓ Valid config accepted")
    
    return True


def test_config_locations():
    """Test --global, --local, --system flags"""
    print()
    print("=" * 60)
    print("Test: config location flags")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set local config (run in temp directory)
        returncode, stdout, stderr = run_command(['config', '--local', 'test.local', 'local-value'], cwd=tmpdir)
        assert returncode == 0, f"Local set failed: {stderr}"
        
        local_config = os.path.join(tmpdir, 'yums3.conf')
        assert os.path.exists(local_config), "Local config not created"
        print("✓ --local flag works")
        
        # Verify local config
        returncode, stdout, stderr = run_command(['config', '--local', 'test.local'], cwd=tmpdir)
        assert stdout == 'local-value', f"Expected 'local-value', got '{stdout}'"
        print("✓ Local config value correct")
    
    return True


def main():
    """Run all tests"""
    print()
    print("YumS3 Config Command Test Suite")
    print()
    
    tests = [
        test_config_list,
        test_config_get,
        test_config_set_and_get,
        test_config_unset,
        test_config_validate,
        test_config_locations,
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
