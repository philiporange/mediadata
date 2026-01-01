"""
Mediadata - A media metadata management system based on torrent files.

This package provides tools for:
- Processing torrent files and extracting metadata
- Managing media libraries with immutable file organization
- Reading and writing XML NFO files compatible with Kodi/Jellyfin
- Gathering metadata from various sources (TMDB, IMDB, Audible, etc.)
"""

from .utils import (
    read_torrent_file,
    calculate_info_hash,
    scan_torrent_files,
    get_torrent_info,
    read_nfo_file,
    write_nfo_file,
    create_library_structure,
    find_nfo_files,
    extract_metadata_source,
    is_media_file
)

from .scan import (
    TorrentScanner,
    FileMatch,
    TorrentMatch,
    create_scan_report
)

from .organize import (
    LibraryOrganizer,
    OrganizeAction,
    CollisionStrategy,
    OrganizeOperation,
    OrganizeResult,
    create_organize_report,
    organize_torrents_cli
)

from .metadata import (
    MediaType,
    IdentificationSource,
    MediaIdentification,
    MetadataResult,
    TMDBClient,
    MediaIdentifier,
    MetadataProcessor,
    process_torrents_metadata
)

from .mediadata import (
    MediaData,
    ProcessingStats,
    process_media
)

__version__ = '0.1.0'
__all__ = [
    # Core utilities
    'read_torrent_file',
    'calculate_info_hash', 
    'scan_torrent_files',
    'get_torrent_info',
    'read_nfo_file',
    'write_nfo_file',
    'create_library_structure',
    'find_nfo_files',
    'extract_metadata_source',
    'is_media_file',
    
    # Scanning
    'TorrentScanner',
    'FileMatch',
    'TorrentMatch',
    'create_scan_report',
    
    # Organization
    'LibraryOrganizer',
    'OrganizeAction',
    'CollisionStrategy',
    'OrganizeOperation',
    'OrganizeResult',
    'create_organize_report',
    'organize_torrents_cli',
    
    # Metadata
    'MediaType',
    'IdentificationSource',
    'MediaIdentification',
    'MetadataResult',
    'TMDBClient',
    'MediaIdentifier',
    'MetadataProcessor',
    'process_torrents_metadata',

    # Main interface
    'MediaData',
    'ProcessingStats',
    'process_media'
]