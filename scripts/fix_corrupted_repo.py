#!/usr/bin/env python3
"""
Script to fix corrupted YUM repository metadata
Removes duplicate SQLite database entries and cleans up old database files
"""

import os
import sys
import xml.etree.ElementTree as ET
import re
from pathlib import Path

def fix_repomd_xml(repomd_path):
    """Remove duplicate database entries from repomd.xml"""
    print(f"Fixing {repomd_path}...")
    
    # Parse repomd.xml
    tree = ET.parse(repomd_path)
    root = tree.getroot()
    
    # Track seen data types
    seen_types = set()
    duplicates_removed = 0
    
    # Remove duplicates (keep first occurrence)
    for data in list(root.findall('data')):
        data_type = data.get('type')
        if data_type:
            if data_type in seen_types:
                root.remove(data)
                duplicates_removed += 1
                print(f"  Removed duplicate: {data_type}")
            else:
                seen_types.add(data_type)
    
    if duplicates_removed > 0:
        # Write fixed repomd.xml with proper formatting
        import xml.dom.minidom as minidom
        
        # Convert to string
        import io
        output = io.BytesIO()
        tree.write(output, encoding='utf-8', xml_declaration=True)
        xml_content = output.getvalue().decode('utf-8')
        
        # Pretty print
        try:
            dom = minidom.parseString(xml_content)
            pretty_xml = dom.toprettyxml(indent='  ', encoding='utf-8').decode('utf-8')
            
            # Remove extra blank lines
            lines = [line for line in pretty_xml.split('\n') if line.strip()]
            xml_content = '\n'.join(lines) + '\n'
        except:
            pass  # If pretty print fails, use original
        
        with open(repomd_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        
        print(f"  ✓ Removed {duplicates_removed} duplicate entries")
        return True
    else:
        print("  ✓ No duplicates found")
        return False

def clean_old_databases(repodata_dir, repomd_path):
    """Remove SQLite database files not referenced in repomd.xml"""
    print(f"\nCleaning old database files in {repodata_dir}...")
    
    # Parse repomd.xml to get referenced files
    tree = ET.parse(repomd_path)
    root = tree.getroot()
    
    referenced_files = set()
    for data in root.findall('data'):
        location = data.find('location')
        if location is not None:
            href = location.get('href')
            if href:
                filename = os.path.basename(href)
                referenced_files.add(filename)
    
    # Find all database files
    db_files = []
    for filename in os.listdir(repodata_dir):
        if filename.endswith('.sqlite.bz2'):
            db_files.append(filename)
    
    # Remove unreferenced database files
    removed = 0
    for db_file in db_files:
        if db_file not in referenced_files:
            db_path = os.path.join(repodata_dir, db_file)
            os.remove(db_path)
            print(f"  Removed: {db_file}")
            removed += 1
    
    if removed > 0:
        print(f"  ✓ Removed {removed} unreferenced database file(s)")
    else:
        print("  ✓ No unreferenced files found")

def main():
    # Find all repodata directories
    repo_base = os.path.expanduser("~/yum-repo")
    
    if not os.path.exists(repo_base):
        print(f"ERROR: Repository not found at {repo_base}")
        return 1
    
    print(f"Scanning {repo_base} for repositories...\n")
    
    fixed_count = 0
    for root, dirs, files in os.walk(repo_base):
        if 'repomd.xml' in files:
            repomd_path = os.path.join(root, 'repomd.xml')
            repodata_dir = root
            
            print(f"Found repository: {repodata_dir}")
            
            # Fix repomd.xml
            if fix_repomd_xml(repomd_path):
                fixed_count += 1
            
            # Clean old database files
            clean_old_databases(repodata_dir, repomd_path)
            
            print()
    
    if fixed_count > 0:
        print(f"✓ Fixed {fixed_count} repository/repositories")
    else:
        print("✓ All repositories are clean")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
