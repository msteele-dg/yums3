#!/usr/bin/env python3
"""
SQLite metadata management for YUM repositories

This module handles creating and updating SQLite database files
for YUM repository metadata (primary_db, filelists_db, other_db).
"""

import sqlite3
import gzip
import xml.etree.ElementTree as ET
import os
import hashlib
from datetime import datetime


class SQLiteMetadataManager:
    """Manages SQLite database files for YUM repository metadata"""
    
    # Namespaces for XML parsing
    NS = {
        'common': 'http://linux.duke.edu/metadata/common',
        'rpm': 'http://linux.duke.edu/metadata/rpm',
        'filelists': 'http://linux.duke.edu/metadata/filelists',
        'otherdata': 'http://linux.duke.edu/metadata/other'
    }
    
    def __init__(self, repodata_dir):
        """
        Initialize SQLite metadata manager
        
        Args:
            repodata_dir: Path to repodata directory
        """
        self.repodata_dir = repodata_dir
    
    def create_primary_db(self, primary_xml_gz):
        """
        Create primary.sqlite database from primary.xml.gz
        
        Args:
            primary_xml_gz: Path to primary.xml.gz file
        
        Returns:
            str: Path to created primary.sqlite file
        """
        db_path = os.path.join(self.repodata_dir, 'primary.sqlite')
        
        # Remove existing database
        if os.path.exists(db_path):
            os.remove(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create schema
        cursor.execute('''
            CREATE TABLE db_info (
                dbversion INTEGER,
                checksum TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE packages (
                pkgKey INTEGER PRIMARY KEY,
                pkgId TEXT,
                name TEXT,
                arch TEXT,
                version TEXT,
                epoch TEXT,
                release TEXT,
                summary TEXT,
                description TEXT,
                url TEXT,
                time_file INTEGER,
                time_build INTEGER,
                rpm_license TEXT,
                rpm_vendor TEXT,
                rpm_group TEXT,
                rpm_buildhost TEXT,
                rpm_sourcerpm TEXT,
                rpm_header_start INTEGER,
                rpm_header_end INTEGER,
                rpm_packager TEXT,
                size_package INTEGER,
                size_installed INTEGER,
                size_archive INTEGER,
                location_href TEXT,
                location_base TEXT,
                checksum_type TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE provides (
                pkgKey INTEGER,
                name TEXT,
                flags TEXT,
                epoch TEXT,
                version TEXT,
                release TEXT,
                FOREIGN KEY(pkgKey) REFERENCES packages(pkgKey)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE requires (
                pkgKey INTEGER,
                name TEXT,
                flags TEXT,
                epoch TEXT,
                version TEXT,
                release TEXT,
                pre BOOLEAN,
                FOREIGN KEY(pkgKey) REFERENCES packages(pkgKey)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE conflicts (
                pkgKey INTEGER,
                name TEXT,
                flags TEXT,
                epoch TEXT,
                version TEXT,
                release TEXT,
                FOREIGN KEY(pkgKey) REFERENCES packages(pkgKey)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE obsoletes (
                pkgKey INTEGER,
                name TEXT,
                flags TEXT,
                epoch TEXT,
                version TEXT,
                release TEXT,
                FOREIGN KEY(pkgKey) REFERENCES packages(pkgKey)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE files (
                pkgKey INTEGER,
                name TEXT,
                type TEXT,
                FOREIGN KEY(pkgKey) REFERENCES packages(pkgKey)
            )
        ''')
        
        # Insert db version
        cursor.execute('INSERT INTO db_info VALUES (10, ?)', ('',))
        
        # Parse XML and populate database
        with gzip.open(primary_xml_gz, 'rt', encoding='utf-8') as f:
            tree = ET.parse(f)
            root = tree.getroot()
        
        pkgKey = 1
        for package in root.findall('common:package', self.NS):
            # Extract package info
            name_elem = package.find('common:name', self.NS)
            arch_elem = package.find('common:arch', self.NS)
            version_elem = package.find('common:version', self.NS)
            checksum_elem = package.find('common:checksum', self.NS)
            summary_elem = package.find('common:summary', self.NS)
            description_elem = package.find('common:description', self.NS)
            packager_elem = package.find('common:packager', self.NS)
            url_elem = package.find('common:url', self.NS)
            time_elem = package.find('common:time', self.NS)
            size_elem = package.find('common:size', self.NS)
            location_elem = package.find('common:location', self.NS)
            format_elem = package.find('common:format', self.NS)
            
            # Insert package
            cursor.execute('''
                INSERT INTO packages (
                    pkgKey, pkgId, name, arch, version, epoch, release,
                    summary, description, url, time_file, time_build,
                    rpm_license, rpm_vendor, rpm_group, rpm_buildhost,
                    rpm_sourcerpm, rpm_header_start, rpm_header_end,
                    rpm_packager, size_package, size_installed, size_archive,
                    location_href, checksum_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                pkgKey,
                checksum_elem.text if checksum_elem is not None else '',
                name_elem.text if name_elem is not None else '',
                arch_elem.text if arch_elem is not None else '',
                version_elem.get('ver') if version_elem is not None else '',
                version_elem.get('epoch') if version_elem is not None else '0',
                version_elem.get('rel') if version_elem is not None else '',
                summary_elem.text if summary_elem is not None else '',
                description_elem.text if description_elem is not None else '',
                url_elem.text if url_elem is not None else '',
                int(time_elem.get('file')) if time_elem is not None else 0,
                int(time_elem.get('build')) if time_elem is not None else 0,
                format_elem.find('rpm:license', self.NS).text if format_elem is not None and format_elem.find('rpm:license', self.NS) is not None else '',
                format_elem.find('rpm:vendor', self.NS).text if format_elem is not None and format_elem.find('rpm:vendor', self.NS) is not None else '',
                format_elem.find('rpm:group', self.NS).text if format_elem is not None and format_elem.find('rpm:group', self.NS) is not None else '',
                format_elem.find('rpm:buildhost', self.NS).text if format_elem is not None and format_elem.find('rpm:buildhost', self.NS) is not None else '',
                format_elem.find('rpm:sourcerpm', self.NS).text if format_elem is not None and format_elem.find('rpm:sourcerpm', self.NS) is not None else '',
                int(format_elem.find('rpm:header-range', self.NS).get('start')) if format_elem is not None and format_elem.find('rpm:header-range', self.NS) is not None else 0,
                int(format_elem.find('rpm:header-range', self.NS).get('end')) if format_elem is not None and format_elem.find('rpm:header-range', self.NS) is not None else 0,
                packager_elem.text if packager_elem is not None else '',
                int(size_elem.get('package')) if size_elem is not None else 0,
                int(size_elem.get('installed')) if size_elem is not None else 0,
                int(size_elem.get('archive')) if size_elem is not None else 0,
                location_elem.get('href') if location_elem is not None else '',
                checksum_elem.get('type') if checksum_elem is not None else 'sha256'
            ))
            
            # Insert provides, requires, conflicts, obsoletes
            if format_elem is not None:
                for provides in format_elem.findall('rpm:provides/rpm:entry', self.NS):
                    cursor.execute('''
                        INSERT INTO provides (pkgKey, name, flags, epoch, version, release)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        pkgKey,
                        provides.get('name', ''),
                        provides.get('flags', ''),
                        provides.get('epoch', ''),
                        provides.get('ver', ''),
                        provides.get('rel', '')
                    ))
                
                for requires in format_elem.findall('rpm:requires/rpm:entry', self.NS):
                    cursor.execute('''
                        INSERT INTO requires (pkgKey, name, flags, epoch, version, release, pre)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        pkgKey,
                        requires.get('name', ''),
                        requires.get('flags', ''),
                        requires.get('epoch', ''),
                        requires.get('ver', ''),
                        requires.get('rel', ''),
                        requires.get('pre') == '1'
                    ))
                
                for conflicts in format_elem.findall('rpm:conflicts/rpm:entry', self.NS):
                    cursor.execute('''
                        INSERT INTO conflicts (pkgKey, name, flags, epoch, version, release)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        pkgKey,
                        conflicts.get('name', ''),
                        conflicts.get('flags', ''),
                        conflicts.get('epoch', ''),
                        conflicts.get('ver', ''),
                        conflicts.get('rel', '')
                    ))
                
                for obsoletes in format_elem.findall('rpm:obsoletes/rpm:entry', self.NS):
                    cursor.execute('''
                        INSERT INTO obsoletes (pkgKey, name, flags, epoch, version, release)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        pkgKey,
                        obsoletes.get('name', ''),
                        obsoletes.get('flags', ''),
                        obsoletes.get('epoch', ''),
                        obsoletes.get('ver', ''),
                        obsoletes.get('rel', '')
                    ))
            
            pkgKey += 1
        
        # Create indexes
        cursor.execute('CREATE INDEX packagename ON packages (name)')
        cursor.execute('CREATE INDEX packageId ON packages (pkgId)')
        cursor.execute('CREATE INDEX providesname ON provides (name)')
        cursor.execute('CREATE INDEX requiresname ON requires (name)')
        
        conn.commit()
        conn.close()
        
        return db_path
    
    def create_filelists_db(self, filelists_xml_gz):
        """
        Create filelists.sqlite database from filelists.xml.gz
        
        Args:
            filelists_xml_gz: Path to filelists.xml.gz file
        
        Returns:
            str: Path to created filelists.sqlite file
        """
        db_path = os.path.join(self.repodata_dir, 'filelists.sqlite')
        
        if os.path.exists(db_path):
            os.remove(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create schema
        cursor.execute('''
            CREATE TABLE db_info (
                dbversion INTEGER,
                checksum TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE packages (
                pkgKey INTEGER PRIMARY KEY,
                pkgId TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE filelist (
                pkgKey INTEGER,
                dirname TEXT,
                filenames TEXT,
                filetypes TEXT,
                FOREIGN KEY(pkgKey) REFERENCES packages(pkgKey)
            )
        ''')
        
        cursor.execute('INSERT INTO db_info VALUES (10, ?)', ('',))
        
        # Parse XML
        with gzip.open(filelists_xml_gz, 'rt', encoding='utf-8') as f:
            tree = ET.parse(f)
            root = tree.getroot()
        
        pkgKey = 1
        for package in root.findall('filelists:package', self.NS):
            pkgid = package.get('pkgid')
            
            cursor.execute('INSERT INTO packages (pkgKey, pkgId) VALUES (?, ?)', (pkgKey, pkgid))
            
            # Group files by directory
            files_by_dir = {}
            for file_elem in package.findall('filelists:file', self.NS):
                filepath = file_elem.text
                filetype = file_elem.get('type', '')
                
                dirname = os.path.dirname(filepath) or '/'
                filename = os.path.basename(filepath)
                
                if dirname not in files_by_dir:
                    files_by_dir[dirname] = {'names': [], 'types': []}
                
                files_by_dir[dirname]['names'].append(filename)
                files_by_dir[dirname]['types'].append(filetype)
            
            # Insert grouped files
            for dirname, files in files_by_dir.items():
                cursor.execute('''
                    INSERT INTO filelist (pkgKey, dirname, filenames, filetypes)
                    VALUES (?, ?, ?, ?)
                ''', (
                    pkgKey,
                    dirname,
                    '/'.join(files['names']),
                    '/'.join(files['types'])
                ))
            
            pkgKey += 1
        
        cursor.execute('CREATE INDEX keyfile ON filelist (pkgKey)')
        cursor.execute('CREATE INDEX pkgId ON packages (pkgId)')
        
        conn.commit()
        conn.close()
        
        return db_path
    
    def create_other_db(self, other_xml_gz):
        """
        Create other.sqlite database from other.xml.gz
        
        Args:
            other_xml_gz: Path to other.xml.gz file
        
        Returns:
            str: Path to created other.sqlite file
        """
        db_path = os.path.join(self.repodata_dir, 'other.sqlite')
        
        if os.path.exists(db_path):
            os.remove(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create schema
        cursor.execute('''
            CREATE TABLE db_info (
                dbversion INTEGER,
                checksum TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE packages (
                pkgKey INTEGER PRIMARY KEY,
                pkgId TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE changelog (
                pkgKey INTEGER,
                author TEXT,
                date INTEGER,
                changelog TEXT,
                FOREIGN KEY(pkgKey) REFERENCES packages(pkgKey)
            )
        ''')
        
        cursor.execute('INSERT INTO db_info VALUES (10, ?)', ('',))
        
        # Parse XML
        with gzip.open(other_xml_gz, 'rt', encoding='utf-8') as f:
            tree = ET.parse(f)
            root = tree.getroot()
        
        pkgKey = 1
        for package in root.findall('otherdata:package', self.NS):
            pkgid = package.get('pkgid')
            
            cursor.execute('INSERT INTO packages (pkgKey, pkgId) VALUES (?, ?)', (pkgKey, pkgid))
            
            for changelog in package.findall('otherdata:changelog', self.NS):
                cursor.execute('''
                    INSERT INTO changelog (pkgKey, author, date, changelog)
                    VALUES (?, ?, ?, ?)
                ''', (
                    pkgKey,
                    changelog.get('author', ''),
                    int(changelog.get('date', '0')),
                    changelog.text or ''
                ))
            
            pkgKey += 1
        
        cursor.execute('CREATE INDEX keychange ON changelog (pkgKey)')
        cursor.execute('CREATE INDEX pkgId ON packages (pkgId)')
        
        conn.commit()
        conn.close()
        
        return db_path
    
    def create_all_databases(self, metadata_files):
        """
        Create all SQLite databases from XML files
        
        Args:
            metadata_files: Dict with keys 'primary', 'filelists', 'other'
                           mapping to XML.gz file paths
        
        Returns:
            dict: Paths to created database files
        """
        db_files = {}
        
        if 'primary' in metadata_files:
            db_files['primary_db'] = self.create_primary_db(metadata_files['primary'])
        
        if 'filelists' in metadata_files:
            db_files['filelists_db'] = self.create_filelists_db(metadata_files['filelists'])
        
        if 'other' in metadata_files:
            db_files['other_db'] = self.create_other_db(metadata_files['other'])
        
        return db_files
    
    @staticmethod
    def compress_sqlite(db_path):
        """
        Compress SQLite database with bzip2
        
        Args:
            db_path: Path to .sqlite file
        
        Returns:
            str: Path to compressed .sqlite.bz2 file
        """
        import bz2
        
        bz2_path = db_path + '.bz2'
        
        with open(db_path, 'rb') as f_in:
            with bz2.open(bz2_path, 'wb') as f_out:
                f_out.write(f_in.read())
        
        # Remove uncompressed file
        os.remove(db_path)
        
        return bz2_path
