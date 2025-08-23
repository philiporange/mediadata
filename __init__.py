"""
MediaData - Media metadata management system.

Main imports for the MediaData system:
- MediaData: Main interface class
- ProcessingStats: Statistics from processing runs
- process_media_directory: Convenience function
"""

from .mediadata import MediaData, ProcessingStats, process_media_directory

# Also expose common classes from src modules
from src import (
    # Core utilities
    read_torrent_file,
    calculate_info_hash, 
    scan_torrent_files,
    get_torrent_info,
    
    # Scanning
    TorrentScanner,
    TorrentMatch,
    FileMatch,
    
    # Organization
    LibraryOrganizer,
    OrganizeAction,
    CollisionStrategy,
    
    # Metadata
    MediaType,
    TMDBClient,
    MediaIdentifier,
    MetadataProcessor
)

__version__ = '0.1.0'
__all__ = [
    # Main interface
    'MediaData',
    'ProcessingStats', 
    'process_media_directory',
    
    # Common utilities and classes
    'read_torrent_file',
    'calculate_info_hash',
    'scan_torrent_files', 
    'get_torrent_info',
    'TorrentScanner',
    'TorrentMatch',
    'FileMatch',
    'LibraryOrganizer',
    'OrganizeAction',
    'CollisionStrategy',
    'MediaType',
    'TMDBClient',
    'MediaIdentifier',
    'MetadataProcessor'
]