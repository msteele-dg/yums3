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
import re

from core.config import load_config, config_command
from core.yum import YumRepo
from core import Colors

try:
    from lxml import etree as ET
except ImportError:
    print("ERROR: lxml is not installed. Install it with: pip install lxml")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Efficient YUM repository manager for S3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    add_parser.add_argument('rpm_files', nargs='+', help='RPM file(s) to add')
    add_parser.add_argument('-y', '--yes', action='store_true', help='Skip confirmation prompt (for CI/CD)')
    add_parser.add_argument('--no-validate', action='store_true', help='Skip post-operation validation')
    
    # Remove subcommand
    remove_parser = subparsers.add_parser('remove', help='Remove packages from repository')
    remove_parser.add_argument('rpm_files', nargs='+', help='RPM filename(s) to remove')
    remove_parser.add_argument('-y', '--yes', action='store_true', help='Skip confirmation prompt (for CI/CD)')
    remove_parser.add_argument('--no-validate', action='store_true', help='Skip post-operation validation')
    
    # Validate subcommand
    validate_parser = subparsers.add_parser('validate', help='Validate repository')
    validate_parser.add_argument('repo_path', help='Repository path (e.g., el9/x86_64)')

    # Replicate subcommand
    replicate_parser = subparsers.add_parser('replicate', help='Replicate packages between distros')
    replicate_parser.add_argument('package_names', nargs='+', help='Package name(s) to replicate')
    replicate_parser.add_argument('--src', required=True, help='Source distro (e.g., el9)')
    replicate_parser.add_argument('--dst', required=True, help='Destination distro (e.g., el10)')
    replicate_parser.add_argument('--arch', help='Architecture (defaults to x86_64)', default=None)
    replicate_parser.add_argument('-y', '--yes', action='store_true', help='Skip confirmation prompt (for CI/CD)')

    # Config subcommand
    config_parser = subparsers.add_parser('config', help='Manage configuration')
    config_parser.add_argument('key', nargs='?', help='Config key (dot notation)')
    config_parser.add_argument('value', nargs='?', help='Config value (if setting)')
    config_parser.add_argument('--list', action='store_true', help='List all config values')
    config_parser.add_argument('--unset', metavar='KEY', help='Remove a config key')
    config_parser.add_argument('--validate', dest='validate_config', action='store_true', help='Validate configuration')
    config_parser.add_argument('--file', help='Use specific config file')
    config_parser.add_argument('--global', dest='global_config', action='store_true', help='Use global config (~/.yums3.conf)')
    config_parser.add_argument('--local', action='store_true', help='Use local config (./yums3.conf)')
    config_parser.add_argument('--system', action='store_true', help='Use system config (/etc/yums3.conf)')
    
    args = parser.parse_args()
    
    # Handle config command
    if args.command == 'config':
        return config_command(args, 'rpm')
    
    # Load configuration
    try:
        config = load_config(args, 'rpm')
        print(config)
               
        # Initialize repository manager
        repo = YumRepo(config)
        print(repo)
        
        # Handle validate command
        if args.command == 'validate':
            # Parse el_version/arch
            parts = args.repo_path.split('/')
            if len(parts) != 2:
                print(Colors.error("✗ Error: Invalid format. Use: el_version/arch (e.g., el9/x86_64)"))
                return 1

            el_version, arch = parts
            success = repo.validate_repository(el_version, arch)
            return 0 if success else 1

        # Handle replicate command
        if args.command == 'replicate':
            print()
            print(Colors.bold("Configuration:"))

            backend_info = repo.storage.get_info()
            for key, value in backend_info.items():
                print(f"  {key}:  {value}")

            print(f"  Action:       {Colors.bold('REPLICATE')}")
            print(f"  Source:       {args.src}")
            print(f"  Destination:  {args.dst}")
            print(f"  Architecture: {args.arch or 'x86_64'}")
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

            repo.replicate_distro(
                args.src,
                args.dst,
                args.package_names,
                arch=args.arch
            )
            return 0
        
        # Determine operation details based on command
        if args.command == 'remove':
            rpm_filenames = [os.path.basename(f) for f in args.rpm_files]
            arch, el_version = repo._detect_from_filename(rpm_filenames[0])
        elif args.command == 'add':
            rpm_filenames = args.rpm_files
            arch, el_version = repo._detect_from_rpm(args.rpm_files[0])
        else:
            print(Colors.error(f"✗ Unknown command: {args.command}"))
            return 1
        action = args.command.upper()
        target = f"{repo.storage.get_url()}/{el_version}/{arch}"
        
        # Show confirmation
        print()
        print(Colors.bold("Configuration:"))
        
        # Get backend info and display it
        backend_info = repo.storage.get_info()
        for key, value in backend_info.items():
            print(f"  {key}:  {value}")
        
        print(f"  Target:       {target}")
        print(f"  Action:       {Colors.bold(action)}")
        print(f"  Packages:     {len(args.rpm_files)}")
        for f in args.rpm_files:
            print(f"    • {os.path.basename(f)}")
        print()
        
        # Confirm operation
        if not args.yes:
            response = input(Colors.bold("Continue? (yes/no): "))
            if response.lower() != "yes":
                print(Colors.warning("Cancelled"))
                return 0
        
        # Execute operation
        if args.command == 'remove':
            repo.remove_packages(rpm_filenames)
        elif args.command == 'add':
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
