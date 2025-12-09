"""
YUM repository manager

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import subprocess
import re
import gzip
import hashlib
from datetime import datetime
import bz2

from core.backend import create_storage_backend
from core.config import RepoConfig
from core.sqlite_metadata import SQLiteMetadataManager
from core import Colors

try:
    from lxml import etree as ET
except ImportError:
    print("ERROR: lxml is not installed. Install it with: pip install lxml")
    import sys
    sys.exit(1)


class YumRepo:
    REPO_TYPE = 'rpm'
    
    def __init__(self, config: RepoConfig):
        """
        Initialize YUM repository manager
        
        Args:
            config: RepoConfig instance with repository configuration
        """
        self.config = config
        self.storage = create_storage_backend(config, repo_type=self.REPO_TYPE)
        self.cache_dir = os.path.expanduser(config.get('repo.cache_dir', '~/yum-repo'))
        self.backup_metadata = None
        self.skip_validation = not config.get('validation.enabled', True)
    
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
        repo_dir = os.path.join(self.cache_dir, el_version, arch)
        repo_path = f"{el_version}/{arch}"
        
        # Prepare local directory
        self._prepare_repo_dir(repo_dir)
        
        # Check if repo exists in storage
        if not self._repo_exists(repo_path):
            self._init_repo(rpm_files, repo_dir, repo_path)
        else:
            # Check for duplicates
            print("Checking for duplicate packages...")
            existing_checksums = self._get_existing_package_checksums(repo_path)
            
            # Filter out duplicates
            new_packages = []
            skipped_packages = []
            updated_packages = []
            
            for rpm_file in rpm_files:
                rpm_basename = os.path.basename(rpm_file)
                rpm_checksum = self._calculate_rpm_checksum(rpm_file)
                
                if rpm_basename in existing_checksums:
                    if existing_checksums[rpm_basename] == rpm_checksum:
                        # Exact duplicate - skip
                        skipped_packages.append(rpm_basename)
                        print(f"  ⊘ {rpm_basename} (already exists with same checksum)")
                    else:
                        # Same filename, different checksum - update
                        updated_packages.append(rpm_basename)
                        new_packages.append(rpm_file)
                        print(f"  ↻ {rpm_basename} (updating - checksum changed)")
                else:
                    # New package
                    new_packages.append(rpm_file)
                    print(f"  + {rpm_basename} (new package)")
            
            # If no new packages, skip metadata regeneration
            if not new_packages:
                print(Colors.success("✓ All packages already exist - nothing to do"))
                return
            
            # Show summary
            if skipped_packages:
                print(Colors.info(f"Skipped {len(skipped_packages)} duplicate package(s)"))
            if updated_packages:
                print(Colors.info(f"Updating {len(updated_packages)} package(s)"))
            
            # Only add new/updated packages
            self._add_to_existing_repo(new_packages, repo_dir, repo_path)
        
        # Quick validation after operation
        if not self.skip_validation:
            print()
            print(Colors.info("Validating repository..."))
            if not self._validate_quick(repo_path):
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
        repo_dir = os.path.join(self.cache_dir, el_version, arch)
        repo_path = f"{el_version}/{arch}"
        
        # Check repo exists
        if not self._repo_exists(repo_path):
            raise ValueError(f"Repository does not exist: {self.storage.get_url()}/{repo_path}")
        
        # Prepare local directory
        self._prepare_repo_dir(repo_dir)
        
        print(Colors.info("Removing packages from repository..."))
        print("Downloading metadata...")
        self.storage.sync_from_storage(f"{repo_path}/repodata", f"{repo_dir}/repodata")
        
        rpms = self.storage.list_files(repo_path, suffix='.rpm')
        
        # Verify RPMs exist
        missing_count = 0
        for rpm_filename in rpm_filenames:
            if rpm_filename not in rpms:
                print(Colors.warning(f"  ⚠ {rpm_filename} not found in repository"))
                missing_count += 1
        
        if missing_count == len(rpm_filenames):
            raise ValueError("None of the specified RPMs exist in the repository")
        
        # Backup metadata before making changes
        print("Creating metadata backup...")
        self._backup_metadata(repo_dir, repo_path)
        
        try:
            print("Updating metadata...")
            self._manipulate_metadata(repo_dir, rpm_filenames)
            
            # Delete from storage
            for rpm_filename in rpm_filenames:
                if rpm_filename in rpms:
                    self.storage.delete_file(f"{repo_path}/{rpm_filename}")
            
            print("Uploading metadata...")
            self.storage.sync_to_storage(f"{repo_dir}/repodata", f"{repo_path}/repodata")
            
            # Clean up backup on success
            self._cleanup_backup()
            
            print(Colors.success(f"✓ Removed {len(rpm_filenames)} package{'s' if len(rpm_filenames) > 1 else ''} from {self.storage.get_url()}/{repo_path}"))
            
        except Exception as e:
            print(Colors.error(f"✗ Operation failed: {e}"))
            print(Colors.warning("Restoring metadata from backup..."))
            self._restore_metadata(repo_path)
            raise
        
        # Quick validation after operation
        if not self.skip_validation:
            print()
            print(Colors.info("Validating repository..."))
            if not self._validate_quick(repo_path):
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
        repo_path = f"{el_version}/{arch}"
        
        # Check repo exists
        if not self._repo_exists(repo_path):
            print(Colors.error(f"✗ Repository does not exist: {self.storage.get_url()}/{repo_path}"))
            return False
        
        print(Colors.info(f"Validating repository: {self.storage.get_url()}/{repo_path}"))
        print()
        
        # Setup paths
        repo_dir = os.path.join(self.cache_dir, el_version, arch)
        self._prepare_repo_dir(repo_dir)
        
        # Download metadata
        print("Downloading metadata...")
        self.storage.sync_from_storage(f"{repo_path}/repodata", f"{repo_dir}/repodata")
        
        # Perform full validation
        return self._validate_full(repo_dir, repo_path)
    
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
    
    def _repo_exists(self, prefix):
        """Check if repository exists in storage"""
        return self.storage.exists(f"{prefix}/repodata/repomd.xml")
    
    def _init_repo(self, rpm_files, repo_dir, repo_path):
        """Initialize a new repository"""
        print(Colors.info("Initializing new repository..."))
        
        for rpm_file in rpm_files:
            subprocess.run(['cp', rpm_file, repo_dir], check=True)
        
        # Create repo WITH SQLite databases (default behavior)
        subprocess.run(['createrepo_c', repo_dir], check=True, 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print("Uploading to storage...")
        self.storage.sync_to_storage(repo_dir, repo_path)
        
        print(Colors.success(f"✓ Published {len(rpm_files)} package{'s' if len(rpm_files) > 1 else ''} to {self.storage.get_url()}/{repo_path}"))
        for rpm_file in rpm_files:
            print(f"  • {os.path.basename(rpm_file)}")
    
    def _add_to_existing_repo(self, rpm_files, repo_dir, repo_path):
        """Add packages to existing repository"""
        print(Colors.info("Updating existing repository..."))
        print("Downloading metadata...")
        self.storage.sync_from_storage(f"{repo_path}/repodata", f"{repo_dir}/repodata")
        
        # Backup metadata before making changes
        print("Creating metadata backup...")
        self._backup_metadata(repo_dir, repo_path)
        
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
                self.storage.upload_file(rpm_file, f"{repo_path}/{rpm_basename}")
            
            # Delete all old repodata files before uploading new ones
            old_metadata = self.storage.list_files(f"{repo_path}/repodata")
            for old_file in old_metadata:
                self.storage.delete_file(f"{repo_path}/repodata/{old_file}")
            
            print("Uploading metadata...")
            self.storage.sync_to_storage(f"{repo_dir}/repodata", f"{repo_path}/repodata")
            
            # Clean up backup on success
            self._cleanup_backup()
            
            print(Colors.success(f"✓ Published {len(rpm_files)} package{'s' if len(rpm_files) > 1 else ''} to {self.storage.get_url()}/{repo_path}"))
            for rpm_file in rpm_files:
                print(f"  • {os.path.basename(rpm_file)}")
                
        except Exception as e:
            print(Colors.error(f"✗ Operation failed: {e}"))
            print(Colors.warning("Restoring metadata from backup..."))
            self._restore_metadata(repo_path)
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
        
        # Write merged primary.xml.gz (lxml handles namespaces correctly)
        with gzip.open(existing_primary, 'wb') as f:
            existing_tree.write(f, encoding='utf-8', xml_declaration=True, pretty_print=False)
        
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
            
            # Write merged filelists.xml.gz (lxml handles namespaces correctly)
            with gzip.open(existing_filelists, 'wb') as f:
                existing_tree.write(f, encoding='utf-8', xml_declaration=True, pretty_print=False)
        
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
            
            # Write merged other.xml.gz (lxml handles namespaces correctly)
            with gzip.open(existing_other, 'wb') as f:
                existing_tree.write(f, encoding='utf-8', xml_declaration=True, pretty_print=False)
        
        # Create SQLite databases from XML files
        print("Creating SQLite databases...")
        
        # Clean up old SQLite database files first
        for filename in os.listdir(repodata_dir):
            if filename.endswith('.sqlite') or filename.endswith('.sqlite.bz2'):
                old_db_path = os.path.join(repodata_dir, filename)
                try:
                    os.remove(old_db_path)
                except OSError:
                    pass  # Ignore errors if file doesn't exist
        
        sqlite_mgr = SQLiteMetadataManager(repodata_dir)
        
        metadata_xml_files = {
            'primary': existing_primary,
        }
        if 'filelists' in existing_files:
            metadata_xml_files['filelists'] = os.path.join(repodata_dir, existing_files['filelists'])
        if 'other' in existing_files:
            metadata_xml_files['other'] = os.path.join(repodata_dir, existing_files['other'])
        
        # Create and compress databases
        db_files = sqlite_mgr.create_all_databases(metadata_xml_files)
        compressed_dbs = {}
        for db_type, db_path in db_files.items():
            compressed_dbs[db_type] = sqlite_mgr.compress_sqlite(db_path)
        
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
            # Skip database files - they're being recreated
            if data_type and data_type.endswith('_db'):
                continue
            # Only process XML metadata files
            if data_type not in ['primary', 'filelists', 'other']:
                continue
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
        
        # Remove old SQLite database entries before adding new ones
        for data in list(repomd_root.findall('repo:data', NS)):
            if data.get('type', '').endswith('_db'):
                repomd_root.remove(data)
        
        # Also check without namespace
        for data in list(repomd_root.findall('data')):
            if data.get('type', '').endswith('_db'):
                repomd_root.remove(data)
        
        # Add SQLite database entries to repomd.xml
        for db_type, db_path in compressed_dbs.items():
            self._add_database_to_repomd(repomd_root, repodata_dir, db_type, db_path)
        
        # Update revision
        revision_elem = repomd_root.find('repo:revision', NS)
        if revision_elem is None:
            revision_elem = repomd_root.find('revision')
        if revision_elem is not None:
            revision_elem.text = str(int(datetime.now().timestamp()))
        
        # Write repomd.xml with proper namespaces (lxml handles this correctly)
        with open(repomd_path, 'wb') as f:
            repomd_tree.write(f, encoding='utf-8', xml_declaration=True, pretty_print=False)
    
    def _add_database_to_repomd(self, repomd_root, repodata_dir, db_type, db_path):
        """Add SQLite database entry to repomd.xml"""
        filename = os.path.basename(db_path)
        checksum = self.calculate_checksum(db_path)
        size = os.path.getsize(db_path)
        timestamp = int(datetime.now().timestamp())
        
        # Calculate checksum of uncompressed database
        with bz2.open(db_path, 'rb') as f:
            uncompressed_data = f.read()
            open_checksum = hashlib.sha256(uncompressed_data).hexdigest()
            open_size = len(uncompressed_data)
        
        # Rename file to match checksum
        new_filename = f"{checksum}-{db_type}.sqlite.bz2"
        new_path = os.path.join(repodata_dir, new_filename)
        os.rename(db_path, new_path)
        
        # Create data element
        data_elem = ET.SubElement(repomd_root, 'data', {'type': db_type})
        
        checksum_elem = ET.SubElement(data_elem, 'checksum', {'type': 'sha256'})
        checksum_elem.text = checksum
        
        open_checksum_elem = ET.SubElement(data_elem, 'open-checksum', {'type': 'sha256'})
        open_checksum_elem.text = open_checksum
        
        location_elem = ET.SubElement(data_elem, 'location', {'href': f'repodata/{new_filename}'})
        
        timestamp_elem = ET.SubElement(data_elem, 'timestamp')
        timestamp_elem.text = str(timestamp)
        
        size_elem = ET.SubElement(data_elem, 'size')
        size_elem.text = str(size)
        
        open_size_elem = ET.SubElement(data_elem, 'open-size')
        open_size_elem.text = str(open_size)
        
        database_version_elem = ET.SubElement(data_elem, 'database_version')
        database_version_elem.text = '10'
    
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
        
        # Create SQLite databases from updated XML files
        print("  Creating SQLite databases...")
        sqlite_mgr = SQLiteMetadataManager(repodata_dir)
        
        # Remove old SQLite databases from repomd.xml
        for data in list(repomd_root.findall('repo:data', NS)):
            if data.get('type', '').endswith('_db'):
                repomd_root.remove(data)
        
        # Also check without namespace
        for data in list(repomd_root.findall('data')):
            if data.get('type', '').endswith('_db'):
                repomd_root.remove(data)
        
        # Build metadata file dict
        metadata_xml_files = {}
        if primary_file:
            metadata_xml_files['primary'] = primary_path
        if filelists_file:
            metadata_xml_files['filelists'] = filelists_path
        if other_file:
            metadata_xml_files['other'] = other_path
        
        # Create and compress databases
        db_files = sqlite_mgr.create_all_databases(metadata_xml_files)
        compressed_dbs = {}
        for db_type, db_path in db_files.items():
            compressed_dbs[db_type] = sqlite_mgr.compress_sqlite(db_path)
        
        # Add SQLite database entries to repomd.xml
        for db_type, db_path in compressed_dbs.items():
            self._add_database_to_repomd(repomd_root, repodata_dir, db_type, db_path)
        
        # Update repomd.xml revision
        revision_elem = repomd_root.find('repo:revision', NS)
        if revision_elem is None:
            revision_elem = repomd_root.find('revision')
        if revision_elem is not None:
            revision_elem.text = str(int(datetime.now().timestamp()))
        
        # Write updated repomd.xml with proper namespaces (lxml handles this correctly)
        with open(repomd_path, 'wb') as f:
            repomd_tree.write(f, encoding='utf-8', xml_declaration=True, pretty_print=False)
        
    def _validate_quick(self, repo_path):
        """
        Quick validation: verify checksums in repomd.xml match actual files
        and check that RPMs are listed in metadata
        
        Returns:
            bool: True if validation passed
        """
        try:
            # Download repomd.xml
            repomd_path = f"{repo_path}/repodata/repomd.xml"
            repomd_content = self.storage.download_file_content(repomd_path)
            
            # Parse repomd.xml
            root = ET.fromstring(repomd_content)
            
            # Check each metadata file
            issues = []
            data_elements = root.findall('data')
            if not data_elements:
                # Try with namespace
                NS = {'repo': 'http://linux.duke.edu/metadata/repo'}
                data_elements = root.findall('repo:data', NS)
            
            # Check for duplicate data types
            data_types = {}
            for data in data_elements:
                data_type = data.get('type')
                if data_type:
                    data_types[data_type] = data_types.get(data_type, 0) + 1
            
            for data_type, count in data_types.items():
                if count > 1:
                    issues.append(f"Duplicate metadata type '{data_type}' found {count} times in repomd.xml")
            
            primary_location = None
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
                file_key = f"{repo_path}/repodata/{file_path}"
                
                # Save primary location for later check
                if data_type == 'primary':
                    primary_location = file_key
                
                # Download and calculate checksum
                try:
                    file_content = self.storage.download_file_content(file_key)
                    
                    sha256 = hashlib.sha256()
                    sha256.update(file_content)
                    actual_checksum = sha256.hexdigest()
                    
                    if actual_checksum != expected_checksum:
                        issues.append(f"Checksum mismatch for {data_type}: expected {expected_checksum[:8]}..., got {actual_checksum[:8]}...")
                
                except ClientError as e:
                    issues.append(f"Missing file: {file_key}")
            
            # Additional check: verify RPMs are listed in primary.xml
            if primary_location:
                try:
                    # Download and parse primary.xml
                    primary_content = self.storage.download_file_content(primary_location)
                    
                    # Decompress if gzipped
                    if primary_location.endswith('.gz'):
                        primary_content = gzip.decompress(primary_content)
                    
                    # Parse XML
                    primary_root = ET.fromstring(primary_content)
                    
                    # Get list of packages in metadata
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
                    
                    print(f"  Found {len(metadata_rpms)} packages in primary.xml")
                    if len(metadata_rpms) <= 10:
                        for rpm in sorted(metadata_rpms):
                            print(f"    - {rpm}")
                    
                    # Get list of RPMs in storage
                    rpms = set(self.storage.list_files(repo_path, suffix='.rpm'))
                    
                    # Check for RPMs in storage but not in metadata
                    orphaned = rpms - metadata_rpms
                    if orphaned:
                        for rpm in sorted(orphaned):
                            issues.append(f"RPM in storage but not in metadata: {rpm}")
                    
                    # Check for RPMs in metadata but not in storage
                    missing = metadata_rpms - rpms
                    if missing:
                        for rpm in sorted(missing):
                            issues.append(f"RPM in metadata but not in storage: {rpm}")
                    
                    # CRITICAL: Validate SQLite databases
                    print("  Checking SQLite databases...")
                    primary_db_file = None
                    for data in data_elements:
                        if data.get('type') == 'primary_db':
                            location = data.find('location')
                            if location is None:
                                NS_REPO = {'repo': 'http://linux.duke.edu/metadata/repo'}
                                location = data.find('repo:location', NS_REPO)
                            if location is not None:
                                primary_db_file = location.get('href').replace('repodata/', '')
                                break
                    
                    if primary_db_file:
                        try:
                            import tempfile
                            import sqlite3
                            import bz2
                            
                            # Download primary_db
                            db_path = f"{repo_path}/repodata/{primary_db_file}"
                            db_compressed = self.storage.download_file_content(db_path)
                            
                            # Decompress
                            db_data = bz2.decompress(db_compressed)
                            
                            # Write to temp file and query
                            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                                tmp.write(db_data)
                                tmp_path = tmp.name
                            
                            try:
                                conn = sqlite3.connect(tmp_path)
                                cursor = conn.cursor()
                                
                                # Count packages in database
                                cursor.execute("SELECT COUNT(*) FROM packages")
                                db_count = cursor.fetchone()[0]
                                
                                # Get package names
                                cursor.execute("SELECT name FROM packages")
                                db_packages = set([row[0] for row in cursor.fetchall()])
                                
                                conn.close()
                                
                                print(f"  Found {db_count} packages in primary_db.sqlite")
                                if db_count <= 10:
                                    for pkg in sorted(db_packages):
                                        print(f"    - {pkg}")
                                
                                # Compare XML vs SQLite
                                xml_package_names = set()
                                for package in packages:
                                    name_elem = package.find('common:name', NS)
                                    if name_elem is None:
                                        name_elem = package.find('name')
                                    if name_elem is not None:
                                        xml_package_names.add(name_elem.text)
                                
                                if xml_package_names != db_packages:
                                    issues.append(f"SQLite database mismatch: XML has {len(xml_package_names)} packages, SQLite has {db_count}")
                                    missing_in_db = xml_package_names - db_packages
                                    if missing_in_db:
                                        for pkg in sorted(missing_in_db)[:5]:  # Limit to first 5
                                            issues.append(f"Package in XML but not in SQLite: {pkg}")
                                        if len(missing_in_db) > 5:
                                            issues.append(f"... and {len(missing_in_db) - 5} more packages missing in SQLite")
                                    extra_in_db = db_packages - xml_package_names
                                    if extra_in_db:
                                        for pkg in sorted(extra_in_db)[:5]:  # Limit to first 5
                                            issues.append(f"Package in SQLite but not in XML: {pkg}")
                                        if len(extra_in_db) > 5:
                                            issues.append(f"... and {len(extra_in_db) - 5} more extra packages in SQLite")
                                else:
                                    print(f"  ✓ SQLite database matches XML ({db_count} packages)")
                                
                            finally:
                                os.unlink(tmp_path)
                        
                        except Exception as e:
                            issues.append(f"Failed to validate SQLite database: {e}")
                    else:
                        issues.append("No primary_db found in metadata (DNF will be slow)")
                    
                except Exception as e:
                    issues.append(f"Failed to validate RPM consistency: {e}")
            
            if issues:
                for issue in issues:
                    print(Colors.warning(f"  ⚠ {issue}"))
                return False
            
            return True
            
        except Exception as e:
            print(Colors.error(f"  ✗ Validation error: {e}"))
            return False
    
    def _validate_full(self, repo_dir, repo_path):
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
        
        # Get list of RPMs from storage
        rpms = set(self.storage.list_files(repo_path, suffix='.rpm'))
        
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
                orphaned = rpms - metadata_rpms
                if orphaned:
                    for rpm in sorted(orphaned):
                        warnings.append(f"Orphaned RPM in S3: {rpm}")
                
                # Check for missing RPMs (in metadata but not in S3)
                missing = metadata_rpms - rpms
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
        print(Colors.bold("3. Checking SQLite databases..."))
        
        # Check for SQLite database files
        db_types = ['primary_db', 'filelists_db', 'other_db']
        db_found = []
        db_missing = []
        
        for db_type in db_types:
            if db_type in metadata_files:
                db_found.append(db_type)
                db_file = metadata_files[db_type]['filename']
                db_path = os.path.join(repo_dir, 'repodata', db_file)
                
                # Verify database can be opened
                try:
                    # Decompress and check
                    with bz2.open(db_path, 'rb') as f:
                        db_data = f.read()
                    
                    # Try to open as SQLite
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        tmp.write(db_data)
                        tmp_path = tmp.name
                    
                    try:
                        import sqlite3
                        conn = sqlite3.connect(tmp_path)
                        cursor = conn.cursor()
                        
                        # Check db_info table exists
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_info'")
                        if not cursor.fetchone():
                            issues.append(f"{db_type}: missing db_info table")
                        
                        # Check packages table exists
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='packages'")
                        if not cursor.fetchone():
                            issues.append(f"{db_type}: missing packages table")
                        else:
                            # Count packages in database
                            cursor.execute("SELECT COUNT(*) FROM packages")
                            db_count = cursor.fetchone()[0]
                            
                            # Compare with XML count
                            if primary_file and db_type == 'primary_db':
                                if db_count != actual_count:
                                    issues.append(f"{db_type}: package count mismatch (DB: {db_count}, XML: {actual_count})")
                        
                        conn.close()
                    finally:
                        os.unlink(tmp_path)
                    
                except Exception as e:
                    issues.append(f"{db_type}: failed to validate - {e}")
            else:
                db_missing.append(db_type)
        
        if db_found:
            print(Colors.success(f"  ✓ Found {len(db_found)} SQLite database(s): {', '.join(db_found)}"))
        
        if db_missing:
            warnings.append(f"Missing SQLite databases: {', '.join(db_missing)}")
            print(Colors.warning(f"  ⚠ Missing: {', '.join(db_missing)}"))
        
        print()
        print(Colors.bold("Summary:"))
        if issues:
            print(Colors.error(f"  ✗ {len(issues)} error(s) found"))
            for issue in issues:
                print(Colors.error(f"    • {issue}"))
            return False
        elif warnings:
            print(Colors.warning(f"  ⚠ {len(warnings)} warning(s) found"))
            print(Colors.success("  ✓ No critical errors"))
            return True
        else:
            print(Colors.success("  ✓ All checks passed"))
            return True
    
    def _backup_metadata(self, repo_dir, repo_path):
        """Create a backup of metadata from local directory before making changes"""
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_prefix = f"{repo_path}/repodata.backup-{timestamp}"
        print(timestamp)
        print(backup_prefix)
        
        # Upload current local repodata to backup location in storage
        # This ensures we backup exactly what we downloaded, not what might be in S3 now
        repodata_dir = os.path.join(repo_dir, 'repodata')
        print(repodata_dir)
        if not os.path.exists(repodata_dir):
            print(Colors.warning("  ⚠ No local metadata to backup"))
            return
        
        backed_up_count = 0
        for filename in os.listdir(repodata_dir):
            print(filename)
            local_file = os.path.join(repodata_dir, filename)
            if os.path.isfile(local_file):
                dest_path = f"{backup_prefix}/{filename}"
                self.storage.upload_file(local_file, dest_path)
                backed_up_count += 1
        
        # Store backup location for potential restoration
        self.backup_metadata = backup_prefix
        print(f"  Backup created: {self.storage.get_url()}/{backup_prefix} ({backed_up_count} files)")
    
    def _restore_metadata(self, repo_path):
        """Restore metadata from backup after a failed operation"""
        if not self.backup_metadata:
            print(Colors.error("  No backup available to restore"))
            return
        
        try:
            # Delete current (corrupted) metadata
            current_files = self.storage.list_files(f"{repo_path}/repodata")
            for filename in current_files:
                self.storage.delete_file(f"{repo_path}/repodata/{filename}")
            
            # Restore from backup
            backup_files = self.storage.list_files(self.backup_metadata)
            for filename in backup_files:
                source_path = f"{self.backup_metadata}/{filename}"
                dest_path = f"{repo_path}/repodata/{filename}"
                self.storage.copy_file(source_path, dest_path)
            
            print(Colors.success("  ✓ Metadata restored from backup"))
            
            # Keep backup for manual inspection
            print(Colors.info(f"  Backup retained at: {self.storage.get_url()}/{self.backup_metadata}"))
            
        except Exception as e:
            print(Colors.error(f"  ✗ Failed to restore backup: {e}"))
            print(Colors.warning(f"  Manual restoration required from: {self.storage.get_url()}/{self.backup_metadata}"))
    
    def _cleanup_backup(self):
        """Remove backup after successful operation"""
        if not self.backup_metadata:
            return
        
        try:
            # Delete backup files
            backup_files = self.storage.list_files(self.backup_metadata)
            for filename in backup_files:
                self.storage.delete_file(f"{self.backup_metadata}/{filename}")
            
            self.backup_metadata = None
            
        except Exception as e:
            # Non-fatal - backup cleanup failure shouldn't stop the operation
            print(Colors.warning(f"  ⚠ Failed to clean up backup: {e}"))
            print(Colors.info(f"  Backup retained at: {self.storage.get_url()}/{self.backup_metadata}"))
    
    def _get_existing_package_checksums(self, repo_path):
        """Get checksums of all packages in repository
        
        Args:
            repo_path: Repository path (e.g., "el9/x86_64")
        
        Returns:
            dict: {rpm_filename: checksum}
        """
        import io
        
        try:
            # First, get the actual primary.xml.gz filename from repomd.xml
            repomd_content = self.storage.download_file_content(f"{repo_path}/repodata/repomd.xml")
            repomd_tree = ET.fromstring(repomd_content)
            
            # Find primary data location
            NS = {'repo': 'http://linux.duke.edu/metadata/repo'}
            primary_location = None
            
            # Try with namespace
            for data in repomd_tree.findall('repo:data', NS):
                if data.get('type') == 'primary':
                    location = data.find('repo:location', NS)
                    if location is not None:
                        primary_location = location.get('href')
                        break
            
            # Try without namespace if not found
            if not primary_location:
                for data in repomd_tree.findall('data'):
                    if data.get('type') == 'primary':
                        location = data.find('location')
                        if location is not None:
                            primary_location = location.get('href')
                            break
            
            if not primary_location:
                return {}
            
            # Download primary.xml.gz (remove 'repodata/' prefix if present)
            primary_path = primary_location.replace('repodata/', '')
            primary_content = self.storage.download_file_content(f"{repo_path}/repodata/{primary_path}")
            
            # Parse and extract checksums
            with gzip.open(io.BytesIO(primary_content), 'rt', encoding='utf-8') as f:
                tree = ET.parse(f)
                root = tree.getroot()
            
            checksums = {}
            
            # Try with namespace first
            NS = {'common': 'http://linux.duke.edu/metadata/common'}
            packages = root.findall('.//{http://linux.duke.edu/metadata/common}package')
            
            if not packages:
                # Try without namespace
                packages = root.findall('.//package')
            
            for package in packages:
                # Get location (filename)
                location_elem = package.find('.//{http://linux.duke.edu/metadata/common}location')
                if location_elem is None:
                    location_elem = package.find('.//location')
                
                # Get checksum
                checksum_elem = package.find('.//{http://linux.duke.edu/metadata/common}checksum')
                if checksum_elem is None:
                    checksum_elem = package.find('.//checksum')
                
                if location_elem is not None and checksum_elem is not None:
                    href = location_elem.get('href')
                    if href:
                        filename = os.path.basename(href)
                        checksums[filename] = checksum_elem.text
            
            return checksums
            
        except Exception as e:
            # If we can't get checksums, assume no duplicates
            print(Colors.warning(f"  ⚠ Could not check for duplicates: {e}"))
            return {}
    
    def _calculate_rpm_checksum(self, rpm_file):
        """Calculate SHA256 checksum of RPM file
        
        Args:
            rpm_file: Path to RPM file
        
        Returns:
            str: SHA256 checksum
        """
        return self.calculate_checksum(rpm_file)
    
    @staticmethod
    def calculate_checksum(filepath):
        """Calculate SHA256 checksum of a file"""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

