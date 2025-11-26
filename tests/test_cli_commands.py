#!/usr/bin/env python3
"""
Test suite for yums3 CLI commands

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import sys
import subprocess
import tempfile


def run_command(args):
    """Run yums3 command and return output"""
    # Get absolute path to yums3.py (in parent directory)
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yums3_path = os.path.join(script_dir, 'yums3.py')
    
    cmd = ['python3', yums3_path] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def test_help_commands():
    """Test help output for all commands"""
    print("=" * 60)
    print("Test: Help Commands")
    print("=" * 60)
    
    commands = [
        [],
        ['add', '--help'],
        ['remove', '--help'],
        ['validate', '--help'],
        ['config', '--help'],
    ]
    
    for cmd in commands:
        returncode, stdout, stderr = run_command(cmd + ['--help'] if not cmd or cmd[-1] != '--help' else cmd)
        assert returncode == 0, f"Help failed for {cmd}: {stderr}"
        assert 'usage:' in stdout.lower(), f"No usage in help for {cmd}"
    
    print("✓ All help commands work")
    return True


def test_config_command():
    """Test config command still works"""
    print()
    print("=" * 60)
    print("Test: Config Command")
    print("=" * 60)
    
    returncode, stdout, stderr = run_command(['config', '--list'])
    assert returncode == 0, f"Config list failed: {stderr}"
    assert 'backend.type' in stdout, "Missing backend.type in config list"
    
    print("✓ Config command works")
    return True


def test_validate_command():
    """Test validate command syntax"""
    print()
    print("=" * 60)
    print("Test: Validate Command Syntax")
    print("=" * 60)
    
    # Test with invalid format (should fail)
    returncode, stdout, stderr = run_command(['validate', 'invalid'])
    assert returncode != 0, "Should fail with invalid format"
    
    print("✓ Validate command syntax works")
    return True


def test_add_command_syntax():
    """Test add command requires files"""
    print()
    print("=" * 60)
    print("Test: Add Command Syntax")
    print("=" * 60)
    
    # Test without files (should fail)
    returncode, stdout, stderr = run_command(['add'])
    assert returncode != 0, "Should fail without files"
    assert 'required' in stderr.lower() or 'error' in stderr.lower(), "Should show error about required files"
    
    print("✓ Add command syntax validation works")
    return True


def test_remove_command_syntax():
    """Test remove command requires files"""
    print()
    print("=" * 60)
    print("Test: Remove Command Syntax")
    print("=" * 60)
    
    # Test without files (should fail)
    returncode, stdout, stderr = run_command(['remove'])
    assert returncode != 0, "Should fail without files"
    assert 'required' in stderr.lower() or 'error' in stderr.lower(), "Should show error about required files"
    
    print("✓ Remove command syntax validation works")
    return True


def test_command_required():
    """Test that a command is required"""
    print()
    print("=" * 60)
    print("Test: Command Required")
    print("=" * 60)
    
    # Test without command (should fail or show help)
    returncode, stdout, stderr = run_command([])
    # Should either fail or show help
    assert returncode != 0 or 'usage:' in stdout.lower(), "Should require a command"
    
    print("✓ Command requirement works")
    return True


def main():
    """Run all tests"""
    print()
    print("YumS3 CLI Commands Test Suite")
    print()
    
    tests = [
        test_help_commands,
        test_config_command,
        test_validate_command,
        test_add_command_syntax,
        test_remove_command_syntax,
        test_command_required,
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
