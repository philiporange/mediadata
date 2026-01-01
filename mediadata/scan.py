"""
Enhanced scanning using torrent-scanner backend.
This module replaces the original scan implementation with torrent-scanner integration,
providing persistent database storage and improved torrent matching capabilities.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import logging

try:
    from torrent_scanner import TorrentScanner as TSScanner, Torrent, Match, TorrentFile
    TORRENT_SCANNER_AVAILABLE = True
except ImportError as e:
    # For testing purposes, create mock classes
    print(f"Warning: torrent_scanner not available ({e}), using mock implementation for testing")
    
    class TSScanner:
        def __init__(self, **kwargs):
            pass
        def index_torrents(self, paths):
            return {'new': 0, 'updated': 0}
        def find_matches(self, paths):
            return {}
        def get_torrent_info(self, info_hash):
            return None
        def get_data_locations(self, info_hash):
            return []
        def list_torrents(self, filter_type='all'):
            return []
        def cleanup_missing_torrents(self):
            return 0
        def get_statistics(self):
            return {'total_torrents': 0, 'matched_torrents': 0, 'total_size_bytes': 0}
    
    class Torrent:
        def __init__(self):
            self.is_multi = False
            self.files = []
            self.name = ""
            self.total_length = 0
            self.info_hash = ""
            self.torrent_path = ""
    
    class Match:
        def __init__(self):
            self.data_path = ""
    
    class TorrentFile:
        def __init__(self):
            self.path = ""
            self.size = 0
    
    TORRENT_SCANNER_AVAILABLE = False


@dataclass
class FileMatch:
    """Represents a matched file within a torrent."""
    torrent_path: str
    filesystem_path: Path
    size: int
    verified: Optional[bool] = None


@dataclass
class TorrentMatch:
    """Compatibility wrapper for torrent-scanner matches."""
    torrent_file: Path
    info_hash: str
    name: str
    root_path: Optional[Path]
    files: List[FileMatch]
    complete: bool
    verified: Optional[bool] = None
    
    @classmethod
    def from_torrent_scanner(cls, torrent: Torrent, matches: List[Match]) -> 'TorrentMatch':
        """Convert from torrent-scanner models to mediadata format."""
        # Get the best match if multiple exist
        match = matches[0] if matches else None
        root_path = Path(match.data_path) if match else None
        
        # Convert file information
        file_matches = []
        if torrent.is_multi:
            # Multi-file torrent - get files from database
            for tf in torrent.files:
                file_path = root_path / tf.path if root_path else None
                if file_path and file_path.exists():
                    file_matches.append(FileMatch(
                        torrent_path=tf.path,
                        filesystem_path=file_path,
                        size=tf.size,
                        verified=None
                    ))
        else:
            # Single file torrent
            if root_path and root_path.exists():
                file_matches.append(FileMatch(
                    torrent_path=torrent.name,
                    filesystem_path=root_path,
                    size=torrent.total_length,
                    verified=None
                ))
        
        return cls(
            torrent_file=Path(torrent.torrent_path),
            info_hash=torrent.info_hash,
            name=torrent.name,
            root_path=root_path,
            files=file_matches,
            complete=bool(match),
            verified=None
        )


class TorrentScanner:
    """Enhanced scanner using torrent-scanner backend."""
    
    def __init__(self, db_path: Optional[Path] = None, redis_path: Optional[Path] = None, 
                 verify_hashes: bool = False):
        """Initialize scanner with database paths."""
        # Use mediadata's config for paths
        if db_path is None:
            db_path = Path.home() / '.mediadata' / 'torrents.db'
        if redis_path is None:
            redis_path = Path.home() / '.mediadata' / 'redis.db'
            
        # Ensure directories exist
        db_path.parent.mkdir(parents=True, exist_ok=True)
        redis_path.parent.mkdir(parents=True, exist_ok=True)
            
        self.scanner = TSScanner(db_path=db_path, redis_path=redis_path)
        self.verify_hashes = verify_hashes
        self.logger = logging.getLogger(__name__)
    
    def scan_and_match(self, folder_paths: List[Path]) -> List[TorrentMatch]:
        """Scan folders for torrents and match to data."""
        self.logger.info(f"Indexing torrents from {len(folder_paths)} folders")
        
        # Index all torrent files
        stats = self.scanner.index_torrents(folder_paths)
        self.logger.info(f"Indexed {stats['new']} new torrents, {stats['updated']} updated")
        
        # Find matches in the same folders
        matches = self.scanner.find_matches(folder_paths)
        self.logger.info(f"Found {len(matches)} matches")
        
        # Convert to mediadata format
        results = []
        for torrent_info, match_list in matches.items():
            torrent = self.scanner.get_torrent_info(torrent_info['info_hash'])
            if torrent:
                tm = TorrentMatch.from_torrent_scanner(torrent, match_list)
                results.append(tm)
        
        return results
    
    def get_torrent_by_hash(self, info_hash: str) -> Optional[TorrentMatch]:
        """Retrieve torrent information from database."""
        torrent = self.scanner.get_torrent_info(info_hash)
        if torrent:
            matches = self.scanner.get_data_locations(info_hash)
            return TorrentMatch.from_torrent_scanner(torrent, matches)
        return None
    
    def list_all_torrents(self, filter_type: str = 'all') -> List[Dict[str, Any]]:
        """List torrents from database with filtering."""
        return self.scanner.list_torrents(filter_type)
    
    def cleanup_missing(self) -> int:
        """Remove torrents whose files no longer exist."""
        return self.scanner.cleanup_missing_torrents()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        return self.scanner.get_statistics()


def create_scan_report(matches: List[TorrentMatch]) -> Dict[str, Any]:
    """Create a detailed scan report from torrent matches."""
    complete_matches = [m for m in matches if m.complete]
    incomplete_matches = [m for m in matches if not m.complete]
    
    total_files = sum(len(m.files) for m in matches)  # Count files from all matches
    total_size = sum(f.size for m in matches for f in m.files)  # Count size from all matches
    
    return {
        'total_torrents': len(matches),
        'complete_matches': len(complete_matches),
        'incomplete_matches': len(incomplete_matches),
        'total_files': total_files,
        'total_size_bytes': total_size,
        'total_size_human': _format_size(total_size),
        'match_rate': len(complete_matches) / len(matches) if matches else 0.0,
        'torrents': [
            {
                'name': m.name,
                'info_hash': m.info_hash,
                'complete': m.complete,
                'files': len(m.files),
                'size_bytes': sum(f.size for f in m.files),
                'root_path': str(m.root_path) if m.root_path else None
            }
            for m in matches
        ]
    }


def _format_size(size_bytes: int) -> str:
    """Format byte size in human-readable format."""
    if size_bytes == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"