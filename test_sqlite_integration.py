#!/usr/bin/env python3
"""
Test script for SQLite integration in yums3

This script validates that SQLite databases are properly created and integrated
into the YUM repository metadata.
"""

import os
import sys
import tempfile
import shutil
import gzip
import bz2
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

# Color output
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


def test_sqlite_metadata_module():
    """Test that sqlite_metadata module can be imported"""
    print_test("Import sqlite_metadata module")
    
    try:
        from sqlite_metadata import SQLiteMetadataManager
        print_pass("Module imported successfully")
        return True
    except ImportError as e:
        print_fail(f"Failed to import: {e}")
        return False


def test_create_sample_metadata():
    """Test creating SQLite databases from sample XML metadata"""
    print_test("Create SQLite databases from XML")
    
    try:
        from sqlite_metadata import SQLiteMetadataManager
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as tmpdir:
            repodata_dir = os.path.join(tmpdir, 'repodata')
            os.makedirs(repodata_dir)
            
            # Create minimal primary.xml.gz
            primary_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://linux.duke.edu/metadata/common" xmlns:rpm="http://linux.duke.edu/metadata/rpm" packages="1">
  <package type="rpm">
    <name>test-package</name>
    <arch>x86_64</arch>
    <version epoch="0" ver="1.0" rel="1.el9"/>
    <checksum type="sha256" pkgid="YES">abc123def456</checksum>
    <summary>Test package</summary>
    <description>A test package for validation</description>
    <packager>Test User</packager>
    <url>https://example.com</url>
    <time file="1234567890" build="1234567890"/>
    <size package="1000" installed="2000" archive="1500"/>
    <location href="test-package-1.0-1.el9.x86_64.rpm"/>
    <format>
      <rpm:license>MIT</rpm:license>
      <rpm:vendor>Test Vendor</rpm:vendor>
      <rpm:group>Development/Tools</rpm:group>
      <rpm:buildhost>localhost</rpm:buildhost>
      <rpm:sourcerpm>test-package-1.0-1.el9.src.rpm</rpm:sourcerpm>
      <rpm:header-range start="280" end="2024"/>
      <rpm:provides>
        <rpm:entry name="test-package" flags="EQ" epoch="0" ver="1.0" rel="1.el9"/>
      </rpm:provides>
      <rpm:requires>
        <rpm:entry name="glibc" flags="GE" epoch="0" ver="2.34"/>
      </rpm:requires>
    </format>
  </package>
</metadata>'''
            
            primary_path = os.path.join(repodata_dir, 'primary.xml.gz')
            with gzip.open(primary_path, 'wt', encoding='utf-8') as f:
                f.write(primary_xml)
            
            print_info(f"Created test primary.xml.gz")
            
            # Create SQLite database
            mgr = SQLiteMetadataManager(repodata_dir)
            db_path = mgr.create_primary_db(primary_path)
            
            print_pass(f"Created primary.sqlite at {os.path.basename(db_path)}")
            
            # Verify database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            expected_tables = ['db_info', 'packages', 'provides', 'requires', 'conflicts', 'obsoletes', 'files']
            for table in expected_tables:
                if table in tables:
                    print_pass(f"Table '{table}' exists")
                else:
                    print_fail(f"Table '{table}' missing")
                    return False
            
            # Check package count
            cursor.execute("SELECT COUNT(*) FROM packages")
            count = cursor.fetchone()[0]
            if count == 1:
                print_pass(f"Package count correct: {count}")
            else:
                print_fail(f"Package count incorrect: {count} (expected 1)")
                return False
            
            # Check package data
            cursor.execute("SELECT name, arch, version FROM packages")
            row = cursor.fetchone()
            if row == ('test-package', 'x86_64', '1.0'):
                print_pass(f"Package data correct: {row}")
            else:
                print_fail(f"Package data incorrect: {row}")
                return False
            
            conn.close()
            
            # Test compression
            compressed_path = mgr.compress_sqlite(db_path)
            if compressed_path.endswith('.bz2'):
                print_pass(f"Database compressed: {os.path.basename(compressed_path)}")
            else:
                print_fail(f"Compression failed")
                return False
            
            # Verify compressed file can be decompressed
            with bz2.open(compressed_path, 'rb') as f:
                data = f.read()
                if len(data) > 0:
                    print_pass(f"Compressed database is valid ({len(data)} bytes)")
                else:
                    print_fail("Compressed database is empty")
                    return False
            
            return True
            
    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_repomd_integration():
    """Test that repomd.xml properly references SQLite databases"""
    print_test("Verify repomd.xml integration")
    
    print_info("This test requires a real repository with SQLite databases")
    print_info("Run yums3.py to add a package, then check repodata/repomd.xml")
    
    # Check if we have a local test repo
    test_repo = os.path.expanduser("~/yum-repo")
    if not os.path.exists(test_repo):
        print_info(f"No test repository found at {test_repo}")
        return True
    
    # Find first repodata directory
    for root, dirs, files in os.walk(test_repo):
        if 'repomd.xml' in files:
            repomd_path = os.path.join(root, 'repomd.xml')
            print_info(f"Found repomd.xml: {repomd_path}")
            
            try:
                tree = ET.parse(repomd_path)
                root_elem = tree.getroot()
                
                # Check for database entries
                data_elements = root_elem.findall('data')
                db_types = []
                xml_types = []
                
                for data in data_elements:
                    data_type = data.get('type')
                    if data_type:
                        if data_type.endswith('_db'):
                            db_types.append(data_type)
                        else:
                            xml_types.append(data_type)
                
                print_info(f"XML metadata: {', '.join(xml_types)}")
                print_info(f"SQLite databases: {', '.join(db_types)}")
                
                if db_types:
                    print_pass(f"Found {len(db_types)} SQLite database(s)")
                    
                    # Verify each database entry has required fields
                    for data in data_elements:
                        data_type = data.get('type')
                        if data_type and data_type.endswith('_db'):
                            checksum = data.find('checksum')
                            location = data.find('location')
                            size = data.find('size')
                            db_version = data.find('database_version')
                            
                            if all([checksum is not None, location is not None, 
                                   size is not None, db_version is not None]):
                                print_pass(f"{data_type}: all required fields present")
                            else:
                                print_fail(f"{data_type}: missing required fields")
                                return False
                else:
                    print_fail("No SQLite databases found in repomd.xml")
                    return False
                
                return True
                
            except Exception as e:
                print_fail(f"Failed to parse repomd.xml: {e}")
                return False
            
            break
    
    return True


def test_dnf_compatibility():
    """Test that the repository is compatible with dnf"""
    print_test("DNF compatibility check")
    
    print_info("This test checks if dnf can read the repository")
    print_info("Requires: dnf installed and a test repository")
    
    # Check if dnf is available
    if shutil.which('dnf') is None:
        print_info("dnf not found, skipping compatibility test")
        return True
    
    test_repo = os.path.expanduser("~/yum-repo")
    if not os.path.exists(test_repo):
        print_info(f"No test repository found at {test_repo}")
        return True
    
    # Find first repo directory
    for root, dirs, files in os.walk(test_repo):
        if 'repodata' in dirs:
            repo_path = root
            print_info(f"Testing repository: {repo_path}")
            
            # Create temporary repo config
            with tempfile.NamedTemporaryFile(mode='w', suffix='.repo', delete=False) as f:
                f.write(f"""[test-repo]
name=Test Repository
baseurl=file://{repo_path}
enabled=1
gpgcheck=0
""")
                repo_config = f.name
            
            try:
                import subprocess
                
                # Try to list packages
                result = subprocess.run(
                    ['dnf', 'repoquery', '--repofrompath', f'test,file://{repo_path}', 
                     '--repo', 'test', '--disablerepo=*', '--enablerepo=test', '-a'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    packages = result.stdout.strip().split('\n')
                    if packages and packages[0]:
                        print_pass(f"dnf can read repository ({len(packages)} packages)")
                        return True
                    else:
                        print_info("Repository is empty or dnf returned no packages")
                        return True
                else:
                    print_fail(f"dnf failed: {result.stderr}")
                    return False
                    
            except subprocess.TimeoutExpired:
                print_fail("dnf command timed out")
                return False
            except Exception as e:
                print_fail(f"Exception: {e}")
                return False
            finally:
                if os.path.exists(repo_config):
                    os.unlink(repo_config)
            
            break
    
    return True


def main():
    print(f"\n{Colors.BOLD}{'='*60}")
    print("SQLite Integration Test Suite for yums3")
    print(f"{'='*60}{Colors.RESET}\n")
    
    tests = [
        ("Module Import", test_sqlite_metadata_module),
        ("SQLite Creation", test_create_sample_metadata),
        ("Repomd Integration", test_repomd_integration),
        ("DNF Compatibility", test_dnf_compatibility),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_fail(f"Test crashed: {e}")
            results.append((name, False))
    
    # Summary
    print(f"\n{Colors.BOLD}{'='*60}")
    print("Test Summary")
    print(f"{'='*60}{Colors.RESET}\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if result else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  {name:.<40} {status}")
    
    print(f"\n{Colors.BOLD}Total: {passed}/{total} tests passed{Colors.RESET}\n")
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
