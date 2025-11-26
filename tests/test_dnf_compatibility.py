#!/usr/bin/env python3
"""
Test DNF compatibility of yums3-generated repositories

This test verifies that repositories created by yums3 are fully
compatible with DNF and produce the same results as createrepo_c.
"""

import os
import sys
import tempfile
import subprocess
import shutil

def run_command(cmd, check=True):
    """Run a command and return output"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def test_dnf_compatibility():
    """Test that yums3 repos work with DNF"""
    
    print("=" * 70)
    print("DNF Compatibility Test")
    print("=" * 70)
    print()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        createrepo_dir = os.path.join(tmpdir, 'createrepo')
        yums3_dir = os.path.join(tmpdir, 'yums3')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        os.makedirs(createrepo_dir)
        os.makedirs(yums3_dir)
        
        # Copy test RPMs
        test_rpms = ['test_rpms/hello-world-1.0.0-1.el9.x86_64.rpm',
                     'test_rpms/goodbye-forever-2.0.0-1.el9.x86_64.rpm']
        
        for rpm in test_rpms:
            shutil.copy(rpm, createrepo_dir)
        
        print("1. Creating repository with createrepo_c...")
        run_command(f'createrepo_c {createrepo_dir}')
        print("   ✓ createrepo_c repository created")
        
        print()
        print("2. Creating repository with yums3...")
        
        # Create config
        config_path = os.path.join(tmpdir, 'yums3.conf')
        with open(config_path, 'w') as f:
            f.write(f'{{\n')
            f.write(f'  "storage_type": "local",\n')
            f.write(f'  "local_storage_path": "{yums3_dir}",\n')
            f.write(f'  "local_repo_base": "{cache_dir}"\n')
            f.write(f'}}\n')
        
        # Add packages
        rpm_args = ' '.join(test_rpms)
        yums3_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'yums3.py')
        stdout, stderr, _ = run_command(f'python3 {yums3_path} --config {config_path} -y {rpm_args}')
        print("   ✓ yums3 repository created")
        
        yums3_repo_dir = os.path.join(yums3_dir, 'el9', 'x86_64')
        
        print()
        print("3. Testing with DNF...")
        
        # Test createrepo_c version
        print("   Testing createrepo_c repository...")
        stdout, stderr, rc = run_command(
            f'dnf repoquery --repofrompath=test_createrepo,{createrepo_dir} '
            f'--repo=test_createrepo -a 2>&1',
            check=False
        )
        
        createrepo_packages = [line for line in stdout.split('\n') 
                              if line and not line.startswith('Added') 
                              and not line.startswith('test_')]
        
        if len(createrepo_packages) != 2:
            print(f"   ✗ ERROR: Expected 2 packages, got {len(createrepo_packages)}")
            print(f"   Output: {stdout}")
            return False
        
        print(f"   ✓ createrepo_c: Found {len(createrepo_packages)} packages")
        for pkg in sorted(createrepo_packages):
            print(f"     - {pkg}")
        
        # Test yums3 version
        print()
        print("   Testing yums3 repository...")
        stdout, stderr, rc = run_command(
            f'dnf repoquery --repofrompath=test_yums3,{yums3_repo_dir} '
            f'--repo=test_yums3 -a 2>&1',
            check=False
        )
        
        yums3_packages = [line for line in stdout.split('\n') 
                         if line and not line.startswith('Added') 
                         and not line.startswith('test_')]
        
        if len(yums3_packages) != 2:
            print(f"   ✗ ERROR: Expected 2 packages, got {len(yums3_packages)}")
            print(f"   Output: {stdout}")
            return False
        
        print(f"   ✓ yums3: Found {len(yums3_packages)} packages")
        for pkg in sorted(yums3_packages):
            print(f"     - {pkg}")
        
        # Compare package lists
        print()
        print("4. Comparing results...")
        if sorted(createrepo_packages) == sorted(yums3_packages):
            print("   ✓ Package lists match!")
        else:
            print("   ✗ ERROR: Package lists differ")
            print(f"   createrepo_c: {sorted(createrepo_packages)}")
            print(f"   yums3:        {sorted(yums3_packages)}")
            return False
        
        print()
        print("5. Verifying metadata structure...")
        
        # Check that all expected files exist
        createrepo_files = set(os.listdir(os.path.join(createrepo_dir, 'repodata')))
        yums3_files = set(os.listdir(os.path.join(yums3_repo_dir, 'repodata')))
        
        # Both should have repomd.xml
        if 'repomd.xml' not in createrepo_files or 'repomd.xml' not in yums3_files:
            print("   ✗ ERROR: Missing repomd.xml")
            return False
        
        # Both should have primary, filelists, other (xml and sqlite)
        required_types = ['primary.xml.gz', 'filelists.xml.gz', 'other.xml.gz',
                         'primary.sqlite.bz2', 'filelists.sqlite.bz2', 'other.sqlite.bz2']
        
        for req_type in required_types:
            createrepo_has = any(f.endswith(req_type) for f in createrepo_files)
            yums3_has = any(f.endswith(req_type) for f in yums3_files)
            
            if not createrepo_has or not yums3_has:
                print(f"   ✗ ERROR: Missing {req_type}")
                return False
        
        print(f"   ✓ Both repos have all required metadata files")
        print(f"     createrepo_c: {len(createrepo_files)} files")
        print(f"     yums3:        {len(yums3_files)} files")
        
        return True

def test_merge_compatibility():
    """Test that merged repos work with DNF"""
    
    print()
    print("=" * 70)
    print("Merge Compatibility Test")
    print("=" * 70)
    print()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        yums3_dir = os.path.join(tmpdir, 'yums3')
        cache_dir = os.path.join(tmpdir, 'cache')
        
        os.makedirs(yums3_dir)
        
        # Create config
        config_path = os.path.join(tmpdir, 'yums3.conf')
        with open(config_path, 'w') as f:
            f.write(f'{{\n')
            f.write(f'  "storage_type": "local",\n')
            f.write(f'  "local_storage_path": "{yums3_dir}",\n')
            f.write(f'  "local_repo_base": "{cache_dir}"\n')
            f.write(f'}}\n')
        
        print("1. Adding first package...")
        yums3_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'yums3.py')
        run_command(f'python3 {yums3_path} --config {config_path} -y test_rpms/hello-world-1.0.0-1.el9.x86_64.rpm')
        print("   ✓ First package added")
        
        print()
        print("2. Adding second package (merge)...")
        run_command(f'python3 {yums3_path} --config {config_path} -y test_rpms/goodbye-forever-2.0.0-1.el9.x86_64.rpm')
        print("   ✓ Second package merged")
        
        yums3_repo_dir = os.path.join(yums3_dir, 'el9', 'x86_64')
        
        print()
        print("3. Testing merged repository with DNF...")
        stdout, stderr, rc = run_command(
            f'dnf repoquery --repofrompath=test_merged,{yums3_repo_dir} '
            f'--repo=test_merged -a 2>&1',
            check=False
        )
        
        packages = [line for line in stdout.split('\n') 
                   if line and not line.startswith('Added') 
                   and not line.startswith('test_')]
        
        if len(packages) != 2:
            print(f"   ✗ ERROR: Expected 2 packages, got {len(packages)}")
            print(f"   Output: {stdout}")
            return False
        
        print(f"   ✓ Found {len(packages)} packages in merged repository")
        for pkg in sorted(packages):
            print(f"     - {pkg}")
        
        # Verify both packages are present
        expected = ['goodbye-forever-0:2.0.0-1.el9.x86_64', 'hello-world-0:1.0.0-1.el9.x86_64']
        if sorted(packages) == sorted(expected):
            print("   ✓ Both packages present and correct")
        else:
            print("   ✗ ERROR: Package list incorrect")
            return False
        
        return True

if __name__ == '__main__':
    print()
    success = True
    
    if not test_dnf_compatibility():
        success = False
    
    if not test_merge_compatibility():
        success = False
    
    print()
    print("=" * 70)
    if success:
        print("✓ All DNF compatibility tests passed!")
        print()
        print("CONCLUSION: yums3 generates DNF-compatible repositories")
        print("=" * 70)
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        print("=" * 70)
        sys.exit(1)
