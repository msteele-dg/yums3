#!/usr/bin/env python3
"""
Regenerate SQLite databases from XML metadata
This fixes the package count mismatch issue
"""

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from sqlite_metadata import SQLiteMetadataManager
except ImportError:
    print("ERROR: sqlite_metadata.py not found")
    sys.exit(1)

def regenerate_databases(repodata_dir):
    """Regenerate SQLite databases from XML files"""
    print(f"Regenerating SQLite databases in {repodata_dir}...")
    
    # Parse repomd.xml to find XML files
    repomd_path = os.path.join(repodata_dir, 'repomd.xml')
    if not os.path.exists(repomd_path):
        print(f"ERROR: repomd.xml not found at {repomd_path}")
        return False
    
    tree = ET.parse(repomd_path)
    root = tree.getroot()
    
    # Find XML metadata files
    xml_files = {}
    for data in root.findall('data'):
        data_type = data.get('type')
        if data_type in ['primary', 'filelists', 'other']:
            location = data.find('location')
            if location is not None:
                href = location.get('href')
                filename = os.path.basename(href)
                filepath = os.path.join(repodata_dir, filename)
                if os.path.exists(filepath):
                    xml_files[data_type] = filepath
                    print(f"  Found {data_type}: {filename}")
    
    if 'primary' not in xml_files:
        print("ERROR: primary.xml.gz not found")
        return False
    
    # Delete old SQLite databases
    print("\n  Removing old SQLite databases...")
    removed_count = 0
    for filename in os.listdir(repodata_dir):
        if filename.endswith('.sqlite') or filename.endswith('.sqlite.bz2'):
            filepath = os.path.join(repodata_dir, filename)
            os.remove(filepath)
            removed_count += 1
            print(f"    Removed: {filename}")
    
    if removed_count == 0:
        print("    No old databases found")
    
    # Remove old database entries from repomd.xml
    print("\n  Removing old database entries from repomd.xml...")
    removed_entries = 0
    for data in list(root.findall('data')):
        if data.get('type', '').endswith('_db'):
            root.remove(data)
            removed_entries += 1
    
    if removed_entries > 0:
        print(f"    Removed {removed_entries} database entries")
    else:
        print("    No old entries found")
    
    # Create new SQLite databases
    print("\n  Creating new SQLite databases...")
    sqlite_mgr = SQLiteMetadataManager(repodata_dir)
    
    try:
        db_files = sqlite_mgr.create_all_databases(xml_files)
        print(f"    Created {len(db_files)} database(s)")
        
        # Compress databases
        compressed_dbs = {}
        for db_type, db_path in db_files.items():
            compressed_path = sqlite_mgr.compress_sqlite(db_path)
            compressed_dbs[db_type] = compressed_path
            print(f"    Compressed: {os.path.basename(compressed_path)}")
        
        # Add database entries to repomd.xml
        print("\n  Adding database entries to repomd.xml...")
        from yums3 import YumRepo
        import hashlib
        import bz2
        from datetime import datetime
        
        for db_type, db_path in compressed_dbs.items():
            filename = os.path.basename(db_path)
            
            # Calculate checksums
            with open(db_path, 'rb') as f:
                compressed_data = f.read()
                checksum = hashlib.sha256(compressed_data).hexdigest()
                size = len(compressed_data)
            
            with bz2.open(db_path, 'rb') as f:
                uncompressed_data = f.read()
                open_checksum = hashlib.sha256(uncompressed_data).hexdigest()
                open_size = len(uncompressed_data)
            
            # Rename file to match checksum
            new_filename = f"{checksum}-{db_type}.sqlite.bz2"
            new_path = os.path.join(repodata_dir, new_filename)
            os.rename(db_path, new_path)
            
            # Create data element
            data_elem = ET.SubElement(root, 'data', {'type': db_type})
            
            checksum_elem = ET.SubElement(data_elem, 'checksum', {'type': 'sha256'})
            checksum_elem.text = checksum
            
            open_checksum_elem = ET.SubElement(data_elem, 'open-checksum', {'type': 'sha256'})
            open_checksum_elem.text = open_checksum
            
            location_elem = ET.SubElement(data_elem, 'location', {'href': f'repodata/{new_filename}'})
            
            timestamp_elem = ET.SubElement(data_elem, 'timestamp')
            timestamp_elem.text = str(int(datetime.now().timestamp()))
            
            size_elem = ET.SubElement(data_elem, 'size')
            size_elem.text = str(size)
            
            open_size_elem = ET.SubElement(data_elem, 'open-size')
            open_size_elem.text = str(open_size)
            
            database_version_elem = ET.SubElement(data_elem, 'database_version')
            database_version_elem.text = '10'
            
            print(f"    Added {db_type} entry")
        
        # Update revision
        revision_elem = root.find('revision')
        if revision_elem is not None:
            revision_elem.text = str(int(datetime.now().timestamp()))
        
        # Write updated repomd.xml with pretty formatting
        import xml.dom.minidom as minidom
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
            pass
        
        with open(repomd_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        
        print("\n✓ Successfully regenerated SQLite databases")
        return True
        
    except Exception as e:
        print(f"\n✗ Failed to regenerate databases: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    repo_base = os.path.expanduser("~/yum-repo")
    
    if not os.path.exists(repo_base):
        print(f"ERROR: Repository not found at {repo_base}")
        return 1
    
    print(f"Scanning {repo_base} for repositories...\n")
    
    success_count = 0
    for root, dirs, files in os.walk(repo_base):
        if 'repomd.xml' in files:
            repodata_dir = root
            print(f"Found repository: {repodata_dir}\n")
            
            if regenerate_databases(repodata_dir):
                success_count += 1
            
            print()
    
    if success_count > 0:
        print(f"✓ Successfully regenerated {success_count} repository/repositories")
        return 0
    else:
        print("✗ No repositories were regenerated")
        return 1

if __name__ == '__main__':
    sys.exit(main())
