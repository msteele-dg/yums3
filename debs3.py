#!/usr/bin/env python3
"""
Debian repository manager

Copyright (c) 2025 Deepgram
Author: Michael Steele <michael.steele@deepgram.com>

Licensed under the MIT License. See LICENSE file for details.
"""


import argparse
import os
import sys
import re

from core.config import load_config, config_command
from core.deb import DebRepo
from core import Colors


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

    replicate_parser = subparsers.add_parser('replicate', help="Replicate packages between distributions")
    replicate_parser.add_argument('package_names', nargs='+', help='Package name(s) or package_version to replicate')
    replicate_parser.add_argument('--src', required=True, help='Source distribution (e.g., focal)')
    replicate_parser.add_argument('--dst', required=True, help='Destination distribution (e.g., noble)')
    replicate_parser.add_argument('--component', help='Component (defaults to config)', default=None)
    replicate_parser.add_argument('--arch', help='Architecture (defaults to config architectures)', default=None)
    replicate_parser.add_argument('-y', '--yes', action='store_true', help='Skip confirmation prompt (for CI/CD)')


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
        config = load_config(args, 'deb')
        
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

        # Handle replicate command
        if args.command == 'replicate':
            print()
            print(Colors.bold("Configuration:"))

            backend_info = repo.storage.get_info()
            for key, value in backend_info.items():
                print(f"  {key:<11}: {value}")

            print(f"  Action:       {Colors.bold('REPLICATE')}")
            print(f"  Source:       {args.src}")
            print(f"  Destination:  {args.dst}")
            print(f"  Packages:     {len(args.package_names)}")
            for pkg in args.package_names:
                print(f"    • {pkg}")
            print()

            # Confirm operation
            if not args.yes:
                response = input(Colors.bold("Continue? (yes/no): "))
                if response.lower() != "yes":
                    print(Colors.warning("Cancelled"))
                    return 0

            repo.replicate_distribution(
                args.src,
                args.dst,
                args.package_names,
                component=args.component,
                arch=args.arch
            )
            return 0

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
