"""
Storage backend abstraction for yums3

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import os
import subprocess
from abc import ABC, abstractmethod
from typing import List, Optional
from .config import RepoConfig

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception


class FileTracker:
    """Track file changes during repository operations"""
    
    def __init__(self):
        self.added_files = []      # New files added in this operation
        self.existing_files = []   # Files that existed before
        self.modified_files = []   # Existing files that were modified
        self.deleted_files = []    # Files that were deleted
    
    def mark_added(self, filename: str):
        """Mark a file as newly added"""
        if filename not in self.added_files:
            self.added_files.append(filename)
    
    def mark_existing(self, filename: str):
        """Mark a file as existing before this operation"""
        if filename not in self.existing_files:
            self.existing_files.append(filename)
    
    def mark_modified(self, filename: str):
        """Mark a file as modified during this operation"""
        if filename not in self.modified_files:
            self.modified_files.append(filename)
    
    def mark_deleted(self, filename: str):
        """Mark a file as deleted during this operation"""
        if filename not in self.deleted_files:
            self.deleted_files.append(filename)
    
    def get_all_current_files(self) -> List[str]:
        """Get all files that should exist after operation"""
        current = set(self.existing_files + self.added_files)
        current -= set(self.deleted_files)
        return list(current)


class StorageBackend(ABC):
    def __init__(self, args):
        if 'debug' in args and args.debug == "True":
            self.debug = True

    def verbose(self, output):
        if self.debug:
            print(f" - [debug] {output}")

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a file exists at the given path"""
        pass
    
    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a single file from storage to local path"""
        pass
    
    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a single file from local path to storage"""
        pass
    
    @abstractmethod
    def delete_file(self, path: str) -> None:
        """Delete a file from storage"""
        pass
    
    @abstractmethod
    def list_files(self, prefix: str, suffix: Optional[str] = None) -> List[str]:
        """List files with optional prefix and suffix filters
        
        Args:
            prefix: Path prefix to search under
            suffix: Optional file extension filter (e.g., '.rpm')
        
        Returns:
            List of relative filenames (not full paths)
        """
        pass
    
    @abstractmethod
    def sync_from_storage(self, remote_prefix: str, local_dir: str) -> List[str]:
        """Sync directory from storage to local
        
        Args:
            remote_prefix: Remote path prefix
            local_dir: Local directory to sync to
        
        Returns:
            List of files downloaded
        """
        pass
    
    @abstractmethod
    def sync_to_storage(self, local_dir: str, remote_prefix: str) -> List[str]:
        """Sync directory from local to storage
        
        Args:
            local_dir: Local directory to sync from
            remote_prefix: Remote path prefix
        
        Returns:
            List of files uploaded
        """
        pass
    
    @abstractmethod
    def get_url(self) -> str:
        """Get human-readable URL for display purposes"""
        pass
    
    @abstractmethod
    def download_file_content(self, remote_path: str) -> bytes:
        """Download file content directly to memory
        
        Args:
            remote_path: Path to file in storage
        
        Returns:
            File content as bytes
        
        Note: Use for small files only (metadata, not large RPMs)
        """
        pass
    
    @abstractmethod
    def copy_file(self, src_path: str, dst_path: str) -> None:
        """Copy a file within storage (backends can optimize this)
        
        Args:
            src_path: Source path in storage
            dst_path: Destination path in storage
        """
        pass
    
    @abstractmethod
    def get_info(self) -> dict:
        """Get backend information for display
        
        Returns:
            Dictionary with display name as key and value as value
            Example: {"Storage": "file:///path/to/storage"}
        """
        pass


def create_storage_backend(config: RepoConfig, repo_type: str) -> StorageBackend:
    """Create storage backend from configuration"""
    storage_type = config.get('backend.type', 's3')
    
    if storage_type == 's3':
        return S3StorageBackend(config, repo_type)
    elif storage_type == 'local':
        return LocalStorageBackend(config, repo_type)
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")


class S3StorageBackend(StorageBackend):
    def __init__(self, config: RepoConfig, repo_type: str):
        """
        Initialize S3 storage backend
                
        Raises:
            ValueError: If bucket_name is not provided
            ImportError: If boto3 is not installed
        """
        if boto3 is None:
            raise ImportError("boto3 is required for S3StorageBackend. Install it with: pip install boto3")

        bucket_name = config.get_for_type('backend.s3.bucket', repo_type)
        endpoint = config.get_for_type('backend.s3.endpoint', repo_type)

        # Validate required configuration
        if not bucket_name:
            raise ValueError(f"backend.{repo_type}.s3.bucket is required for S3StorageBackend and {repo_type} repo")
        
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint

        aws_profile = config.get_for_type('backend.s3.profile', repo_type)
        aws_region = config.get_for_type('backend.s3.region', repo_type)
        
        # Determine which profile/region to use:
        # 1. Explicit profile from config (if not 'default')
        # 2. AWS_PROFILE environment variable (boto3 handles this automatically when profile_name=None)
        # 3. Default credentials chain (when profile_name=None)
        self.aws_profile_src = None
        if aws_profile and aws_profile != 'default':
            self.aws_profile = aws_profile
            self.aws_profile_src = config.config_file
        elif os.environ.get('AWS_PROFILE'):
            self.aws_profile = os.environ.get('AWS_PROFILE')
            self.aws_profile_src = "AWS_PROFILE"
        else:
            self.aws_profile = None
        
        self.aws_region_src = None
        if aws_region:
            self.aws_region = aws_region
            self.aws_region_src = config.config_file
        elif os.environ.get('AWS_REGION'):
            self.aws_region = os.environ.get('AWS_REGION')
            self.aws_region_src = "AWS_REGION"
        else:
            self.aws_region = None

        # Initialize boto3 client
        session = boto3.Session(
            profile_name=self.aws_profile,
            region_name=self.aws_region
        )
        s3_config = {}
        if self.endpoint_url:
            s3_config['endpoint_url'] = endpoint_url

        self.s3_client = session.client('s3', **s3_config)

        self.debug = config.get('backend.debug', False)
    
    def exists(self, path: str) -> bool:
        """Check if a file exists in S3"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=path)
            return True
        except ClientError:
            return False
    
    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from S3 to local path"""
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.s3_client.download_file(
            self.bucket_name,
            remote_path,
            local_path
        )
    
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a file from local path to S3"""
        self.s3_client.upload_file(local_path, self.bucket_name, remote_path)
    
    def delete_file(self, path: str) -> None:
        """Delete a file from S3"""
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=path)
    
    def list_files(self, prefix: str, suffix: Optional[str] = None) -> List[str]:
        """List files in S3 with optional suffix filter"""
        objects = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    filename = key.split('/')[-1]
                    if suffix is None or filename.endswith(suffix):
                        objects.append(filename)
        
        return objects
    
    def sync_from_storage(self, remote_prefix: str, local_dir: str) -> List[str]:
        """Sync directory from S3 to local"""
        os.makedirs(local_dir, exist_ok=True)
        downloaded = []
        
        paginator = self.s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=remote_prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    relative_path = key[len(remote_prefix):].lstrip('/')
                    if not relative_path:
                        continue
                    
                    local_file = os.path.join(local_dir, relative_path)
                    os.makedirs(os.path.dirname(local_file), exist_ok=True)
                    self.s3_client.download_file(self.bucket_name, key, local_file)
                    downloaded.append(relative_path)
        
        return downloaded
    
    def sync_to_storage(self, local_dir: str, remote_prefix: str) -> List[str]:
        """Sync directory from local to S3"""
        uploaded = []
        
        for root, dirs, files in os.walk(local_dir):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_dir)
                s3_key = f"{remote_prefix}/{relative_path}".replace('//', '/')
                self.s3_client.upload_file(local_path, self.bucket_name, s3_key)
                uploaded.append(relative_path)
        
        return uploaded
    
    def get_url(self) -> str:
        """Get S3 URL for display"""
        if self.endpoint_url:
            return f"{self.endpoint_url}/{self.bucket_name}"
        return f"https://{self.bucket_name}.s3.amazonaws.com"
    
    def download_file_content(self, remote_path: str) -> bytes:
        """Download file content directly to memory"""
        obj = self.s3_client.get_object(Bucket=self.bucket_name, Key=remote_path)
        return obj['Body'].read()
    
    def copy_file(self, src_path: str, dst_path: str) -> None:
        """Copy a file within S3 (uses efficient copy_object)"""
        self.verbose(f"copy {src_path} -> {dst_path}")
        self.s3_client.copy_object(
            Bucket=self.bucket_name,
            CopySource={'Bucket': self.bucket_name, 'Key': src_path},
            Key=dst_path
        )
    
    def get_info(self) -> dict:
        """Get S3 backend information for display"""
        info = {}
        
        # Get AWS account
        try:
            sts_client = boto3.client('sts')
            identity = sts_client.get_caller_identity()
            info['AWS Account'] = identity['Account']
        except:
            info['AWS Account'] = "Unable to determine"
        
        # Get AWS region
        info['AWS Region'] = f"{self.aws_region} (from {self.aws_region_src})"
        info['AWS Profile'] = f"{self.aws_profile} (from {self.aws_profile_src})"
        
        # Get S3 URL
        info['S3 URL'] = self.get_url()
        
        return info


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend for testing"""
    
    def __init__(self, config: RepoConfig, repo_type: str):
        """
        Initialize local storage backend
        
        Args:
            base_path: Base directory for storage
        
        Raises:
            ValueError: If base_path is not provided or is empty
        """
        # Validate required configuration
        base_path = config.get_for_type('backend.local.path', repo_type)

        if not base_path:
            raise ValueError("base_path is required for LocalStorageBackend")
        
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)
    
    def _get_full_path(self, path: str) -> str:
        """Convert relative path to full path"""
        return os.path.join(self.base_path, path.lstrip('/'))
    
    def exists(self, path: str) -> bool:
        """Check if a file exists in local storage"""
        return os.path.exists(self._get_full_path(path))
    
    def download_file(self, remote_path: str, local_path: str) -> None:
        """Copy from 'remote' (base_path) to local working directory"""
        src = self._get_full_path(remote_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        subprocess.run(['cp', src, local_path], check=True)
    
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Copy from local working directory to 'remote' (base_path)"""
        dst = self._get_full_path(remote_path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        subprocess.run(['cp', local_path, dst], check=True)
    
    def delete_file(self, path: str) -> None:
        """Delete a file from local storage"""
        full_path = self._get_full_path(path)
        if os.path.exists(full_path):
            os.remove(full_path)
    
    def list_files(self, prefix: str, suffix: Optional[str] = None) -> List[str]:
        """List files in local storage with optional suffix filter"""
        prefix_path = self._get_full_path(prefix)
        if not os.path.exists(prefix_path):
            return []
        
        files = []
        if os.path.isfile(prefix_path):
            filename = os.path.basename(prefix_path)
            if suffix is None or filename.endswith(suffix):
                files.append(filename)
        else:
            for item in os.listdir(prefix_path):
                item_path = os.path.join(prefix_path, item)
                if os.path.isfile(item_path):
                    if suffix is None or item.endswith(suffix):
                        files.append(item)
        
        return files
    
    def sync_from_storage(self, remote_prefix: str, local_dir: str) -> List[str]:
        """Copy directory from base_path to local working directory"""
        src = self._get_full_path(remote_prefix)
        os.makedirs(local_dir, exist_ok=True)
        
        if not os.path.exists(src):
            return []
        
        downloaded = []
        for root, dirs, files in os.walk(src):
            for file in files:
                src_file = os.path.join(root, file)
                relative_path = os.path.relpath(src_file, src)
                dst_file = os.path.join(local_dir, relative_path)
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                subprocess.run(['cp', src_file, dst_file], check=True)
                downloaded.append(relative_path)
        
        return downloaded
    
    def sync_to_storage(self, local_dir: str, remote_prefix: str) -> List[str]:
        """Copy directory from local working directory to base_path"""
        dst = self._get_full_path(remote_prefix)
        os.makedirs(dst, exist_ok=True)
        
        uploaded = []
        for root, dirs, files in os.walk(local_dir):
            for file in files:
                src_file = os.path.join(root, file)
                relative_path = os.path.relpath(src_file, local_dir)
                dst_file = os.path.join(dst, relative_path)
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                subprocess.run(['cp', src_file, dst_file], check=True)
                uploaded.append(relative_path)
        
        return uploaded
    
    def get_url(self) -> str:
        """Get file:// URL for display"""
        return f"file://{self.base_path}"
    
    def download_file_content(self, remote_path: str) -> bytes:
        """Download file content directly to memory"""
        full_path = self._get_full_path(remote_path)
        with open(full_path, 'rb') as f:
            return f.read()
    
    def copy_file(self, src_path: str, dst_path: str) -> None:
        """Copy a file within local storage"""
        import shutil
        src_full = self._get_full_path(src_path)
        dst_full = self._get_full_path(dst_path)
        os.makedirs(os.path.dirname(dst_full), exist_ok=True)
        shutil.copy2(src_full, dst_full)
    
    def get_info(self) -> dict:
        """Get local storage backend information for display"""
        return {
            'Storage': self.get_url()
        }
