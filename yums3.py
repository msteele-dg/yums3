#!/usr/bin/env python3
"""
yums3 - Efficient YUM repository manager for S3

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import argparse
import os
import sys
import subprocess
import re
import gzip
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import json

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("ERROR: boto3 is not installed. Install it with: pip install boto3")
    sys.exit(1)


class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    @staticmethod
    def error(msg):
        return f"{Colors.RED}{msg}{Colors.RESET}"
    
    @staticmethod
    def success(msg):
        return f"{Colors.GREEN}{msg}{Colors.RESET}"
    
    @staticmethod
    def warning(msg):
        return f"{Colors.YELLOW}{msg}{Colors.RESET}"
    
    @staticmethod
    def info(msg):
        return f"{Colors.BLUE}{msg}{Colors.RESET}"
    
    @staticmethod
    def bold(msg):
        return f"{Colors.BOLD}{msg}{Colors.RESET}"


class YumRepo:
    """YUM repository manager for S3-backed repositories"""
    
    def __init__(self, s3_bucket_name, local_repo_base=None, skip_validation=False):
        """
        Initialize YUM repository manager
        
        Args:
            s3_bucket_name: Name of the S3 bucket
            local_repo_base: Base directory for local repo cache (default: ~/yum-repo)
            skip_validation: Skip post-operation validation
        """
        self.s3_bucket_name = s3_bucket_name
        self.local_repo_base = local_repo_base or os.path.expanduser("~/yum-repo")
        self.backup_metadata = None  # Store backup metadata location
        self.skip_validation = skip_validation
        
        # Initialize boto3 clients
        try:
            self.s3_client = boto3.client('s3')
            self.sts_client = boto3.client('sts')
            session = boto3.Session()
            self.aws_region = session.region_name
            self.aws_profile = os.environ.get('AWS_PROFILE', 'default')
        except NoCredentialsError:
            print("ERROR: AWS credentials not found")
            sys.exit(1)
    
    def add_packages(self, rpm_files):
        """
        Add one or more RPM packages to the repository
        
        Args:
            rpm_files: List of paths to RPM files to add
        """
        # Validate files exist
        for rpm_file in rpm_files:
            if not os.path.isfile(rpm_file):
                raise FileNotFoundError(f"RPM file not found: {rpm_file}")
        
        # Detect metadata from first RPM
        arch, el_version = self._detect_from_rpm(rpm_files[0])
        
        # Validate all RPMs match
        self._validate_rpm_compatibility(rpm_files, arch, el_version)
        
        # Setup paths
        repo_dir = os.path.join(self.local_repo_base, el_version, arch)
        s3_prefix = f"{el_version}/{arch}"
        
        # Prepare local directory
        self._prepare_repo_dir(repo_dir)
        
        # Check if repo exists in S3
        if not self._s3_repo_exists(s3_prefix):
            self._init_repo(rpm_files, repo_dir, s3_prefix)
        else:
            self._add_to_existing_repo(rpm_files, repo_dir, s3_prefix)
        
        # Quick validation after operation
        if not self.skip_validation:
            print()
            print(Colors.info("Validating repository..."))
            if not self._validate_quick(s3_prefix):
                print(Colors.warning("⚠ Validation found issues (operation completed but repo may have problems)"))
            else:
                print(Colors.success("✓ Validation passed"))
    
    def remove_packages(self, rpm_filenames, el_version=None, arch=None):
        """
        Remove one or more RPM packages from the repository
        
        Args:
            rpm_filenames: List of RPM filenames (not full paths) to remove
            el_version: EL version (e.g., 'el9'). If None, detected from filename
            arch: Architecture (e.g., 'x86_64'). If None, detected from filename
        """
        # Detect metadata from filename if not provided
        if not el_version or not arch:
            arch_detected, el_detected = self._detect_from_filename(rpm_filenames[0])
            arch = arch or arch_detected
            el_version = el_version or el_detected
        
        # Setup paths
        repo_dir = os.path.join(self.local_repo_base, el_version, arch)
        s3_prefix = f"{el_version}/{arch}"
        
        # Check repo exists
        if not self._s3_repo_exists(s3_prefix):
            raise ValueError(f"Repository does not exist: s3://{self.s3_bucket_name}/{s3_prefix}")
        
        # Prepare local directory
        self._prepare_repo_dir(repo_dir)
        
        print(Colors.info("Removing packages from repository..."))
        print("Downloading metadata...")
        self._s3_sync_from_s3(f"{s3_prefix}/repodata", f"{repo_dir}/repodata")
        
        s3_rpms = self._s3_list_objects(s3_prefix, suffix='.rpm')
        
        # Verify RPMs exist
        missing_count = 0
        for rpm_filename in rpm_filenames:
            if rpm_filename not in s3_rpms:
                print(Colors.warning(f"  ⚠ {rpm_filename} not found in repository"))
                missing_count += 1
        
        if missing_count == len(rpm_filenames):
            raise ValueError("None of the specified RPMs exist in the repository")
        
        # Backup metadata before making changes
        print("Creating metadata backup...")
        self._backup_metadata(repo_dir, s3_prefix)
        
        try:
            print("Updating metadata...")
            self._manipulate_metadata(repo_dir, rpm_filenames)
            
            # Delete from S3
            for rpm_filename in rpm_filenames:
                if rpm_filename in s3_rpms:
                    self.s3_client.delete_object(
                        Bucket=self.s3_bucket_name,
                        Key=f"{s3_prefix}/{rpm_filename}"
                    )
            
            print("Uploading metadata...")
            self._s3_sync_to_s3(f"{repo_dir}/repodata", f"{s3_prefix}/repodata")
            
            # Clean up backup on success
            self._cleanup_backup()
            
            print(Colors.success(f"✓ Removed {len(rpm_filenames)} package{'s' if len(rpm_filenames) > 1 else ''} from s3://{self.s3_bucket_name}/{s3_prefix}"))
            
        except Exception as e:
            print(Colors.error(f"✗ Operation failed: {e}"))
            print(Colors.warning("Restoring metadata from backup..."))
            self._restore_metadata(s3_prefix)
            raise
        
        # Quick validation after operation
        if not self.skip_validation:
            print()
            print(Colors.info("Validating repository..."))
            if not self._validate_quick(s3_prefix):
                print(Colors.warning("⚠ Validation found issues (operation completed but repo may have problems)"))
            else:
                print(Colors.success("✓ Validation passed"))
    
    def validate_repository(self, el_version, arch):
        """
        Perform full validation of repository
        
        Args:
            el_version: EL version (e.g., 'el9')
            arch: Architecture (e.g., 'x86_64')
        
        Returns:
            bool: True if validation passed, False otherwise
        """
        s3_prefix = f"{el_version}/{arch}"
        
        # Check repo exists
        if not self._s3_repo_exists(s3_prefix):
            print(Colors.error(f"✗ Repository does not exist: s3://{self.s3_bucket_name}/{s3_prefix}"))
            return False
        
        print(Colors.info(f"Validating repository: s3://{self.s3_bucket_name}/{s3_prefix}"))
        print()
        
        # Setup paths
        repo_dir = os.path.join(self.local_repo_base, el_version, arch)
        self._prepare_repo_dir(repo_dir)
        
        # Download metadata
        print("Downloading metadata...")
        self._s3_sync_from_s3(f"{s3_prefix}/repodata", f"{repo_dir}/repodata")
        
        # Perform full validation
        return self._validate_full(repo_dir, s3_prefix)
    
    def get_aws_info(self):
        """Get AWS configuration information"""
        try:
            identity = self.sts_client.get_caller_identity()
            aws_account = identity['Account']
        except ClientError:
            aws_account = "Unable to determine"
        
        aws_region_env = os.environ.get('AWS_REGION')
        if aws_region_env:
            aws_region_info = f"{aws_region_env} (from AWS_REGION)"
        elif os.environ.get('AWS_DEFAULT_REGION'):
            aws_region_info = f"{os.environ['AWS_DEFAULT_REGION']} (from AWS_DEFAULT_REGION)"
        elif self.aws_region:
            aws_region_info = f"{self.aws_region} (from config)"
        else:
            aws_region_info = "Unable to determine"
        
        aws_profile_info = f"{self.aws_profile} (from AWS_PROFILE)" if self.aws_profile != 'default' else "default"
        
        return {
            'account': aws_account,
            'region': aws_region_info,
            'profile': aws_profile_info
        }
    
    # Private helper methods
    
    def _detect_from_filename(self, rpm_filename):
        """Detect arch and EL version from filename"""
        first_rpm = rpm_filename
        
        arch_match = re.search(r'\.(x86_64|aarch64|noarch)\.rpm$', first_rpm)
        if not arch_match:
            raise ValueError(f"Could not detect architecture from filename: {first_rpm}")
        arch = arch_match.group(1)
        
        el_match = re.search(r'\.el(\d+)\.', first_rpm)
        if not el_match:
            raise ValueError(f"Could not detect EL version from filename: {first_rpm}")
        el_version = f"el{el_match.group(1)}"
        
        return arch, el_version
    
    def _detect_from_rpm(self, rpm_file):
        """Detect arch and EL version from RPM file"""
        first_rpm = rpm_file
        
        result = subprocess.run(
            ['rpm', '-qp', '--queryformat', '%{ARCH}', first_rpm],
            capture_output=True, text=True
        )
        if result.returncode != 0 or not result.stdout:
            raise ValueError(f"Failed to detect architecture from RPM: {first_rpm}")
        arch = result.stdout.strip()
        
        result = subprocess.run(
            ['rpm', '-qp', '--queryformat', '%{RELEASE}', first_rpm],
            capture_output=True, text=True
        )
        if result.returncode != 0 or not result.stdout:
            raise ValueError(f"Failed to detect release from RPM: {first_rpm}")
        release = result.stdout.strip()
        
        el_match = re.search(r'el\d+', release)
        if not el_match:
            raise ValueError(f"Could not determine EL version from release: {release}")
        el_version = el_match.group(0)
        
        return arch, el_version
    
    def _validate_rpm_compatibility(self, rpm_files, expected_arch, expected_el):
        """Verify all RPMs match the same arch/version"""
        for rpm_file in rpm_files:
            rpm_arch, rpm_el = self._detect_from_rpm(rpm_file)
            
            if rpm_arch != expected_arch or rpm_el != expected_el:
                raise ValueError(
                    f"RPM mismatch: Expected {expected_el}/{expected_arch}, "
                    f"found {rpm_el}/{rpm_arch} in {os.path.basename(rpm_file)}"
                )
        
        print(Colors.info(f"Target: {expected_el}/{expected_arch} ({len(rpm_files)} package{'s' if len(rpm_files) > 1 else ''})"))
    
    def _prepare_repo_dir(self, repo_dir):
        """Clean and create fresh local repo directory"""
        if os.path.exists(repo_dir):
            subprocess.run(['rm', '-rf', repo_dir], check=True)
        os.makedirs(repo_dir, exist_ok=True)
    
    def _s3_repo_exists(self, s3_prefix):
        """Check if repository exists in S3"""
        try:
            self.s3_client.head_object(
                Bucket=self.s3_bucket_name,
                Key=f"{s3_prefix}/repodata/repomd.xml"
            )
            return True
        except ClientError:
            return False
    
    def _init_repo(self, rpm_files, repo_dir, s3_prefix):
        """Initialize a new repository"""
        print(Colors.info("Initializing new repository..."))
        
        for rpm_file in rpm_files:
            subprocess.run(['cp', rpm_file, repo_dir], check=True)
        
        # Create repo without SQLite databases (XML only)
        subprocess.run(['createrepo_c', '--no-database', repo_dir], check=True, 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print("Uploading to S3...")
        self._s3_sync_to_s3(repo_dir, s3_prefix)
        
        print(Colors.success(f"✓ Published {len(rpm_files)} package{'s' if len(rpm_files) > 1 else ''} to s3://{self.s3_bucket_name}/{s3_prefix}"))
        for rpm_file in rpm_files:
            print(f"  • {os.path.basename(rpm_file)}")
    
    def _add_to_existing_repo(self, rpm_files, repo_dir, s3_prefix):
        """Add packages to existing repository"""
        print(Colors.info("Updating existing repository..."))
        print("Downloading metadata...")
        self._s3_sync_from_s3(f"{s3_prefix}/repodata", f"{repo_dir}/repodata")
        
        # Backup metadata before making changes
        print("Creating metadata backup...")
        self._backup_metadata(repo_dir, s3_prefix)
        
        try:
            temp_repo = f"{repo_dir}.new"
            os.makedirs(temp_repo, exist_ok=True)
            
            for rpm_file in rpm_files:
                subprocess.run(['cp', rpm_file, temp_repo], check=True)
            
            # Create metadata without SQLite databases
            subprocess.run(['createrepo_c', '--no-database', temp_repo], check=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            print("Merging metadata...")
            self._merge_metadata(repo_dir, temp_repo, rpm_files)
            
            subprocess.run(['rm', '-rf', temp_repo], check=True)
            
            print("Uploading packages...")
            for rpm_file in rpm_files:
                rpm_basename = os.path.basename(rpm_file)
                self.s3_client.upload_file(
                    rpm_file,
                    self.s3_bucket_name,
                    f"{s3_prefix}/{rpm_basename}"
                )
            
            # Delete all old repodata files before uploading new ones
            old_metadata = self._s3_list_objects(f"{s3_prefix}/repodata")
            for old_file in old_metadata:
                self.s3_client.delete_object(
                    Bucket=self.s3_bucket_name,
                    Key=f"{s3_prefix}/repodata/{old_file}"
                )
            
            print("Uploading metadata...")
            self._s3_sync_to_s3(f"{repo_dir}/repodata", f"{s3_prefix}/repodata")
            
            # Clean up backup on success
            self._cleanup_backup()
            
            print(Colors.success(f"✓ Published {len(rpm_files)} package{'s' if len(rpm_files) > 1 else ''} to s3://{self.s3_bucket_name}/{s3_prefix}"))
            for rpm_file in rpm_files:
                print(f"  • {os.path.basename(rpm_file)}")
                
        except Exception as e:
            print(Colors.error(f"✗ Operation failed: {e}"))
            print(Colors.warning("Restoring metadata from backup..."))
            self._restore_metadata(s3_prefix)
            raise
    
    def _merge_metadata(self, repo_dir, temp_repo, rpm_files):
        """Merge new package metadata into existing repository metadata"""
        repodata_dir = os.path.join(repo_dir, 'repodata')
        temp_repodata_dir = os.path.join(temp_repo, 'repodata')
        
        # Namespaces
        NS = {
            'repo': 'http://linux.duke.edu/metadata/repo',
            'rpm': 'http://linux.duke.edu/metadata/rpm',
            'common': 'http://linux.duke.edu/metadata/common',
            'filelists': 'http://linux.duke.edu/metadata/filelists',
            'otherdata': 'http://linux.duke.edu/metadata/other'
        }
        
        # Register namespaces
        for prefix, uri in NS.items():
            ET.register_namespace(prefix, uri)
        
        # Parse both repomd.xml files to find metadata files
        def get_metadata_files(repodata_path):
            repomd_path = os.path.join(repodata_path, 'repomd.xml')
            tree = ET.parse(repomd_path)
            root = tree.getroot()
            files = {}
            
            # Try with namespace first
            data_elements = root.findall('repo:data', NS)
            if not data_elements:
                # Try without namespace (for files we've already stripped)
                data_elements = root.findall('data')
            
            for data in data_elements:
                data_type = data.get('type')
                
                # Try with namespace first
                location = data.find('repo:location', NS)
                if location is None:
                    # Try without namespace
                    location = data.find('location')
                
                if location is not None:
                    files[data_type] = location.get('href').replace('repodata/', '')
            return files
        
        existing_files = get_metadata_files(repodata_dir)
        new_files = get_metadata_files(temp_repodata_dir)
        
        # Merge primary.xml.gz
        existing_primary = os.path.join(repodata_dir, existing_files['primary'])
        new_primary = os.path.join(temp_repodata_dir, new_files['primary'])
        
        with gzip.open(existing_primary, 'rt', encoding='utf-8') as f:
            existing_tree = ET.parse(f)
            existing_root = existing_tree.getroot()
        
        with gzip.open(new_primary, 'rt', encoding='utf-8') as f:
            new_tree = ET.parse(f)
            new_root = new_tree.getroot()
        
        # Add new packages to existing metadata
        packages_added = 0
        for package in new_root.findall('common:package', NS):
            existing_root.append(package)
            packages_added += 1
        
        # Update package count
        current_count = int(existing_root.get('packages', '0'))
        existing_root.set('packages', str(current_count + packages_added))
        
        # Write merged primary.xml.gz
        with gzip.open(existing_primary, 'wt', encoding='utf-8') as f:
            existing_tree.write(f, encoding='unicode', xml_declaration=True)
        
        # Merge filelists.xml.gz
        if 'filelists' in existing_files and 'filelists' in new_files:
            existing_filelists = os.path.join(repodata_dir, existing_files['filelists'])
            new_filelists = os.path.join(temp_repodata_dir, new_files['filelists'])
            
            with gzip.open(existing_filelists, 'rt', encoding='utf-8') as f:
                existing_tree = ET.parse(f)
                existing_root = existing_tree.getroot()
            
            with gzip.open(new_filelists, 'rt', encoding='utf-8') as f:
                new_tree = ET.parse(f)
                new_root = new_tree.getroot()
            
            for package in new_root.findall('filelists:package', NS):
                existing_root.append(package)
            
            current_count = int(existing_root.get('packages', '0'))
            existing_root.set('packages', str(current_count + packages_added))
            
            with gzip.open(existing_filelists, 'wt', encoding='utf-8') as f:
                existing_tree.write(f, encoding='unicode', xml_declaration=True)
        
        # Merge other.xml.gz
        if 'other' in existing_files and 'other' in new_files:
            existing_other = os.path.join(repodata_dir, existing_files['other'])
            new_other = os.path.join(temp_repodata_dir, new_files['other'])
            
            with gzip.open(existing_other, 'rt', encoding='utf-8') as f:
                existing_tree = ET.parse(f)
                existing_root = existing_tree.getroot()
            
            with gzip.open(new_other, 'rt', encoding='utf-8') as f:
                new_tree = ET.parse(f)
                new_root = new_tree.getroot()
            
            for package in new_root.findall('otherdata:package', NS):
                existing_root.append(package)
            
            current_count = int(existing_root.get('packages', '0'))
            existing_root.set('packages', str(current_count + packages_added))
            
            with gzip.open(existing_other, 'wt', encoding='utf-8') as f:
                existing_tree.write(f, encoding='unicode', xml_declaration=True)
        
        # Update repomd.xml with new checksums and rename files
        repomd_path = os.path.join(repodata_dir, 'repomd.xml')
        repomd_tree = ET.parse(repomd_path)
        repomd_root = repomd_tree.getroot()
        
        # Try with namespace first, fallback to no namespace
        data_elements = repomd_root.findall('repo:data', NS)
        if not data_elements:
            data_elements = repomd_root.findall('data')
        
        for data in data_elements:
            data_type = data.get('type')
            if data_type in existing_files:
                old_filepath = os.path.join(repodata_dir, existing_files[data_type])
                
                # Calculate new checksum
                new_checksum = self.calculate_checksum(old_filepath)
                
                # Determine file extension
                if old_filepath.endswith('.xml.gz'):
                    ext = '-' + data_type + '.xml.gz'
                elif old_filepath.endswith('.sqlite.bz2'):
                    ext = '-' + data_type + '.sqlite.bz2'
                else:
                    ext = os.path.splitext(old_filepath)[1]
                
                # Rename file to match new checksum
                new_filename = new_checksum + ext
                new_filepath = os.path.join(repodata_dir, new_filename)
                os.rename(old_filepath, new_filepath)
                
                # Update checksum element
                checksum_elem = data.find('repo:checksum', NS)
                if checksum_elem is None:
                    checksum_elem = data.find('checksum')
                if checksum_elem is not None:
                    checksum_elem.text = new_checksum
                
                # Update location
                location_elem = data.find('repo:location', NS)
                if location_elem is None:
                    location_elem = data.find('location')
                if location_elem is not None:
                    location_elem.set('href', f'repodata/{new_filename}')
                
                # Update open-checksum (for .gz files)
                open_checksum_elem = data.find('repo:open-checksum', NS)
                if open_checksum_elem is None:
                    open_checksum_elem = data.find('open-checksum')
                if open_checksum_elem is not None and new_filepath.endswith('.gz'):
                    with gzip.open(new_filepath, 'rb') as f:
                        sha256 = hashlib.sha256()
                        for chunk in iter(lambda: f.read(4096), b''):
                            sha256.update(chunk)
                        open_checksum_elem.text = sha256.hexdigest()
                
                # Update size
                size_elem = data.find('repo:size', NS)
                if size_elem is None:
                    size_elem = data.find('size')
                if size_elem is not None:
                    size_elem.text = str(os.path.getsize(new_filepath))
                
                # Update open-size (for .gz files)
                open_size_elem = data.find('repo:open-size', NS)
                if open_size_elem is None:
                    open_size_elem = data.find('open-size')
                if open_size_elem is not None and new_filepath.endswith('.gz'):
                    with gzip.open(new_filepath, 'rb') as f:
                        open_size_elem.text = str(len(f.read()))
                
                # Update timestamp
                timestamp_elem = data.find('repo:timestamp', NS)
                if timestamp_elem is None:
                    timestamp_elem = data.find('timestamp')
                if timestamp_elem is not None:
                    timestamp_elem.text = str(int(datetime.now().timestamp()))
        
        # Update revision
        revision_elem = repomd_root.find('repo:revision', NS)
        if revision_elem is not None:
            revision_elem.text = str(int(datetime.now().timestamp()))
        
        # Write repomd.xml without namespace prefixes (DNF compatibility)
        import io
        output = io.BytesIO()
        repomd_tree.write(output, encoding='utf-8', xml_declaration=True)
        xml_content = output.getvalue().decode('utf-8')
        
        # Remove namespace prefixes from repomd.xml only
        xml_content = re.sub(r'<repo:', '<', xml_content)
        xml_content = re.sub(r'</repo:', '</', xml_content)
        xml_content = re.sub(r' xmlns:repo="[^"]*"', '', xml_content)
        xml_content = re.sub(r' xmlns:rpm="[^"]*"', '', xml_content)
        
        with open(repomd_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        
        # Remove SQLite database entries and files
        self._remove_sqlite_databases(repo_dir)
    
    def _remove_sqlite_databases(self, repo_dir):
        """Remove SQLite database entries from repomd.xml and delete .sqlite files"""
        repodata_dir = os.path.join(repo_dir, 'repodata')
        repomd_path = os.path.join(repodata_dir, 'repomd.xml')
        
        # Parse repomd.xml
        tree = ET.parse(repomd_path)
        root = tree.getroot()
        
        # Find and remove all *_db entries
        data_elements = root.findall('data')
        for data in data_elements:
            data_type = data.get('type')
            if data_type and data_type.endswith('_db'):
                root.remove(data)
                
                # Get filename and delete the file
                location = data.find('location')
                if location is not None:
                    filename = location.get('href').replace('repodata/', '')
                    filepath = os.path.join(repodata_dir, filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)
        
        # Write updated repomd.xml
        tree.write(repomd_path, encoding='utf-8', xml_declaration=True)
        
        # Strip namespaces from repomd.xml (DNF compatibility)
        with open(repomd_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        
        xml_content = re.sub(r'<repo:', '<', xml_content)
        xml_content = re.sub(r'</repo:', '</', xml_content)
        xml_content = re.sub(r' xmlns:repo="[^"]*"', '', xml_content)
        xml_content = re.sub(r' xmlns:rpm="[^"]*"', '', xml_content)
        
        with open(repomd_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
    
    def _manipulate_metadata(self, repo_dir, packages_to_remove):
        """Directly manipulate YUM metadata to remove packages"""
        repodata_dir = os.path.join(repo_dir, 'repodata')
        
        # Namespaces
        NS = {
            'repo': 'http://linux.duke.edu/metadata/repo',
            'rpm': 'http://linux.duke.edu/metadata/rpm',
            'common': 'http://linux.duke.edu/metadata/common',
            'filelists': 'http://linux.duke.edu/metadata/filelists',
            'otherdata': 'http://linux.duke.edu/metadata/other'
        }
        
        # Register namespaces
        for prefix, uri in NS.items():
            ET.register_namespace(prefix, uri)
        
        # Parse repomd.xml to find metadata files
        repomd_path = os.path.join(repodata_dir, 'repomd.xml')
        repomd_tree = ET.parse(repomd_path)
        repomd_root = repomd_tree.getroot()
        
        metadata_files = {}
        for data in repomd_root.findall('repo:data', NS):
            data_type = data.get('type')
            location = data.find('repo:location', NS)
            if location is not None:
                metadata_files[data_type] = location.get('href').replace('repodata/', '')
        
        # Process primary.xml.gz
        primary_file = metadata_files.get('primary')
        if not primary_file:
            print("ERROR: Could not find primary metadata")
            sys.exit(1)
        
        primary_path = os.path.join(repodata_dir, primary_file)
        with gzip.open(primary_path, 'rt', encoding='utf-8') as f:
            primary_tree = ET.parse(f)
            primary_root = primary_tree.getroot()
        
        # Remove packages from primary.xml
        packages_removed = 0
        for package in list(primary_root.findall('common:package', NS)):
            location = package.find('common:location', NS)
            if location is not None:
                href = location.get('href')
                filename = os.path.basename(href)
                if filename in packages_to_remove:
                    primary_root.remove(package)
                    packages_removed += 1
                    print(f"  Removed {filename} from primary metadata")
        
        # Update package count
        current_count = int(primary_root.get('packages', '0'))
        primary_root.set('packages', str(current_count - packages_removed))
        
        # Write updated primary.xml.gz
        new_primary_path = primary_path + '.new'
        with gzip.open(new_primary_path, 'wt', encoding='utf-8') as f:
            primary_tree.write(f, encoding='unicode', xml_declaration=True)
        os.replace(new_primary_path, primary_path)
        
        # Process filelists.xml.gz
        filelists_file = metadata_files.get('filelists')
        if filelists_file:
            filelists_path = os.path.join(repodata_dir, filelists_file)
            with gzip.open(filelists_path, 'rt', encoding='utf-8') as f:
                filelists_tree = ET.parse(f)
                filelists_root = filelists_tree.getroot()
            
            for package in list(filelists_root.findall('filelists:package', NS)):
                name = package.get('name')
                for rpm in packages_to_remove:
                    if rpm.startswith(name + '-'):
                        filelists_root.remove(package)
                        break
            
            current_count = int(filelists_root.get('packages', '0'))
            filelists_root.set('packages', str(current_count - packages_removed))
            
            new_filelists_path = filelists_path + '.new'
            with gzip.open(new_filelists_path, 'wt', encoding='utf-8') as f:
                filelists_tree.write(f, encoding='unicode', xml_declaration=True)
            os.replace(new_filelists_path, filelists_path)
        
        # Process other.xml.gz
        other_file = metadata_files.get('other')
        if other_file:
            other_path = os.path.join(repodata_dir, other_file)
            with gzip.open(other_path, 'rt', encoding='utf-8') as f:
                other_tree = ET.parse(f)
                other_root = other_tree.getroot()
            
            for package in list(other_root.findall('otherdata:package', NS)):
                name = package.get('name')
                for rpm in packages_to_remove:
                    if rpm.startswith(name + '-'):
                        other_root.remove(package)
                        break
            
            current_count = int(other_root.get('packages', '0'))
            other_root.set('packages', str(current_count - packages_removed))
            
            new_other_path = other_path + '.new'
            with gzip.open(new_other_path, 'wt', encoding='utf-8') as f:
                other_tree.write(f, encoding='unicode', xml_declaration=True)
            os.replace(new_other_path, other_path)
        
        # Update repomd.xml with new checksums and timestamps
        for data in repomd_root.findall('repo:data', NS):
            data_type = data.get('type')
            if data_type in metadata_files:
                filepath = os.path.join(repodata_dir, metadata_files[data_type])
                
                # Update checksum
                checksum_elem = data.find('repo:checksum', NS)
                if checksum_elem is not None:
                    checksum_elem.text = self.calculate_checksum(filepath)
                
                # Update size
                size_elem = data.find('repo:size', NS)
                if size_elem is not None:
                    size_elem.text = str(os.path.getsize(filepath))
                
                # Update timestamp
                timestamp_elem = data.find('repo:timestamp', NS)
                if timestamp_elem is not None:
                    timestamp_elem.text = str(int(datetime.now().timestamp()))
        
        # Update repomd.xml revision
        revision_elem = repomd_root.find('repo:revision', NS)
        if revision_elem is not None:
            revision_elem.text = str(int(datetime.now().timestamp()))
        
        # Write updated repomd.xml without namespace prefixes (DNF compatibility)
        import io
        output = io.BytesIO()
        repomd_tree.write(output, encoding='utf-8', xml_declaration=True)
        xml_content = output.getvalue().decode('utf-8')
        
        # Remove namespace prefixes from repomd.xml only
        xml_content = re.sub(r'<repo:', '<', xml_content)
        xml_content = re.sub(r'</repo:', '</', xml_content)
        xml_content = re.sub(r' xmlns:repo="[^"]*"', '', xml_content)
        xml_content = re.sub(r' xmlns:rpm="[^"]*"', '', xml_content)
        
        with open(repomd_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        

    
    def _validate_quick(self, s3_prefix):
        """
        Quick validation: verify checksums in repomd.xml match actual files
        
        Returns:
            bool: True if validation passed
        """
        try:
            # Download repomd.xml
            repomd_key = f"{s3_prefix}/repodata/repomd.xml"
            repomd_obj = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=repomd_key)
            repomd_content = repomd_obj['Body'].read()
            
            # Parse repomd.xml
            root = ET.fromstring(repomd_content)
            
            # Check each metadata file
            issues = []
            data_elements = root.findall('data')
            if not data_elements:
                # Try with namespace
                NS = {'repo': 'http://linux.duke.edu/metadata/repo'}
                data_elements = root.findall('repo:data', NS)
            
            for data in data_elements:
                data_type = data.get('type')
                
                # Get checksum from repomd.xml
                checksum_elem = data.find('checksum')
                if checksum_elem is None:
                    NS = {'repo': 'http://linux.duke.edu/metadata/repo'}
                    checksum_elem = data.find('repo:checksum', NS)
                
                if checksum_elem is None:
                    continue
                
                expected_checksum = checksum_elem.text
                
                # Get location
                location_elem = data.find('location')
                if location_elem is None:
                    NS = {'repo': 'http://linux.duke.edu/metadata/repo'}
                    location_elem = data.find('repo:location', NS)
                
                if location_elem is None:
                    continue
                
                file_path = location_elem.get('href').replace('repodata/', '')
                file_key = f"{s3_prefix}/repodata/{file_path}"
                
                # Download and calculate checksum
                try:
                    file_obj = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=file_key)
                    file_content = file_obj['Body'].read()
                    
                    sha256 = hashlib.sha256()
                    sha256.update(file_content)
                    actual_checksum = sha256.hexdigest()
                    
                    if actual_checksum != expected_checksum:
                        issues.append(f"Checksum mismatch for {data_type}: expected {expected_checksum[:8]}..., got {actual_checksum[:8]}...")
                
                except ClientError as e:
                    issues.append(f"Missing file: {file_key}")
            
            if issues:
                for issue in issues:
                    print(Colors.warning(f"  ⚠ {issue}"))
                return False
            
            return True
            
        except Exception as e:
            print(Colors.error(f"  ✗ Validation error: {e}"))
            return False
    
    def _validate_full(self, repo_dir, s3_prefix):
        """
        Full validation: checksums, consistency, and client compatibility
        
        Returns:
            bool: True if validation passed
        """
        issues = []
        warnings = []
        
        print(Colors.bold("1. Checking metadata integrity..."))
        
        # Parse repomd.xml
        repomd_path = os.path.join(repo_dir, 'repodata', 'repomd.xml')
        if not os.path.exists(repomd_path):
            print(Colors.error("  ✗ repomd.xml not found"))
            return False
        
        try:
            tree = ET.parse(repomd_path)
            root = tree.getroot()
        except ET.ParseError as e:
            print(Colors.error(f"  ✗ Failed to parse repomd.xml: {e}"))
            return False
        
        # Check for namespace prefixes (DNF incompatibility)
        with open(repomd_path, 'r') as f:
            content = f.read()
            if '<repo:' in content or '<rpm:' in content:
                issues.append("repomd.xml contains namespace prefixes (DNF incompatible)")
        
        # Get metadata files
        data_elements = root.findall('data')
        metadata_files = {}
        
        for data in data_elements:
            data_type = data.get('type')
            location = data.find('location')
            checksum_elem = data.find('checksum')
            size_elem = data.find('size')
            
            if location is not None and checksum_elem is not None:
                filename = location.get('href').replace('repodata/', '')
                metadata_files[data_type] = {
                    'filename': filename,
                    'checksum': checksum_elem.text,
                    'size': int(size_elem.text) if size_elem is not None else None
                }
        
        # Verify required metadata exists
        required = ['primary', 'filelists', 'other']
        for req in required:
            if req not in metadata_files:
                issues.append(f"Missing required metadata: {req}")
        
        # Verify checksums and sizes
        for data_type, info in metadata_files.items():
            filepath = os.path.join(repo_dir, 'repodata', info['filename'])
            
            if not os.path.exists(filepath):
                issues.append(f"Missing file: {info['filename']}")
                continue
            
            # Check size
            actual_size = os.path.getsize(filepath)
            if info['size'] and actual_size != info['size']:
                issues.append(f"Size mismatch for {data_type}: expected {info['size']}, got {actual_size}")
            
            # Check checksum
            actual_checksum = self.calculate_checksum(filepath)
            if actual_checksum != info['checksum']:
                issues.append(f"Checksum mismatch for {data_type}")
        
        if issues:
            for issue in issues:
                print(Colors.error(f"  ✗ {issue}"))
        else:
            print(Colors.success("  ✓ Metadata integrity OK"))
        
        print()
        print(Colors.bold("2. Checking repository consistency..."))
        
        # Get list of RPMs from S3
        s3_rpms = set(self._s3_list_objects(s3_prefix, suffix='.rpm'))
        
        # Parse primary.xml to get packages in metadata
        primary_file = metadata_files.get('primary', {}).get('filename')
        if primary_file:
            primary_path = os.path.join(repo_dir, 'repodata', primary_file)
            
            try:
                with gzip.open(primary_path, 'rt', encoding='utf-8') as f:
                    primary_tree = ET.parse(f)
                    primary_root = primary_tree.getroot()
                
                # Try with namespace
                NS = {'common': 'http://linux.duke.edu/metadata/common'}
                packages = primary_root.findall('common:package', NS)
                if not packages:
                    packages = primary_root.findall('package')
                
                metadata_rpms = set()
                for package in packages:
                    location = package.find('common:location', NS)
                    if location is None:
                        location = package.find('location')
                    
                    if location is not None:
                        href = location.get('href')
                        filename = os.path.basename(href)
                        metadata_rpms.add(filename)
                
                # Check for orphaned RPMs (in S3 but not in metadata)
                orphaned = s3_rpms - metadata_rpms
                if orphaned:
                    for rpm in sorted(orphaned):
                        warnings.append(f"Orphaned RPM in S3: {rpm}")
                
                # Check for missing RPMs (in metadata but not in S3)
                missing = metadata_rpms - s3_rpms
                if missing:
                    for rpm in sorted(missing):
                        issues.append(f"Missing RPM from S3: {rpm}")
                
                # Check package count
                declared_count = int(primary_root.get('packages', '0'))
                actual_count = len(packages)
                if declared_count != actual_count:
                    issues.append(f"Package count mismatch: declared {declared_count}, found {actual_count}")
                
            except Exception as e:
                issues.append(f"Failed to parse primary.xml: {e}")
        
        if issues:
            for issue in issues:
                print(Colors.error(f"  ✗ {issue}"))
        elif warnings:
            for warning in warnings:
                print(Colors.warning(f"  ⚠ {warning}"))
            print(Colors.success("  ✓ No critical issues"))
        else:
            print(Colors.success("  ✓ Repository consistency OK"))
        
        print()
        print(Colors.bold("Summary:"))
        if issues:
            print(Colors.error(f"  ✗ {len(issues)} error(s) found"))
            return False
        elif warnings:
            print(Colors.warning(f"  ⚠ {len(warnings)} warning(s) found"))
            print(Colors.success("  ✓ No critical errors"))
            return True
        else:
            print(Colors.success("  ✓ All checks passed"))
            return True
    
    def _backup_metadata(self, repo_dir, s3_prefix):
        """Create a backup of metadata in S3 before making changes"""
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_prefix = f"{s3_prefix}/repodata.backup-{timestamp}"
        
        # Copy all repodata files to backup location in S3
        repodata_files = self._s3_list_objects(f"{s3_prefix}/repodata")
        
        for filename in repodata_files:
            source_key = f"{s3_prefix}/repodata/{filename}"
            dest_key = f"{backup_prefix}/{filename}"
            
            self.s3_client.copy_object(
                Bucket=self.s3_bucket_name,
                CopySource={'Bucket': self.s3_bucket_name, 'Key': source_key},
                Key=dest_key
            )
        
        # Store backup location for potential restoration
        self.backup_metadata = backup_prefix
        print(f"  Backup created: s3://{self.s3_bucket_name}/{backup_prefix}")
    
    def _restore_metadata(self, s3_prefix):
        """Restore metadata from backup after a failed operation"""
        if not self.backup_metadata:
            print(Colors.error("  No backup available to restore"))
            return
        
        try:
            # Delete current (corrupted) metadata
            current_files = self._s3_list_objects(f"{s3_prefix}/repodata")
            for filename in current_files:
                self.s3_client.delete_object(
                    Bucket=self.s3_bucket_name,
                    Key=f"{s3_prefix}/repodata/{filename}"
                )
            
            # Restore from backup
            backup_files = self._s3_list_objects(self.backup_metadata)
            for filename in backup_files:
                source_key = f"{self.backup_metadata}/{filename}"
                dest_key = f"{s3_prefix}/repodata/{filename}"
                
                self.s3_client.copy_object(
                    Bucket=self.s3_bucket_name,
                    CopySource={'Bucket': self.s3_bucket_name, 'Key': source_key},
                    Key=dest_key
                )
            
            print(Colors.success("  ✓ Metadata restored from backup"))
            
            # Keep backup for manual inspection
            print(Colors.info(f"  Backup retained at: s3://{self.s3_bucket_name}/{self.backup_metadata}"))
            
        except Exception as e:
            print(Colors.error(f"  ✗ Failed to restore backup: {e}"))
            print(Colors.warning(f"  Manual restoration required from: s3://{self.s3_bucket_name}/{self.backup_metadata}"))
    
    def _cleanup_backup(self):
        """Remove backup after successful operation"""
        if not self.backup_metadata:
            return
        
        try:
            # Delete backup files
            backup_files = self._s3_list_objects(self.backup_metadata)
            for filename in backup_files:
                self.s3_client.delete_object(
                    Bucket=self.s3_bucket_name,
                    Key=f"{self.backup_metadata}/{filename}"
                )
            
            self.backup_metadata = None
            
        except Exception as e:
            # Non-fatal - backup cleanup failure shouldn't stop the operation
            print(Colors.warning(f"  ⚠ Failed to clean up backup: {e}"))
            print(Colors.info(f"  Backup retained at: s3://{self.s3_bucket_name}/{self.backup_metadata}"))
    
    def _s3_sync_from_s3(self, s3_prefix, local_dir):
        """Sync files from S3 to local directory"""
        os.makedirs(local_dir, exist_ok=True)
        
        paginator = self.s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.s3_bucket_name, Prefix=s3_prefix):
            if 'Contents' not in page:
                continue
            
            for obj in page['Contents']:
                key = obj['Key']
                # Calculate relative path
                rel_path = key[len(s3_prefix):].lstrip('/')
                if not rel_path:
                    continue
                
                local_file = os.path.join(local_dir, rel_path)
                os.makedirs(os.path.dirname(local_file), exist_ok=True)
                
                self.s3_client.download_file(self.s3_bucket_name, key, local_file)
    
    def _s3_sync_to_s3(self, local_dir, s3_prefix):
        """Sync files from local directory to S3"""
        for root, dirs, files in os.walk(local_dir):
            for filename in files:
                local_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_path, local_dir)
                s3_key = f"{s3_prefix}/{relative_path}".replace('\\', '/')
                
                self.s3_client.upload_file(local_path, self.s3_bucket_name, s3_key)
    
    def _s3_list_objects(self, prefix, suffix=None):
        """List objects in S3 with optional suffix filter"""
        objects = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=self.s3_bucket_name, Prefix=prefix):
            if 'Contents' not in page:
                continue
            
            for obj in page['Contents']:
                key = obj['Key']
                basename = os.path.basename(key)
                if suffix is None or basename.endswith(suffix):
                    objects.append(basename)
        
        return objects
    
    @staticmethod
    def calculate_checksum(filepath):
        """Calculate SHA256 checksum of a file"""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()


def load_config():
    """
    Load configuration from file
    
    Searches for config in order:
    1. ./yums3.conf (current directory)
    2. ~/.yums3.conf (user home)
    3. /etc/yums3.conf (system-wide)
    
    Returns:
        dict: Configuration dictionary
    """
    config_locations = [
        'yums3.conf',
        os.path.expanduser('~/.yums3.conf'),
        '/etc/yums3.conf'
    ]
    
    default_config = {
        's3_bucket': None,
        'local_repo_base': None
    }
    
    for config_path in config_locations:
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
                    print(Colors.info(f"Loaded config from: {config_path}"))
                    break
            except (json.JSONDecodeError, IOError) as e:
                print(Colors.warning(f"Failed to load config from {config_path}: {e}"))
                continue
    
    return default_config


def main():
    parser = argparse.ArgumentParser(
        description='Manage YUM repository in S3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Add RPMs:       %(prog)s package.rpm
  Remove RPMs:    %(prog)s --remove package-1.0-1.el9.x86_64.rpm
  Batch add:      %(prog)s -y pkg1.rpm pkg2.rpm pkg3.rpm
  Validate repo:  %(prog)s --validate el9/x86_64
  Skip validation: %(prog)s --no-validate package.rpm

Configuration:
  Create ~/.yums3.conf or /etc/yums3.conf with:
  {
    "s3_bucket": "your-bucket-name",
    "local_repo_base": "/path/to/cache"
  }
        """
    )
    
    parser.add_argument(
        'rpm_files',
        nargs='+',
        help='RPM file(s) to add or remove'
    )
    parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompt (for CI/CD)'
    )
    parser.add_argument(
        '-b', '--bucket',
        help='S3 bucket name (overrides config file)'
    )
    parser.add_argument(
        '-d', '--repo-dir',
        help='Custom local repository base directory (overrides config file)'
    )
    parser.add_argument(
        '--remove',
        action='store_true',
        help='Remove specified RPMs from repository instead of adding'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate repository (requires el_version/arch as argument)'
    )
    parser.add_argument(
        '--no-validate',
        action='store_true',
        help='Skip post-operation validation'
    )
    
    args = parser.parse_args()
    
    # Load configuration with precedence: config file < CLI args
    config = load_config()
    
    try:
        # Apply CLI argument overrides
        s3_bucket = args.bucket if args.bucket else config['s3_bucket']
        local_repo_base = args.repo_dir if args.repo_dir else config['local_repo_base']
        
        # Initialize repository manager
        repo = YumRepo(
            s3_bucket_name=s3_bucket,
            local_repo_base=local_repo_base,
            skip_validation=args.no_validate
        )
        
        # Handle validation command
        if args.validate:
            if len(args.rpm_files) != 1:
                print(Colors.error("✗ Error: --validate requires exactly one argument: el_version/arch"))
                print("Example: ./rpm-repo.py --validate el9/x86_64")
                return 1
            
            # Parse el_version/arch
            parts = args.rpm_files[0].split('/')
            if len(parts) != 2:
                print(Colors.error("✗ Error: Invalid format. Use: el_version/arch (e.g., el9/x86_64)"))
                return 1
            
            el_version, arch = parts
            success = repo.validate_repository(el_version, arch)
            return 0 if success else 1
        
        # Get AWS info for confirmation
        aws_info = repo.get_aws_info()
        
        # Determine operation details
        if args.remove:
            rpm_filenames = [os.path.basename(f) for f in args.rpm_files]
            # Detect from first filename
            arch, el_version = repo._detect_from_filename(rpm_filenames[0])
            action = "REMOVE"
            target = f"s3://{repo.s3_bucket_name}/{el_version}/{arch}"
        else:
            rpm_filenames = args.rpm_files
            # Detect from first RPM
            arch, el_version = repo._detect_from_rpm(args.rpm_files[0])
            action = "ADD"
            target = f"s3://{repo.s3_bucket_name}/{el_version}/{arch}"
        
        # Show confirmation
        print()
        print(Colors.bold("Configuration:"))
        print(f"  AWS Account:  {aws_info['account']}")
        print(f"  AWS Region:   {aws_info['region']}")
        print(f"  Target:       {target}")
        print(f"  Action:       {Colors.bold(action)}")
        print(f"  Packages:     {len(args.rpm_files)}")
        for rpm_file in args.rpm_files:
            print(f"    • {os.path.basename(rpm_file)}")
        print()
        
        # Confirm operation
        if not args.yes:
            response = input(Colors.bold("Continue? (yes/no): "))
            if response.lower() != "yes":
                print(Colors.warning("Cancelled"))
                return 0
        
        # Execute operation
        if args.remove:
            repo.remove_packages(rpm_filenames)
        else:
            repo.add_packages(args.rpm_files)
        
        return 0
        
    except (ValueError, FileNotFoundError) as e:
        print(Colors.error(f"✗ Error: {e}"))
        return 1
    except KeyboardInterrupt:
        print(Colors.warning("\n✗ Cancelled"))
        return 130
    except Exception as e:
        print(Colors.error(f"✗ Unexpected error: {e}"))
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
