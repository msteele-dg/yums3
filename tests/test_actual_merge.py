#!/usr/bin/env python3
"""
Integration test for yums3 merge functionality
Tests the actual _merge_metadata function
"""

import os
import sys
import tempfile
import shutil
import subprocess
import gzip
import xml.etree.ElementTree as ET

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import the actual yums3 code
try:
    from yums3 import YumRepo
except ImportError:
    print("ERROR: Could not import yums3")
    sys.exit(1)

try:
    from core.sqlite_metadata import SQLiteMetadataManager
except ImportError:
    print("ERROR: Could not import sqlite_metadata")
    sys.exit(1)


def create_test_rpm(name, version, tmpdir):
    """Create a minimal test RPM"""
    rpm_name = f"{name}-{version}-1.el9.x86_64.rpm"
    rpm_path = os.path.join(tmpdir, rpm_name)
    
    # Create a minimal RPM using rpmbuild or fpm
    # For now, we'll skip actual RPM creation and just test metadata merge
    # In real test, you'd need actual RPMs
    return rpm_path, rpm_name


def test_merge_metadata():
    """Test that _merge_metadata correctly merges packages"""
    
    print("Testing _merge_metadata function...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create initial repo with 2 packages
        repo_dir = os.path.join(tmpdir, "repo")
        os.makedirs(repo_dir)
        
        # We need actual RPM files for createrepo_c to work
        # Let's check if we have any test RPMs available
        test_rpm_dir = "/tmp/rpmbuild/RPMS/x86_64"
        if not os.path.exists(test_rpm_dir):
            print(f"ERROR: No test RPMs found at {test_rpm_dir}")
            print("Please build some test RPMs first")
            return False
        
        # Get list of available RPMs
        rpms = [f for f in os.listdir(test_rpm_dir) if f.endswith('.rpm')]
        if len(rpms) < 3:
            print(f"ERROR: Need at least 3 RPMs for testing, found {len(rpms)}")
            return False
        
        print(f"Found {len(rpms)} test RPMs")
        
        # Copy first 2 RPMs to initial repo
        initial_rpms = rpms[:2]
        for rpm in initial_rpms:
            shutil.copy(os.path.join(test_rpm_dir, rpm), repo_dir)
        
        print(f"Initial repo: {initial_rpms}")
        
        # Create initial metadata
        result = subprocess.run(
            ['createrepo_c', '--no-database', repo_dir],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"ERROR: createrepo_c failed: {result.stderr}")
            return False
        
        print("✓ Created initial metadata")
        
        # Parse initial primary.xml to count packages
        repodata_dir = os.path.join(repo_dir, 'repodata')
        repomd_path = os.path.join(repodata_dir, 'repomd.xml')
        
        tree = ET.parse(repomd_path)
        root = tree.getroot()
        
        # Find primary.xml location
        NS_REPO = {'repo': 'http://linux.duke.edu/metadata/repo'}
        primary_file = None
        
        # Try with namespace first
        data_elements = root.findall('repo:data', NS_REPO)
        if not data_elements:
            # Try without namespace
            data_elements = root.findall('data')
        
        for data in data_elements:
            if data.get('type') == 'primary':
                location = data.find('repo:location', NS_REPO)
                if location is None:
                    location = data.find('location')
                if location is not None:
                    primary_file = location.get('href').replace('repodata/', '')
                    break
        
        if not primary_file:
            print("ERROR: Could not find primary metadata")
            return False
        
        primary_path = os.path.join(repodata_dir, primary_file)
        
        with gzip.open(primary_path, 'rt', encoding='utf-8') as f:
            primary_tree = ET.parse(f)
            primary_root = primary_tree.getroot()
        
        initial_count = int(primary_root.get('packages', '0'))
        print(f"Initial package count: {initial_count}")
        
        # Get list of packages in initial metadata
        NS = {'common': 'http://linux.duke.edu/metadata/common'}
        initial_packages = []
        for package in primary_root.findall('common:package', NS):
            if not package:
                package = primary_root.findall('package')
            name_elem = package.find('common:name', NS)
            if name_elem is None:
                name_elem = package.find('name')
            if name_elem is not None:
                initial_packages.append(name_elem.text)
        
        print(f"Initial packages in metadata: {initial_packages}")
        
        # Create temp repo with 1 new package
        temp_repo = os.path.join(tmpdir, "temp_repo")
        os.makedirs(temp_repo)
        
        new_rpm = rpms[2]
        shutil.copy(os.path.join(test_rpm_dir, new_rpm), temp_repo)
        
        print(f"New package to add: {new_rpm}")
        
        # Create metadata for new package
        result = subprocess.run(
            ['createrepo_c', '--no-database', temp_repo],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"ERROR: createrepo_c failed for temp repo: {result.stderr}")
            return False
        
        print("✓ Created temp metadata")
        
        # Now test the actual _merge_metadata function
        print("\nCalling _merge_metadata...")
        
        # Create a YumRepo instance (we need it for the method)
        # Use dummy S3 bucket since we're only testing merge
        try:
            repo = YumRepo(
                s3_bucket_name="test-bucket",
                local_repo_base=tmpdir,
                skip_validation=True
            )
        except SystemExit:
            # If AWS credentials fail, that's OK for this test
            print("Note: AWS credentials not available, but that's OK for this test")
            # We'll call the method directly without the instance
            pass
        
        # Call the merge function
        try:
            repo._merge_metadata(repo_dir, temp_repo, [new_rpm])
        except Exception as e:
            print(f"ERROR: _merge_metadata failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        print("✓ Merge completed")
        
        # Verify the merge
        # Re-parse the merged primary.xml
        tree = ET.parse(repomd_path)
        root = tree.getroot()
        
        # Find primary.xml location (it will have a new checksum)
        primary_file = None
        
        # Try with namespace first
        data_elements = root.findall('repo:data', NS_REPO)
        if not data_elements:
            # Try without namespace
            data_elements = root.findall('data')
        
        for data in data_elements:
            if data.get('type') == 'primary':
                location = data.find('repo:location', NS_REPO)
                if location is None:
                    location = data.find('location')
                if location is not None:
                    primary_file = location.get('href').replace('repodata/', '')
                    break
        
        if not primary_file:
            print("ERROR: Could not find primary metadata after merge")
            return False
        
        primary_path = os.path.join(repodata_dir, primary_file)
        
        with gzip.open(primary_path, 'rt', encoding='utf-8') as f:
            merged_tree = ET.parse(f)
            merged_root = merged_tree.getroot()
        
        merged_count = int(merged_root.get('packages', '0'))
        print(f"\nMerged package count: {merged_count}")
        print(f"Expected: {initial_count + 1}")
        
        # Get list of packages in merged metadata
        merged_packages = []
        for package in merged_root.findall('common:package', NS):
            if not package:
                package = merged_root.findall('package')
            name_elem = package.find('common:name', NS)
            if name_elem is None:
                name_elem = package.find('name')
            if name_elem is not None:
                merged_packages.append(name_elem.text)
        
        print(f"Packages in merged metadata: {merged_packages}")
        
        # Verify count
        if merged_count != initial_count + 1:
            print(f"❌ ERROR: Package count mismatch!")
            print(f"   Expected: {initial_count + 1}, Got: {merged_count}")
            return False
        
        if len(merged_packages) != merged_count:
            print(f"❌ ERROR: Declared count ({merged_count}) doesn't match actual packages ({len(merged_packages)})")
            return False
        
        # Check SQLite databases were created
        db_files = [f for f in os.listdir(repodata_dir) if f.endswith('.sqlite.bz2')]
        print(f"\nSQLite databases created: {len(db_files)}")
        for db_file in db_files:
            print(f"  - {db_file}")
        
        if len(db_files) == 0:
            print("❌ ERROR: No SQLite databases created!")
            return False
        
        print("\n✅ All merge tests passed!")
        return True


if __name__ == '__main__':
    success = test_merge_metadata()
    sys.exit(0 if success else 1)
