"""
Default configuration settings for mediadata.

Uses ~/.mediadata as the base directory for all settings and data storage.
These defaults can be overridden via environment variables or .env file.

Default paths:
- Archive: ~/.mediadata/archive
- Torrent watch directory: ~/.mediadata/torrents  
- Temp directory: ~/.mediadata/temp
"""

import os
from pathlib import Path
from typing import Dict, List

# Base directories - use ~/.mediadata as the default base
_DEFAULT_BASE_DIR = Path.home() / ".mediadata"
DEFAULT_ARCHIVE_PATH = _DEFAULT_BASE_DIR / "archive"
DEFAULT_TORRENT_WATCH_DIR = _DEFAULT_BASE_DIR / "torrents"
DEFAULT_TEMP_DIR = _DEFAULT_BASE_DIR / "temp"

# Metadata sources and their priority (higher number = higher priority)
METADATA_SOURCE_PRIORITY = {
    'override': 100,
    'manual': 90,
    'interop': 80,
    'tmdb': 70,
    'tvdb': 70,
    'imdb': 70,
    'audible': 70,
    'openlibrary': 70,
    'goodreads': 70,
    'scanner': 10
}

# Media file extensions by category
MEDIA_EXTENSIONS = {
    'video': ['.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts'],
    'audio': ['.mp3', '.flac', '.m4a', '.aac', '.ogg', '.wav', '.wma', '.m4b', '.opus'],
    'book': ['.epub', '.pdf', '.mobi', '.azw3', '.djvu', '.fb2', '.lit', '.pdb']
}

# NFO interoperability filenames
INTEROP_NFO_NAMES = {
    'movie': 'movie.nfo',
    'tvshow': 'tvshow.nfo',
    'season': 'season.nfo',
    'episode': 'episode.nfo',
    'artist': 'artist.nfo', 
    'album': 'album.nfo',
    'book': 'book.nfo',
    'audiobook': 'audiobook.nfo'
}

# Art file names
ART_FILENAMES = {
    'poster': 'poster.jpg',
    'fanart': 'fanart.jpg',
    'banner': 'banner.jpg',
    'cover': 'cover.jpg',
    'logo': 'logo.png',
    'disc': 'disc.png',
    'thumbnail': 'thumb.jpg'
}


class Config:
    """Configuration class that loads settings from environment and defaults."""
    
    def __init__(self):
        self.archive_path = Path(os.environ.get('MEDIADATA_ARCHIVE', DEFAULT_ARCHIVE_PATH))
        self.torrent_watch_dir = Path(os.environ.get('MEDIADATA_TORRENT_WATCH_DIR', DEFAULT_TORRENT_WATCH_DIR))
        self.temp_dir = Path(os.environ.get('MEDIADATA_TEMP_DIR', DEFAULT_TEMP_DIR))
        
        # Source priority (can be overridden)
        self.source_priority = METADATA_SOURCE_PRIORITY.copy()
        
        # Media extensions
        self.media_extensions = MEDIA_EXTENSIONS.copy()
        
        # Create directories if they don't exist
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create necessary directories if they don't exist."""
        for path in [self.archive_path, self.torrent_watch_dir, self.temp_dir]:
            path.mkdir(parents=True, exist_ok=True)
    
    def get_torrent_dir(self, info_hash: str) -> Path:
        """Get the directory path for a specific torrent."""
        return self.archive_path / info_hash.lower()
    
    def get_data_dir(self, info_hash: str) -> Path:
        """Get the data directory for a specific torrent."""
        return self.get_torrent_dir(info_hash) / 'data'
    
    def get_metadata_dir(self, info_hash: str) -> Path:
        """Get the metadata directory for a specific torrent."""
        return self.get_torrent_dir(info_hash) / 'metadata'
    
    def is_media_file(self, file_path: Path) -> bool:
        """Check if a file is a media file based on extension."""
        ext = file_path.suffix.lower()
        for extensions in self.media_extensions.values():
            if ext in extensions:
                return True
        return False
    
    def get_media_type(self, file_path: Path) -> str:
        """Get the media type category for a file."""
        ext = file_path.suffix.lower()
        for media_type, extensions in self.media_extensions.items():
            if ext in extensions:
                return media_type
        return 'unknown'


# Global config instance
config = Config()