"""
Generic CLI for repository managers

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""

import argparse
import os
import sys

from core.config import RepoConfig
from core.constants import REPO_CONFIG_FILES
from core import Colors


def create_repo_manager(config, repo_type):
    """Factory function to create appropriate repo manager"""
    if repo_type == 'rpm':
        from core.yum import YumRepo
        return YumRepo(config)
    elif repo_type == 'deb':
        from core.deb import DebRepo
        return DebRepo(config)
    else:
        raise ValueError(f"Unknown repo type: {repo_type}")


def config_command(args, repo_type):
    """Handle config subcommand"""
    if args.file:
        config_file = args.file
    elif args.system:
        config_file = REPO_CONFIG_FILES.get("system")
    elif args.local:
        config_file = REPO_CONFIG_FILES.get("local")
    else:  # --global or default
        config_file = REPO_CONFIG_FILES.get("user")
    
    config = RepoConfig(config_file)
    
    if args.list:
        print(f"Reading {config_file}")
        print("="*40)
        for key, value in sorted(config.list().items()):
            print(f"{key}={value}{'*' if key in config.track_defaults else ''}")
        return 0
    
    elif args.unset:
        if config.unset(args.unset):
            config.save()
            print(f"Unset {args.unset}")
        else:
            print(f"Key not found: {args.unset}")
            return 1
        return 0
    
    elif args.validate_config:
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
        if args.value:
            config.set(args.key, args.value)
            config.save()
            print(f"Set {args.key} = {args.value}")
        else:
            value = config.get(args.key)
            if value is not None:
                print(value)
            else:
                print(f"Key not found: {args.key}")
                return 1
        return 0
    
    else:
        print(f"Config file: {config.config_file}")
        print(f"Keys: {len(config.data)}")
        return 0


def create_parser(repo_type):
    """Create argument parser for repo type"""
    script_name = 'yums3' if repo_type == 'rpm' else 'debs3'
    repo_name = 'YUM' if repo_type == 'rpm' else 'Debian'
    
    parser = argparse.ArgumentParser(
        description=f'Efficient {repo_name} repository manager for S3',
    )
    
    # Global options
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('-b', '--bucket', help='S3 bucket name (overrides config file)')
    parser.add_argument('-d', '--cache-dir', help='Custom cache directory (overrides config file)')
    parser.add_argument('--s3-endpoint-url', help='Custom S3 endpoint URL for S3-compatible services (overrides config file)')
    parser.add_argument('--profile', help='AWS profile to use (overrides config file and AWS_PROFILE env var)')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute', required=True)
    
    # Add subcommand
    add_parser = subparsers.add_parser('add', help='Add packages to repository')
    if repo_type == 'rpm':
        add_parser.add_argument('rpm_files', nargs='+', help='RPM file(s) to add')
    else:
        add_parser.add_argument('deb_files', nargs='+', help='Debian package file(s) to add')
        add_parser.add_argument('--distribution', help='Override distribution detection')
        add_parser.add_argument('--component', help='Override component detection')
    add_parser.add_argument('-y', '--yes', action='store_true', help='Skip confirmation prompt (for CI/CD)')
    add_parser.add_argument('--no-validate', action='store_true', help='Skip post-operation validation')
    
    # Remove subcommand
    remove_parser = subparsers.add_parser('remove', help='Remove packages from repository')
    if repo_type == 'rpm':
        remove_parser.add_argument('rpm_files', nargs='+', help='RPM filename(s) to remove')
    else:
        remove_parser.add_argument('package_names', nargs='+', help='Package name(s) to remove')
        remove_parser.add_argument('--distribution', help='Distribution name')
        remove_parser.add_argument('--component', help='Component name')
        remove_parser.add_argument('--architecture', help='Architecture')
    remove_parser.add_argument('-y', '--yes', action='store_true', help='Skip confirmation prompt (for CI/CD)')
    remove_parser.add_argument('--no-validate', action='store_true', help='Skip post-operation validation')
    
    # Validate subcommand
    validate_parser = subparsers.add_parser('validate', help='Validate repository')
    if repo_type == 'rpm':
        validate_parser.add_argument('repo_path', help='Repository path (e.g., el9/x86_64)')
    else:
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
    config_parser.add_argument('--global', dest='global_config', action='store_true', help='Use global config')
    config_parser.add_argument('--local', action='store_true', help='Use local config')
    config_parser.add_argument('--system', action='store_true', help='Use system config')
    
    return parser


def main(repo_type):
    """Generic main function for both RPM and DEB repos"""
    parser = create_parser(repo_type)
    args = parser.parse_args()
    
    # Handle config command
    if args.command == 'config':
        return config_command(args, repo_type)
    
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
        repo = create_repo_manager(config, repo_type)
        
        # Handle validate command
        if args.command == 'validate':
            if repo_type == 'rpm':
                parts = args.repo_path.split('/')
                if len(parts) != 2:
                    print(Colors.error("✗ Error: Invalid format. Use: el_version/arch (e.g., el9/x86_64)"))
                    return 1
                el_version, arch = parts
                success = repo.validate_repository(el_version, arch)
            else:
                success = repo.validate_repository(args.distribution, args.component, args.architecture)
            return 0 if success else 1
        
        # Get files for operation
        if repo_type == 'rpm':
            files = args.rpm_files if args.command == 'add' else args.rpm_files
        else:
            files = args.deb_files if args.command == 'add' else args.package_names
        
        # Show confirmation
        print()
        print(Colors.bold("Configuration:"))
        
        backend_info = repo.storage.get_info()
        for key, value in backend_info.items():
            print(f"  {key:<13}: {value}")
        
        print(f"  Action:       {Colors.bold(args.command.upper())}")
        print(f"  Packages:     {len(files)}")
        for f in files:
            print(f"    • {os.path.basename(f)}")
        print()
        
        # Confirm operation
        if not args.yes:
            response = input(Colors.bold("Continue? (yes/no): "))
            if response.lower() != "yes":
                print(Colors.warning("Cancelled"))
                return 0
        
        # Execute operation
        if args.command == 'add':
            if repo_type == 'rpm':
                repo.add_packages(files)
            else:
                repo.add_packages(files)
        elif args.command == 'remove':
            if repo_type == 'rpm':
                repo.remove_packages(files)
            else:
                repo.remove_packages(
                    files,
                    distribution=getattr(args, 'distribution', None),
                    component=getattr(args, 'component', None),
                    arch=getattr(args, 'architecture', None)
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
