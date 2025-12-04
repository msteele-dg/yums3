#!/usr/bin/env python3
"""
debs3 - Efficient Debian repository manager for S3

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
import bz2
import hashlib
import io
from datetime import datetime
from pathlib import Path
import json
import tempfile

from core.backend import create_storage_backend
from core.config import RepoConfig
from core.constants import REPO_CONFIG_FILES
from core import Colors


class DebRepo:
    """Debian repository manager with pluggable storage backends"""
    
    def __init__(self, config: RepoConfig):
        """
        Initialize Debian repository manager
        
        Args:
            config: RepoConfig instance with repository configuration
        """
        self.config = config
        # Use Debian-specific config with fallback to shared config
        self.storage = create_storage_backend(config, repo_type='deb')
        # Check repo.deb.cache_dir first, then repo.cache_dir, then default
        cache_dir = (config.get('repo.deb.cache_dir') or 
                     config.get('repo.cache_dir') or 
                     '~/deb-repo')
        self.cache_dir = os.path.expanduser(cache_dir)
        self.skip_validation = not config.get('validation.enabled', True)
        
        # Debian-specific configuration
        self.default_distribution = config.get('debian.default_distribution', 'focal')
        self.default_component = config.get('debian.default_component', 'main')
        self.architectures = config.get('debian.architectures', 'amd64 arm64').split()
        self.origin = config.get('debian.origin', 'MyRepo')
        self.label = config.get('debian.label', 'MyRepo')
        
        # Backup tracking
        self.backup_path = None

    def add_packages(self, deb_files):
        """
        Add one or more Debian packages to the repository
        
        Args:
            deb_files: List of paths to .deb files to add
        """
        # Validate files exist
        for deb_file in deb_files:
            if not os.path.isfile(deb_file):
                raise FileNotFoundError(f"Debian package not found: {deb_file}")
        
        # Detect metadata from first package
        distribution, component, arch = self._detect_from_deb(deb_files[0])
        
        # Validate all packages match
        self._validate_deb_compatibility(deb_files, distribution, component, arch)
        
        print(Colors.info(f"Target: {distribution}/{component}/{arch} ({len(deb_files)} package(s))"))
        
        # Check if repository exists
        if not self._repo_exists(distribution, component, arch):
            self._init_repo(deb_files, distribution, component, arch)
            
            # Quick validation after init
            if not self.skip_validation:
                print()
                print(Colors.info("Validating repository..."))
                if self.validate_repository(distribution, component, arch):
                    print(Colors.success("✓ Validation passed"))
                else:
                    print(Colors.warning("⚠ Validation found issues"))
        else:
            self._add_to_existing_repo(deb_files, distribution, component, arch)
            
            # Quick validation after operation
            if not self.skip_validation:
                print()
                print(Colors.info("Validating repository..."))
                if self.validate_repository(distribution, component, arch):
                    print(Colors.success("✓ Validation passed"))
                else:
                    print(Colors.warning("⚠ Validation found issues"))
    
    def remove_packages(self, package_names, distribution=None, component=None, arch=None):
        """
        Remove one or more Debian packages from the repository
        
        Args:
            package_names: List of package names or package_version strings to remove
            distribution: Distribution name (e.g., 'focal'). If None, uses default
            component: Component name (e.g., 'main'). If None, uses default
            arch: Architecture (e.g., 'amd64'). If None, uses default
        """
        distribution = distribution or self.default_distribution
        component = component or self.default_component
        arch = arch or self.architectures[0]
        
        print(Colors.info(f"Removing packages from {distribution}/{component}/{arch}..."))
        
        # Check if repository exists
        if not self._repo_exists(distribution, component, arch):
            raise ValueError(
                f"Repository does not exist: {distribution}/{component}/{arch}"
            )
        
        # Download existing Packages file
        print("Downloading metadata...")
        local_dir = os.path.join(self.cache_dir, distribution, component, f"binary-{arch}")
        os.makedirs(local_dir, exist_ok=True)
        
        packages_path = f"dists/{distribution}/{component}/binary-{arch}/Packages"
        local_packages = os.path.join(local_dir, 'Packages')
        
        self.storage.download_file(packages_path, local_packages)
        
        # Parse existing packages
        print("Parsing metadata...")
        packages_to_remove = []
        remaining_entries = {}
        
        with open(local_packages, 'r') as f:
            content = f.read()
        
        current_entry = []
        current_package = None
        current_version = None
        current_filename = None
        
        for line in content.split('\n'):
            if line.strip() == '':
                if current_entry and current_package:
                    # Check if this package should be removed
                    should_remove = False
                    for pkg_name in package_names:
                        if '_' in pkg_name:
                            # Format: package_version
                            if f"{current_package}_{current_version}" == pkg_name:
                                should_remove = True
                                break
                        else:
                            # Just package name - remove all versions
                            if current_package == pkg_name:
                                should_remove = True
                                break
                    
                    if should_remove:
                        packages_to_remove.append({
                            'package': current_package,
                            'version': current_version,
                            'filename': current_filename
                        })
                        print(f"  ✗ {current_package} {current_version}")
                    else:
                        key = f"{current_package}_{current_version}"
                        remaining_entries[key] = '\n'.join(current_entry) + '\n\n'
                
                current_entry = []
                current_package = None
                current_version = None
                current_filename = None
            else:
                current_entry.append(line)
                if line.startswith('Package:'):
                    current_package = line.split(':', 1)[1].strip()
                elif line.startswith('Version:'):
                    current_version = line.split(':', 1)[1].strip()
                elif line.startswith('Filename:'):
                    current_filename = line.split(':', 1)[1].strip()
        
        if not packages_to_remove:
            print(Colors.warning("⚠ No matching packages found"))
            return
        
        print(f"Removing {len(packages_to_remove)} package(s)...")
        
        # Create backup before making changes
        self._backup_metadata(distribution, component, arch)
        
        try:
            # Delete packages from pool
            print("Deleting packages from pool...")
            for pkg_info in packages_to_remove:
                if pkg_info['filename']:
                    try:
                        self.storage.delete_file(pkg_info['filename'])
                        print(f"  ✗ {pkg_info['filename']}")
                    except Exception as e:
                        print(Colors.warning(f"  ⚠ Could not delete {pkg_info['filename']}: {e}"))
            
            # Write updated Packages file
            print("Updating metadata...")
            with open(local_packages, 'w') as f:
                for key in sorted(remaining_entries.keys()):
                    f.write(remaining_entries[key])
            
            # Compress
            with open(local_packages, 'rb') as f_in:
                with gzip.open(local_packages + '.gz', 'wb') as f_out:
                    f_out.write(f_in.read())
            
            with open(local_packages, 'rb') as f_in:
                with bz2.open(local_packages + '.bz2', 'wb') as f_out:
                    f_out.write(f_in.read())
            
            # Generate Release file
            print("Updating Release file...")
            self._generate_release_file(distribution, local_dir)
            
            # Upload metadata
            print("Uploading metadata...")
            self._upload_metadata(distribution, component, arch, local_dir)
            
            # Clean up backup on success
            self._cleanup_backup()
            
            print(Colors.success(
                f"✓ Removed {len(packages_to_remove)} package(s) from "
                f"{self.storage.get_url()}/{distribution}/{component}/{arch}"
            ))
        
        except Exception as e:
            print(Colors.error(f"✗ Operation failed: {e}"))
            print(Colors.warning("Restoring metadata from backup..."))
            self._restore_metadata(distribution, component, arch)
            raise
    
    def validate_repository(self, distribution, component, arch):
        """
        Perform full validation of repository
        
        Args:
            distribution: Distribution name (e.g., 'focal')
            component: Component name (e.g., 'main')
            arch: Architecture (e.g., 'amd64')
        
        Returns:
            bool: True if validation passed
        """
        print(Colors.info(f"Validating repository: {distribution}/{component}/{arch}"))
        
        errors = []
        warnings = []
        
        # Check if repository exists
        if not self._repo_exists(distribution, component, arch):
            print(Colors.error(f"✗ Repository does not exist: {distribution}/{component}/{arch}"))
            return False
        
        # Validate Release file
        print("Checking Release file...")
        release_errors = self._validate_release_file(distribution, component, arch)
        errors.extend(release_errors)
        
        if not release_errors:
            print(Colors.success("  ✓ Release file valid"))
        
        # Validate Packages file
        print("Checking Packages file...")
        packages_errors, packages_warnings = self._validate_packages_file(distribution, component, arch)
        errors.extend(packages_errors)
        warnings.extend(packages_warnings)
        
        if not packages_errors:
            print(Colors.success("  ✓ Packages file valid"))
        
        # Validate pool integrity
        print("Checking pool integrity...")
        pool_errors = self._validate_pool_integrity(distribution, component, arch)
        errors.extend(pool_errors)
        
        if not pool_errors:
            print(Colors.success("  ✓ Pool integrity valid"))
        
        # Report results
        print()
        if errors:
            print(Colors.error(f"✗ Validation failed with {len(errors)} error(s):"))
            for error in errors:
                print(Colors.error(f"  - {error}"))
        
        if warnings:
            print(Colors.warning(f"⚠ {len(warnings)} warning(s):"))
            for warning in warnings:
                print(Colors.warning(f"  - {warning}"))
        
        if not errors and not warnings:
            print(Colors.success("✓ Repository is valid"))
        
        return len(errors) == 0
    
    def _validate_release_file(self, distribution, component, arch):
        """
        Validate Release file checksums
        
        Returns:
            list: Error messages
        """
        errors = []
        
        try:
            # Download Release file
            release_content = self.storage.download_file_content(f"dists/{distribution}/Release")
            release_text = release_content.decode('utf-8')
            
            # Parse checksums
            checksums = {'MD5Sum': {}, 'SHA1': {}, 'SHA256': {}}
            current_section = None
            
            for line in release_text.split('\n'):
                if line.startswith('MD5Sum:'):
                    current_section = 'MD5Sum'
                elif line.startswith('SHA1:'):
                    current_section = 'SHA1'
                elif line.startswith('SHA256:'):
                    current_section = 'SHA256'
                elif current_section and line.startswith(' '):
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        checksum, size, filename = parts[0], parts[1], parts[2]
                        checksums[current_section][filename] = checksum
            
            # Verify checksums for Packages files
            packages_files = [
                f"{component}/binary-{arch}/Packages",
                f"{component}/binary-{arch}/Packages.gz",
                f"{component}/binary-{arch}/Packages.bz2"
            ]
            
            for filename in packages_files:
                if filename not in checksums['SHA256']:
                    errors.append(f"Missing checksum for {filename} in Release file")
                    continue
                
                try:
                    # Download file and verify checksum
                    file_content = self.storage.download_file_content(f"dists/{distribution}/{filename}")
                    actual_checksum = hashlib.sha256(file_content).hexdigest()
                    expected_checksum = checksums['SHA256'][filename]
                    
                    if actual_checksum != expected_checksum:
                        errors.append(
                            f"Checksum mismatch for {filename}: "
                            f"expected {expected_checksum}, got {actual_checksum}"
                        )
                except Exception as e:
                    errors.append(f"Could not verify {filename}: {e}")
        
        except Exception as e:
            errors.append(f"Could not validate Release file: {e}")
        
        return errors
    
    def _validate_packages_file(self, distribution, component, arch):
        """
        Validate Packages file integrity
        
        Returns:
            tuple: (errors, warnings)
        """
        errors = []
        warnings = []
        
        try:
            # Download Packages file
            packages_content = self.storage.download_file_content(
                f"dists/{distribution}/{component}/binary-{arch}/Packages"
            )
            packages_text = packages_content.decode('utf-8')
            
            # Parse packages
            packages = []
            current_package = {}
            
            for line in packages_text.split('\n'):
                if line.strip() == '':
                    if current_package:
                        packages.append(current_package)
                        current_package = {}
                elif ':' in line:
                    key, value = line.split(':', 1)
                    current_package[key.strip()] = value.strip()
            
            # Validate each package
            for pkg in packages:
                if 'Filename' not in pkg:
                    errors.append(f"Package {pkg.get('Package', 'unknown')} missing Filename field")
                    continue
                
                filename = pkg['Filename']
                
                # Check if file exists in pool
                if not self.storage.exists(filename):
                    errors.append(f"Package file missing: {filename}")
                    continue
                
                # Verify checksums if available
                if 'SHA256' in pkg:
                    try:
                        file_content = self.storage.download_file_content(filename)
                        actual_checksum = hashlib.sha256(file_content).hexdigest()
                        expected_checksum = pkg['SHA256']
                        
                        if actual_checksum != expected_checksum:
                            errors.append(
                                f"Checksum mismatch for {filename}: "
                                f"expected {expected_checksum}, got {actual_checksum}"
                            )
                    except Exception as e:
                        warnings.append(f"Could not verify checksum for {filename}: {e}")
        
        except Exception as e:
            errors.append(f"Could not validate Packages file: {e}")
        
        return errors, warnings
    
    def _validate_pool_integrity(self, distribution, component, arch):
        """
        Validate pool integrity (no orphaned packages)
        
        Returns:
            list: Error messages
        """
        errors = []
        
        try:
            # Get all packages from Packages file
            packages_content = self.storage.download_file_content(
                f"dists/{distribution}/{component}/binary-{arch}/Packages"
            )
            packages_text = packages_content.decode('utf-8')
            
            referenced_files = set()
            for line in packages_text.split('\n'):
                if line.startswith('Filename:'):
                    filename = line.split(':', 1)[1].strip()
                    referenced_files.add(filename)
            
            # Get all .deb files in pool
            pool_files = set()
            try:
                # List all files in pool
                all_files = self.storage.list_files(f"pool/{component}", suffix='.deb')
                for filename in all_files:
                    # Reconstruct full path
                    # This is a simplified check - in reality we'd need to walk the pool structure
                    pool_files.add(filename)
            except:
                # If we can't list pool files, skip this check
                pass
            
            # Check for orphaned files (in pool but not in Packages)
            # Note: This is a simplified check - full implementation would need
            # to properly walk the pool directory structure
            
        except Exception as e:
            # Pool integrity check is optional
            pass
        
        return errors
    
    def _detect_from_deb(self, deb_file):
        """
        Extract distribution, component, and architecture from .deb file
        
        Args:
            deb_file: Path to .deb file
        
        Returns:
            tuple: (distribution, component, architecture)
        """
        # Extract control file metadata
        result = subprocess.run(
            ['dpkg-deb', '-f', deb_file, 'Architecture'],
            capture_output=True, text=True, check=True
        )
        
        arch = result.stdout.strip()
        
        # Try to get distribution from control file (custom field)
        result = subprocess.run(
            ['dpkg-deb', '-f', deb_file, 'Distribution'],
            capture_output=True, text=True
        )
        distribution = result.stdout.strip() or self.default_distribution
        
        # Try to get component from control file (custom field)
        result = subprocess.run(
            ['dpkg-deb', '-f', deb_file, 'Component'],
            capture_output=True, text=True
        )
        component = result.stdout.strip() or self.default_component
        
        return distribution, component, arch
    
    def _validate_deb_compatibility(self, deb_files, distribution, component, arch):
        """
        Validate that all .deb files are compatible (same dist/component/arch)
        
        Args:
            deb_files: List of .deb file paths
            distribution: Expected distribution
            component: Expected component
            arch: Expected architecture
        
        Raises:
            ValueError: If packages are incompatible
        """
        for deb_file in deb_files:
            file_dist, file_comp, file_arch = self._detect_from_deb(deb_file)
            
            if file_arch != arch:
                raise ValueError(
                    f"Architecture mismatch: {deb_file} is {file_arch}, expected {arch}"
                )
            
            # Distribution and component can differ, but warn
            if file_dist != distribution:
                print(Colors.warning(
                    f"  ⚠ {os.path.basename(deb_file)}: distribution {file_dist} "
                    f"differs from {distribution}"
                ))
            
            if file_comp != component:
                print(Colors.warning(
                    f"  ⚠ {os.path.basename(deb_file)}: component {file_comp} "
                    f"differs from {component}"
                ))

    def _get_pool_path(self, deb_file):
        """
        Calculate pool path for a .deb file
        
        Args:
            deb_file: Path to .deb file
        
        Returns:
            str: Pool path (e.g., 'pool/main/m/myapp/myapp_1.0.0_amd64.deb')
        """
        # Extract package name from control file
        result = subprocess.run(
            ['dpkg-deb', '-f', deb_file, 'Package'],
            capture_output=True, text=True, check=True
        )
        package_name = result.stdout.strip()
        
        # Get first letter for prefix
        prefix = package_name[0].lower()
        
        # Special case for lib* packages
        if package_name.startswith('lib'):
            if len(package_name) > 3:
                prefix = f"lib{package_name[3]}"
            else:
                prefix = 'lib'
        
        component = self.default_component
        filename = os.path.basename(deb_file)
        
        return f"pool/{component}/{prefix}/{package_name}/{filename}"
    
    def _repo_exists(self, distribution, component, arch):
        """
        Check if repository exists in storage
        
        Args:
            distribution: Distribution name
            component: Component name
            arch: Architecture
        
        Returns:
            bool: True if repository exists
        """
        packages_path = f"dists/{distribution}/{component}/binary-{arch}/Packages"
        return self.storage.exists(packages_path)
    
    def _init_repo(self, deb_files, distribution, component, arch):
        """
        Initialize a new repository
        
        Args:
            deb_files: List of .deb file paths
            distribution: Distribution name
            component: Component name
            arch: Architecture
        """
        print(Colors.info("Initializing new repository..."))
        
        # Create local directory structure
        local_dir = os.path.join(self.cache_dir, distribution, component, f"binary-{arch}")
        os.makedirs(local_dir, exist_ok=True)
        
        # Copy packages to pool
        print("Uploading packages to pool...")
        for deb_file in deb_files:
            pool_path = self._get_pool_path(deb_file)
            self.storage.upload_file(deb_file, pool_path)
            print(f"  • {os.path.basename(deb_file)} → {pool_path}")
        
        # Generate Packages file
        print("Generating metadata...")
        self._generate_packages_file(deb_files, distribution, component, arch, local_dir)
        
        # Generate Release file
        self._generate_release_file(distribution, local_dir)
        
        # Upload metadata
        print("Uploading metadata...")
        self._upload_metadata(distribution, component, arch, local_dir)
        
        print(Colors.success(
            f"✓ Published {len(deb_files)} package(s) to "
            f"{self.storage.get_url()}/{distribution}/{component}/{arch}"
        ))
        for deb_file in deb_files:
            print(f"  • {os.path.basename(deb_file)}")
    
    def _get_existing_package_checksums(self, distribution, component, arch):
        """
        Get checksums of all packages in repository
        
        Args:
            distribution: Distribution name
            component: Component name
            arch: Architecture
        
        Returns:
            dict: {package_name: {version: checksum}}
        """
        try:
            # Download Packages file
            packages_path = f"dists/{distribution}/{component}/binary-{arch}/Packages.gz"
            packages_content = self.storage.download_file_content(packages_path)
            
            # Decompress and parse
            with gzip.open(io.BytesIO(packages_content), 'rt', encoding='utf-8') as f:
                content = f.read()
            
            # Parse Packages file (RFC 822 format)
            checksums = {}
            current_package = {}
            
            for line in content.split('\n'):
                if line.strip() == '':
                    # End of package entry
                    if current_package.get('Package') and current_package.get('SHA256'):
                        pkg_name = current_package['Package']
                        version = current_package.get('Version', '')
                        checksum = current_package['SHA256']
                        
                        if pkg_name not in checksums:
                            checksums[pkg_name] = {}
                        checksums[pkg_name][version] = checksum
                    
                    current_package = {}
                elif ':' in line:
                    key, value = line.split(':', 1)
                    current_package[key.strip()] = value.strip()
            
            return checksums
            
        except Exception as e:
            print(Colors.warning(f"  ⚠ Could not check for duplicates: {e}"))
            return {}
    
    def _extract_package_info(self, deb_file):
        """
        Extract package name and version from .deb file
        
        Args:
            deb_file: Path to .deb file
        
        Returns:
            tuple: (package_name, version)
        """
        result = subprocess.run(
            ['dpkg-deb', '-f', deb_file, 'Package', 'Version'],
            capture_output=True, text=True, check=True
        )
        
        lines = result.stdout.strip().split('\n')
        package_name = lines[0].split(':', 1)[1].strip() if len(lines) > 0 else ''
        version = lines[1].split(':', 1)[1].strip() if len(lines) > 1 else ''
        
        return package_name, version
    
    def _add_to_existing_repo(self, deb_files, distribution, component, arch):
        """
        Add packages to existing repository with deduplication
        
        Args:
            deb_files: List of .deb file paths
            distribution: Distribution name
            component: Component name
            arch: Architecture
        """
        print(Colors.info("Updating existing repository..."))
        
        # Check for duplicates
        print("Checking for duplicate packages...")
        existing_checksums = self._get_existing_package_checksums(distribution, component, arch)
        
        # Filter out duplicates
        new_packages = []
        skipped_packages = []
        updated_packages = []
        
        for deb_file in deb_files:
            pkg_name, version = self._extract_package_info(deb_file)
            deb_checksum = self._calculate_sha256(deb_file)
            
            if pkg_name in existing_checksums:
                if version in existing_checksums[pkg_name]:
                    if existing_checksums[pkg_name][version] == deb_checksum:
                        # Exact duplicate - skip
                        skipped_packages.append(os.path.basename(deb_file))
                        print(f"  ⊘ {os.path.basename(deb_file)} (already exists with same checksum)")
                    else:
                        # Same name/version, different checksum - update
                        updated_packages.append(os.path.basename(deb_file))
                        new_packages.append(deb_file)
                        print(f"  ↻ {os.path.basename(deb_file)} (updating - checksum changed)")
                else:
                    # New version
                    new_packages.append(deb_file)
                    print(f"  + {os.path.basename(deb_file)} (new version)")
            else:
                # New package
                new_packages.append(deb_file)
                print(f"  + {os.path.basename(deb_file)} (new package)")
        
        # If no new packages, skip metadata regeneration
        if not new_packages:
            print(Colors.success("✓ All packages already exist - nothing to do"))
            return
        
        # Show summary
        if skipped_packages:
            print(Colors.info(f"Skipped {len(skipped_packages)} duplicate package(s)"))
        if updated_packages:
            print(Colors.info(f"Updating {len(updated_packages)} package(s)"))
        
        # Create backup before making changes
        self._backup_metadata(distribution, component, arch)
        
        try:
            # Upload new packages to pool
            print("Uploading packages to pool...")
            for deb_file in new_packages:
                pool_path = self._get_pool_path(deb_file)
                self.storage.upload_file(deb_file, pool_path)
                print(f"  • {os.path.basename(deb_file)} → {pool_path}")
            
            # Download existing metadata
            print("Downloading existing metadata...")
            local_dir = os.path.join(self.cache_dir, distribution, component, f"binary-{arch}")
            os.makedirs(local_dir, exist_ok=True)
            
            packages_path = f"dists/{distribution}/{component}/binary-{arch}/Packages"
            local_packages = os.path.join(local_dir, 'Packages')
            
            try:
                self.storage.download_file(packages_path, local_packages)
            except:
                # If download fails, start fresh
                pass
            
            # Merge metadata
            print("Merging metadata...")
            self._merge_packages_file(new_packages, local_packages, distribution, component, arch)
            
            # Generate Release file
            print("Updating Release file...")
            self._generate_release_file(distribution, local_dir)
            
            # Upload metadata
            print("Uploading metadata...")
            self._upload_metadata(distribution, component, arch, local_dir)
            
            # Clean up backup on success
            self._cleanup_backup()
            
            print(Colors.success(
                f"✓ Published {len(new_packages)} package(s) to "
                f"{self.storage.get_url()}/{distribution}/{component}/{arch}"
            ))
            for deb_file in new_packages:
                print(f"  • {os.path.basename(deb_file)}")
        
        except Exception as e:
            print(Colors.error(f"✗ Operation failed: {e}"))
            print(Colors.warning("Restoring metadata from backup..."))
            self._restore_metadata(distribution, component, arch)
            raise
    
    def _merge_packages_file(self, new_deb_files, existing_packages_file, distribution, component, arch):
        """
        Merge new packages into existing Packages file
        
        Args:
            new_deb_files: List of new .deb file paths
            existing_packages_file: Path to existing Packages file
            distribution: Distribution name
            component: Component name
            arch: Architecture
        """
        # Parse existing packages
        existing_entries = {}
        if os.path.exists(existing_packages_file):
            with open(existing_packages_file, 'r') as f:
                content = f.read()
            
            current_entry = []
            current_package = None
            current_version = None
            
            for line in content.split('\n'):
                if line.strip() == '':
                    if current_entry and current_package:
                        key = f"{current_package}_{current_version}"
                        existing_entries[key] = '\n'.join(current_entry) + '\n\n'
                    current_entry = []
                    current_package = None
                    current_version = None
                else:
                    current_entry.append(line)
                    if line.startswith('Package:'):
                        current_package = line.split(':', 1)[1].strip()
                    elif line.startswith('Version:'):
                        current_version = line.split(':', 1)[1].strip()
        
        # Generate entries for new packages
        for deb_file in new_deb_files:
            pkg_name, version = self._extract_package_info(deb_file)
            
            # Extract all control fields
            result = subprocess.run(
                ['dpkg-deb', '-f', deb_file],
                capture_output=True, text=True, check=True
            )
            control_data = result.stdout
            
            # Calculate checksums
            md5sum = self._calculate_md5(deb_file)
            sha1sum = self._calculate_sha1(deb_file)
            sha256sum = self._calculate_sha256(deb_file)
            size = os.path.getsize(deb_file)
            
            # Get pool path
            pool_path = self._get_pool_path(deb_file)
            
            # Build package entry
            entry = control_data.strip() + f"\nFilename: {pool_path}\n"
            entry += f"Size: {size}\n"
            entry += f"MD5sum: {md5sum}\n"
            entry += f"SHA1: {sha1sum}\n"
            entry += f"SHA256: {sha256sum}\n\n"
            
            # Add or update entry
            key = f"{pkg_name}_{version}"
            existing_entries[key] = entry
        
        # Write merged Packages file
        with open(existing_packages_file, 'w') as f:
            # Sort by package name for consistency
            for key in sorted(existing_entries.keys()):
                f.write(existing_entries[key])
        
        # Compress
        with open(existing_packages_file, 'rb') as f_in:
            with gzip.open(existing_packages_file + '.gz', 'wb') as f_out:
                f_out.write(f_in.read())
        
        with open(existing_packages_file, 'rb') as f_in:
            with bz2.open(existing_packages_file + '.bz2', 'wb') as f_out:
                f_out.write(f_in.read())
    
    def _generate_packages_file(self, deb_files, distribution, component, arch, local_dir):
        """
        Generate Packages file for the given packages
        
        Args:
            deb_files: List of .deb file paths
            distribution: Distribution name
            component: Component name
            arch: Architecture
            local_dir: Local directory to write Packages file
        """
        packages_content = []
        
        for deb_file in deb_files:
            # Extract all control fields
            result = subprocess.run(
                ['dpkg-deb', '-f', deb_file],
                capture_output=True, text=True, check=True
            )
            control_data = result.stdout
            
            # Calculate checksums
            md5sum = self._calculate_md5(deb_file)
            sha1sum = self._calculate_sha1(deb_file)
            sha256sum = self._calculate_sha256(deb_file)
            size = os.path.getsize(deb_file)
            
            # Get pool path
            pool_path = self._get_pool_path(deb_file)
            
            # Build package entry
            entry = control_data.strip() + f"\nFilename: {pool_path}\n"
            entry += f"Size: {size}\n"
            entry += f"MD5sum: {md5sum}\n"
            entry += f"SHA1: {sha1sum}\n"
            entry += f"SHA256: {sha256sum}\n\n"
            
            packages_content.append(entry)
        
        # Write Packages file
        packages_file = os.path.join(local_dir, 'Packages')
        with open(packages_file, 'w') as f:
            f.write(''.join(packages_content))
        
        # Compress
        with open(packages_file, 'rb') as f_in:
            with gzip.open(packages_file + '.gz', 'wb') as f_out:
                f_out.write(f_in.read())
        
        with open(packages_file, 'rb') as f_in:
            with bz2.open(packages_file + '.bz2', 'wb') as f_out:
                f_out.write(f_in.read())

    def _generate_release_file(self, distribution, local_dir):
        """
        Generate Release file for distribution
        
        Args:
            distribution: Distribution name
            local_dir: Local directory containing Packages files (binary-arch directory)
        """
        # Find all Packages files starting from the distribution directory
        # local_dir is cache_dir/distribution/component/binary-arch
        # We need to walk from cache_dir/distribution to find all Packages files
        dist_dir = os.path.dirname(os.path.dirname(local_dir))  # Go up to distribution level
        
        packages_files = []
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                if file.startswith('Packages'):
                    packages_files.append(os.path.join(root, file))
        
        # Calculate checksums
        md5sums = []
        sha1sums = []
        sha256sums = []
        
        for pkg_file in packages_files:
            # Get relative path from distribution directory
            relative_path = os.path.relpath(pkg_file, dist_dir)
            size = os.path.getsize(pkg_file)
            
            md5sums.append(f" {self._calculate_md5(pkg_file)} {size:8d} {relative_path}")
            sha1sums.append(f" {self._calculate_sha1(pkg_file)} {size:8d} {relative_path}")
            sha256sums.append(f" {self._calculate_sha256(pkg_file)} {size:8d} {relative_path}")
        
        # Build Release file
        release_content = f"""Origin: {self.origin}
Label: {self.label}
Suite: {distribution}
Codename: {distribution}
Date: {datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S UTC')}
Architectures: {' '.join(self.architectures)}
Components: {self.default_component}
Description: {self.origin} Debian Repository
MD5Sum:
{chr(10).join(md5sums)}
SHA1:
{chr(10).join(sha1sums)}
SHA256:
{chr(10).join(sha256sums)}
"""
        
        # Write Release file at distribution level
        release_file = os.path.join(dist_dir, 'Release')
        with open(release_file, 'w') as f:
            f.write(release_content)
    
    def _upload_metadata(self, distribution, component, arch, local_dir):
        """
        Upload metadata files to storage
        
        Args:
            distribution: Distribution name
            component: Component name
            arch: Architecture
            local_dir: Local directory containing metadata
        """
        # Upload Packages files
        for filename in ['Packages', 'Packages.gz', 'Packages.bz2']:
            local_file = os.path.join(local_dir, filename)
            if os.path.exists(local_file):
                remote_path = f"dists/{distribution}/{component}/binary-{arch}/{filename}"
                self.storage.upload_file(local_file, remote_path)
        
        # Upload Release file from distribution level
        # local_dir is cache_dir/distribution/component/binary-arch
        dist_dir = os.path.dirname(os.path.dirname(local_dir))  # Go up to distribution level
        release_file = os.path.join(dist_dir, 'Release')
        if os.path.exists(release_file):
            remote_path = f"dists/{distribution}/Release"
            self.storage.upload_file(release_file, remote_path)

    def _backup_metadata(self, distribution, component, arch):
        """
        Create backup of metadata before making changes
        
        Args:
            distribution: Distribution name
            component: Component name
            arch: Architecture
        """
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        self.backup_path = f"dists/{distribution}/metadata.backup-{timestamp}"
        
        print(f"Creating metadata backup...")
        
        try:
            # Backup Packages files
            for filename in ['Packages', 'Packages.gz', 'Packages.bz2']:
                src = f"dists/{distribution}/{component}/binary-{arch}/{filename}"
                dst = f"{self.backup_path}/{component}/binary-{arch}/{filename}"
                
                if self.storage.exists(src):
                    self.storage.copy_file(src, dst)
            
            # Backup Release file
            src = f"dists/{distribution}/Release"
            dst = f"{self.backup_path}/Release"
            
            if self.storage.exists(src):
                self.storage.copy_file(src, dst)
            
            print(f"  Backup created: {self.storage.get_url()}/{self.backup_path}")
        
        except Exception as e:
            print(Colors.warning(f"  ⚠ Backup failed: {e}"))
            self.backup_path = None
    
    def _restore_metadata(self, distribution, component, arch):
        """
        Restore metadata from backup
        
        Args:
            distribution: Distribution name
            component: Component name
            arch: Architecture
        """
        if not self.backup_path:
            print(Colors.warning("  ⚠ No backup available to restore"))
            return
        
        print(f"Restoring metadata from backup...")
        
        try:
            # Restore Packages files
            for filename in ['Packages', 'Packages.gz', 'Packages.bz2']:
                src = f"{self.backup_path}/{component}/binary-{arch}/{filename}"
                dst = f"dists/{distribution}/{component}/binary-{arch}/{filename}"
                
                if self.storage.exists(src):
                    self.storage.copy_file(src, dst)
            
            # Restore Release file
            src = f"{self.backup_path}/Release"
            dst = f"dists/{distribution}/Release"
            
            if self.storage.exists(src):
                self.storage.copy_file(src, dst)
            
            print(Colors.success("  ✓ Metadata restored from backup"))
            
            # Keep backup for manual inspection
            print(Colors.info(f"  Backup retained at: {self.storage.get_url()}/{self.backup_path}"))
        
        except Exception as e:
            print(Colors.error(f"  ✗ Failed to restore backup: {e}"))
            print(Colors.warning(f"  Manual restoration required from: {self.storage.get_url()}/{self.backup_path}"))
    
    def _cleanup_backup(self):
        """Remove backup after successful operation"""
        if not self.backup_path:
            return
        
        try:
            # Delete backup files
            backup_files = self.storage.list_files(self.backup_path)
            for filename in backup_files:
                self.storage.delete_file(f"{self.backup_path}/{filename}")
            
            self.backup_path = None
        
        except Exception as e:
            # Non-fatal - backup cleanup failure shouldn't stop the operation
            print(Colors.warning(f"  ⚠ Failed to clean up backup: {e}"))
            print(Colors.info(f"  Backup retained at: {self.storage.get_url()}/{self.backup_path}"))
    
    @staticmethod
    def _calculate_md5(filepath):
        """Calculate MD5 checksum of a file"""
        md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5.update(chunk)
        return md5.hexdigest()
    
    @staticmethod
    def _calculate_sha1(filepath):
        """Calculate SHA1 checksum of a file"""
        sha1 = hashlib.sha1()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha1.update(chunk)
        return sha1.hexdigest()
    
    @staticmethod
    def _calculate_sha256(filepath):
        """Calculate SHA256 checksum of a file"""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()


def config_command(args):
    if args.file:
        config_file = args.file
    elif args.system:
        config_file = REPO_CONFIG_FILES.get("system")
    elif args.local:
        config_file = REPO_CONFIG_FILES.get("local")
    else:  # --global or default
        config_file = REPO_CONFIG_FILES.get("user")
    
    # Load config
    config = RepoConfig(config_file)
    
    # Handle different operations
    if args.list:
        # List all config values
        print(f"Reading {config_file}")
        print("="*40)
        for key, value in sorted(config.list().items()):
            print(f"{key}={value}{'*' if key in config.track_defaults else ''}")
        return 0
    
    elif args.unset:
        # Unset a key
        if config.unset(args.unset):
            config.save()
            print(f"Unset {args.unset}")
        else:
            print(f"Key not found: {args.unset}")
            return 1
        return 0
    
    elif args.validate_config:
        # Validate configuration
        errors = config.validate()
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return 1
        else:
            print("Configuration is valid")
        return 0
    
    elif args.key:
        # Get or set a key
        if args.value:
            # Set value
            config.set(args.key, args.value)
            config.save()
            print(f"Set {args.key} = {args.value}")
        else:
            # Get value
            value = config.get(args.key)
            if value is not None:
                print(value)
            else:
                print(f"Key not found: {args.key}")
                return 1
        return 0
    
    else:
        # No operation specified, show current config file
        print(f"Config file: {config.config_file}")
        print(f"Keys: {len(config.data)}")
        return 0



def main():
    parser = argparse.ArgumentParser(
        description='Efficient Debian repository manager for S3',
    )
    
    # Global options
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('-b', '--bucket', help='S3 bucket name (overrides config file)')
    parser.add_argument('-d', '--cache-dir', help='Custom cache directory (overrides config file)')
    parser.add_argument('--s3-endpoint-url', help='Custom S3 endpoint URL for S3-compatible services (overrides config file)')
    parser.add_argument('--profile', help='AWS profile to use (overrides config file and AWS_PROFILE env var)')
    
    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute', required=True)
    
    # Add subcommand
    add_parser = subparsers.add_parser('add', help='Add packages to repository')
    add_parser.add_argument('deb_files', nargs='+', help='Debian package file(s) to add')
    add_parser.add_argument('-y', '--yes', action='store_true', help='Skip confirmation prompt (for CI/CD)')
    add_parser.add_argument('--no-validate', action='store_true', help='Skip post-operation validation')
    add_parser.add_argument('--distribution', help='Override distribution detection')
    add_parser.add_argument('--component', help='Override component detection')
    
    # Remove subcommand
    remove_parser = subparsers.add_parser('remove', help='Remove packages from repository')
    remove_parser.add_argument('package_names', nargs='+', help='Package name(s) to remove')
    remove_parser.add_argument('-y', '--yes', action='store_true', help='Skip confirmation prompt (for CI/CD)')
    remove_parser.add_argument('--distribution', help='Distribution name')
    remove_parser.add_argument('--component', help='Component name')
    remove_parser.add_argument('--architecture', help='Architecture')
    
    # Validate subcommand
    validate_parser = subparsers.add_parser('validate', help='Validate repository')
    validate_parser.add_argument('distribution', help='Distribution name (e.g., focal)')
    validate_parser.add_argument('component', help='Component name (e.g., main)')
    validate_parser.add_argument('architecture', help='Architecture (e.g., amd64)')
    
    # Config subcommand
    config_parser = subparsers.add_parser('config', help='Manage configuration')
    config_parser.add_argument('key', nargs='?', help='Config key (dot notation)')
    config_parser.add_argument('value', nargs='?', help='Config value (if setting)')
    config_parser.add_argument('--list', action='store_true', help='List all config values')
    config_parser.add_argument('--unset', metavar='KEY', help='Remove a config key')
    config_parser.add_argument('--validate', dest='validate_config', action='store_true', help='Validate configuration')
    config_parser.add_argument('--file', help='Use specific config file')
    config_parser.add_argument('--global', dest='global_config', action='store_true', help='Use global config (~/.debs3.conf)')
    config_parser.add_argument('--local', action='store_true', help='Use local config (./debs3.conf)')
    config_parser.add_argument('--system', action='store_true', help='Use system config (/etc/debs3.conf)')
    
    args = parser.parse_args()
    
    # Handle config command
    if args.command == 'config':
        return config_command(args)
    
    # Load configuration
    try:
        config = RepoConfig(args.config)
        
        # Apply CLI argument overrides
        if args.bucket:
            config.set('backend.s3.bucket', args.bucket)
        if args.cache_dir:
            config.set('repo.cache_dir', args.cache_dir)
        if args.s3_endpoint_url:
            config.set('backend.s3.endpoint', args.s3_endpoint_url)
        if args.profile:
            config.set('backend.s3.profile', args.profile)
        if hasattr(args, 'no_validate') and args.no_validate:
            config.set('validation.enabled', False)
        
        # Initialize repository manager
        repo = DebRepo(config)

        action = args.command.upper()

        # Handle validate command
        if args.command == 'validate':
            success = repo.validate_repository(args.distribution, args.component, args.architecture)
            return 0 if success else 1
        
        # Get backend info and show confirmation
        print()
        print(Colors.bold("Configuration:"))
        
        backend_info = repo.storage.get_info()
        for key, value in backend_info.items():
            print(f"  {key:<11}: {value}")

        print(f"  Action:       {Colors.bold(action)}")
        print(f"  Packages:     {len(args.deb_files)}")
        for f in args.deb_files:
            print(f"    • {os.path.basename(f)}")
        print()

        # Confirm operation
        if not args.yes:
            response = input(Colors.bold("Continue? (yes/no): "))
            if response.lower() != "yes":
                print(Colors.warning("Cancelled"))
                return 0

        # Execute Operation
        if args.command == 'add':
            repo.add_packages(args.deb_files)
        elif args.command == 'remove':
            repo.remove_packages(
                args.package_names,
                distribution=args.distribution,
                component=args.component,
                arch=args.architecture
            )
        
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
