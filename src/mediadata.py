"""
MediaData - Main interface for media metadata management system.

This module provides the primary MediaData class that orchestrates all functionality:
- Torrent scanning and matching to filesystem data
- Library organization with hash-based structure
- Metadata identification and fetching from TMDB
- NFO file generation and management
- Comprehensive logging and audit trails

Example Usage:
    from mediadata import MediaData
    
    # Initialize with archive directory
    media = MediaData('/path/to/archive')
    
    # Complete workflow: scan, organize, fetch metadata
    results = media.process_directory(
        torrent_dir='/path/to/torrents',
        data_dir='/path/to/media/files'
    )
    
    # Or step by step
    matches = media.scan_and_match('/torrents', '/data')
    organized = media.organize_torrents(matches)
    metadata_results = media.fetch_metadata(organized)
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union, Callable, Any
from dataclasses import dataclass
from datetime import datetime
import time

# Import all the functionality from our modules
from .scan import TorrentScanner, TorrentMatch, create_scan_report
from .organize import (
    LibraryOrganizer, 
    OrganizeAction, 
    CollisionStrategy, 
    OrganizeResult,
    create_organize_report
)
from .metadata import (
    MetadataProcessor,
    TMDBClient,
    GoodreadsClient,
    MediaIdentifier,
    MetadataResult,
    setup_metadata_logging,
    process_torrents_metadata
)
from .utils import scan_torrent_files, get_torrent_info
from .config.config import config


@dataclass
class ProcessingStats:
    """Statistics from a complete processing run."""
    total_torrents_found: int = 0
    successful_matches: int = 0
    organized_torrents: int = 0
    metadata_processed: int = 0
    total_files: int = 0
    total_size_bytes: int = 0
    processing_time_seconds: float = 0.0
    
    def __post_init__(self):
        """Calculate derived statistics."""
        self.match_rate = (self.successful_matches / self.total_torrents_found 
                          if self.total_torrents_found > 0 else 0.0)
        self.organization_rate = (self.organized_torrents / self.successful_matches 
                                if self.successful_matches > 0 else 0.0)
        self.metadata_rate = (self.metadata_processed / self.organized_torrents 
                            if self.organized_torrents > 0 else 0.0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'total_torrents_found': self.total_torrents_found,
            'successful_matches': self.successful_matches,
            'organized_torrents': self.organized_torrents,
            'metadata_processed': self.metadata_processed,
            'total_files': self.total_files,
            'total_size_bytes': self.total_size_bytes,
            'total_size_human': self._format_size(self.total_size_bytes),
            'processing_time_seconds': self.processing_time_seconds,
            'match_rate': self.match_rate,
            'organization_rate': self.organization_rate,
            'metadata_rate': self.metadata_rate
        }
    
    def _format_size(self, size_bytes: int) -> str:
        """Format byte size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"


class MediaData:
    """
    Main interface for the MediaData system.
    
    This class orchestrates all functionality for managing media metadata:
    - Scanning torrents and matching to filesystem data
    - Organizing files into hash-based library structure  
    - Fetching metadata from TMDB and other sources
    - Generating NFO files compatible with Kodi/Jellyfin
    - Comprehensive logging and audit trails
    """
    
    def __init__(self, 
                 archive_dir: Union[str, Path],
                 tmdb_api_key: Optional[str] = None,
                 goodreads_cache_expire: int = 3600,
                 verify_hashes: bool = False,
                 organize_action: OrganizeAction = OrganizeAction.MOVE,
                 collision_strategy: CollisionStrategy = CollisionStrategy.COMPARE,
                 max_workers: int = 4):
        """
        Initialize MediaData system.
        
        Args:
            archive_dir: Directory where organized media library will be stored
            tmdb_api_key: TMDB API key (optional, can use TMDB_API_KEY env var)
            goodreads_cache_expire: Cache expiration time in seconds for Goodreads
            verify_hashes: Whether to verify file integrity using torrent piece hashes
            organize_action: How to handle files (move, copy, symlink, hardlink)
            collision_strategy: How to handle file collisions
            max_workers: Number of worker threads for parallel operations
        """
        self.archive_dir = Path(archive_dir)
        self.tmdb_api_key = tmdb_api_key
        self.goodreads_cache_expire = goodreads_cache_expire
        self.verify_hashes = verify_hashes
        self.organize_action = organize_action
        self.collision_strategy = collision_strategy
        self.max_workers = max_workers
        
        # Ensure archive directory exists
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components - always use torrent-scanner backend
        self.scanner = TorrentScanner(
            db_path=config.torrent_db_path,
            redis_path=config.redis_db_path,
            verify_hashes=self.verify_hashes
        )
        
        self.organizer = LibraryOrganizer(
            library_path=self.archive_dir,
            default_action=self.organize_action,
            collision_strategy=self.collision_strategy,
            max_workers=self.max_workers
        )
        
        self.tmdb_client = TMDBClient(self.tmdb_api_key)
        self.goodreads_client = GoodreadsClient(cache_expire=self.goodreads_cache_expire)
        self.metadata_processor = MetadataProcessor(self.tmdb_client, self.goodreads_client)
        
        # Setup logging
        self.logger = self._setup_logging()
        
        # Store configuration
        self.config = {
            'archive_dir': str(self.archive_dir),
            'verify_hashes': self.verify_hashes,
            'organize_action': self.organize_action.value,
            'collision_strategy': self.collision_strategy.value,
            'max_workers': self.max_workers,
            'tmdb_configured': bool(self.tmdb_api_key or os.environ.get('TMDB_API_KEY')),
            'goodreads_cache_expire': self.goodreads_cache_expire
        }
        
        self.logger.info(f"MediaData initialized with archive directory: {self.archive_dir}")
        self.logger.info(f"Configuration: {self.config}")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for MediaData operations."""
        # Create logs directory in archive
        logs_dir = self.archive_dir / 'logs'
        logs_dir.mkdir(exist_ok=True)
        
        # Setup logger
        logger = logging.getLogger('mediadata.main')
        logger.setLevel(logging.INFO)
        
        # Avoid duplicate handlers
        if not logger.handlers:
            # File handler
            log_file = logs_dir / f"mediadata_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.INFO)
            
            # Console handler  
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # Formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
        
        return logger
    
    def scan_torrents(self, torrent_dir: Union[str, Path], recursive: bool = True) -> List[Path]:
        """
        Scan directory for torrent files.
        
        Args:
            torrent_dir: Directory containing .torrent files
            recursive: Whether to scan subdirectories
            
        Returns:
            List of torrent file paths found
        """
        self.logger.info(f"Scanning for torrents in: {torrent_dir}")
        torrent_files = scan_torrent_files(Path(torrent_dir), recursive)
        self.logger.info(f"Found {len(torrent_files)} torrent files")
        return torrent_files
    
    
    def scan_and_match(self, 
                      folder_paths: List[Union[str, Path]],
                      progress_callback: Optional[Callable[[str, float], None]] = None) -> List[TorrentMatch]:
        """
        Scan folders for torrents and match them to data files using torrent-scanner backend.
        
        Args:
            folder_paths: List of directories to scan for both torrents and media files
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of TorrentMatch objects
        """
        self.logger.info(f"Starting torrent-scanner based scanning and matching for {len(folder_paths)} folders")
        
        # Convert to Path objects
        paths = [Path(p) for p in folder_paths]
        
        if progress_callback:
            progress_callback("Indexing torrents and finding matches", 50)
        
        # Use the enhanced scanner which handles both indexing and matching
        matches = self.scanner.scan_and_match(paths)
        
        # Log results
        complete_matches = [m for m in matches if m.complete]
        self.logger.info(f"Torrent-scanner matching complete: {len(complete_matches)}/{len(matches)} torrents matched")
        
        if progress_callback:
            progress_callback("Matching complete", 100)
        
        return matches
    
    def _deduplicate_matches(self, matches: List[TorrentMatch]) -> List[TorrentMatch]:
        """
        Remove duplicate matches, preferring complete matches over partial ones.
        
        Args:
            matches: List of potentially duplicate TorrentMatch objects
            
        Returns:
            List of unique matches
        """
        # Group matches by info_hash
        matches_by_hash = {}
        for match in matches:
            info_hash = match.info_hash
            if info_hash not in matches_by_hash:
                matches_by_hash[info_hash] = []
            matches_by_hash[info_hash].append(match)
        
        # Select best match for each hash
        unique_matches = []
        for info_hash, match_list in matches_by_hash.items():
            if len(match_list) == 1:
                unique_matches.append(match_list[0])
            else:
                # Prefer complete matches, then matches with more files
                best_match = max(match_list, key=lambda m: (m.complete, len(m.files)))
                unique_matches.append(best_match)
                
                self.logger.debug(f"Deduplicated torrent {info_hash}: kept match with {len(best_match.files)} files (complete: {best_match.complete})")
        
        return unique_matches
    
    def organize_torrents(self, 
                         torrent_matches: List[TorrentMatch],
                         dry_run: bool = False,
                         progress_callback: Optional[Callable[[str, float], None]] = None) -> List[OrganizeResult]:
        """
        Organize matched torrents into the archive library structure.
        
        Args:
            torrent_matches: List of matched torrents to organize
            dry_run: If True, don't actually move files
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of OrganizeResult objects
        """
        self.logger.info(f"Organizing {len(torrent_matches)} torrents into library")
        
        if dry_run:
            self.logger.info("DRY RUN MODE - No files will be moved")
            self.organizer.dry_run = True
        
        # Filter to complete matches only
        complete_matches = [m for m in torrent_matches if m.complete]
        if not complete_matches:
            self.logger.warning("No complete matches to organize")
            return []
        
        # Organize torrents
        results = self.organizer.organize_matches(complete_matches, progress_callback)
        
        # Log results
        successful = [r for r in results if r.success]
        self.logger.info(f"Organization complete: {len(successful)}/{len(results)} torrents organized")
        
        return results
    
    def fetch_metadata(self, 
                      organize_results: List[OrganizeResult],
                      progress_callback: Optional[Callable[[str], None]] = None) -> List[MetadataResult]:
        """
        Fetch metadata for organized torrents.
        
        Args:
            organize_results: List of organization results
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of MetadataResult objects
        """
        # Filter to successful organizations
        successful_results = [r for r in organize_results if r.success]
        
        if not successful_results:
            self.logger.warning("No successfully organized torrents to process metadata for")
            return []
        
        self.logger.info(f"Processing metadata for {len(successful_results)} organized torrents")
        
        metadata_results = []
        
        for i, result in enumerate(successful_results):
            if progress_callback:
                progress_callback(f"Processing metadata for {result.torrent_match.name} ({i+1}/{len(successful_results)})")
            
            # Setup logging for this specific torrent
            log_dir = result.target_dir / 'metadata' / 'logs'
            setup_metadata_logging(log_dir)
            
            # Process metadata
            metadata_result = self.metadata_processor.process_torrent_match(
                result.torrent_match, 
                result.target_dir
            )
            metadata_results.append(metadata_result)
            
            # Log individual result
            if metadata_result.identification:
                self.logger.info(f"✓ {metadata_result.identification.title} - metadata processed")
            else:
                self.logger.warning(f"✗ {result.torrent_match.name} - metadata failed: {metadata_result.error}")
        
        successful_metadata = [r for r in metadata_results if r.identification]
        self.logger.info(f"Metadata processing complete: {len(successful_metadata)}/{len(metadata_results)} successful")
        
        return metadata_results
    
    def process(self,
               folder_paths: List[Union[str, Path]], 
               dry_run: bool = False,
               progress_callback: Optional[Callable[[str, float], None]] = None) -> ProcessingStats:
        """
        Complete workflow: scan folders for torrents, match, organize, and fetch metadata.
        
        Args:
            folder_paths: List of directories to scan for torrents and media files
            dry_run: If True, don't actually move files
            progress_callback: Optional callback for progress updates
            
        Returns:
            ProcessingStats with comprehensive results
        """
        start_time = time.time()
        
        self.logger.info("=" * 60)
        self.logger.info("STARTING COMPLETE MEDIADATA PROCESSING WORKFLOW (UNIFIED FOLDERS)")
        self.logger.info(f"Folders to scan: {[str(p) for p in folder_paths]}")
        self.logger.info("=" * 60)
        
        stats = ProcessingStats()
        
        def progress_wrapper(message: str, percent: float = 0.0):
            if progress_callback:
                progress_callback(message, percent)
            self.logger.info(f"Progress: {message} ({percent:.1f}%)")
        
        try:
            # Step 1: Scan and match using unified approach
            progress_wrapper("Scanning folders for torrents and matching", 10)
            matches = self.scan_and_match(folder_paths, progress_wrapper)
            
            stats.total_torrents_found = len(matches)
            stats.successful_matches = len([m for m in matches if m.complete])
            
            if not matches:
                self.logger.error("No torrents found or matched - stopping workflow")
                return stats
            
            # Step 2: Organize 
            progress_wrapper("Organizing torrents into library", 40)
            organize_results = self.organize_torrents(matches, dry_run, progress_wrapper)
            
            stats.organized_torrents = len([r for r in organize_results if r.success])
            
            # Calculate file stats
            for result in organize_results:
                if result.success:
                    stats.total_files += len(result.operations)
                    stats.total_size_bytes += result.bytes_processed
            
            if not organize_results or not any(r.success for r in organize_results):
                self.logger.error("No torrents successfully organized - stopping workflow")
                return stats
            
            # Step 3: Fetch metadata (only if not dry run)
            if not dry_run:
                progress_wrapper("Fetching metadata from TMDB", 80)
                
                def metadata_progress(message: str):
                    progress_wrapper(f"Metadata: {message}", 85)
                
                metadata_results = self.fetch_metadata(organize_results, metadata_progress)
                stats.metadata_processed = len([r for r in metadata_results if r.identification])
            else:
                self.logger.info("Skipping metadata processing in dry-run mode")
            
            progress_wrapper("Processing complete", 100)
            
        except Exception as e:
            self.logger.error(f"Error during processing: {e}")
            raise
        
        finally:
            stats.processing_time_seconds = time.time() - start_time
            
            # Log final statistics
            self.logger.info("=" * 60)
            self.logger.info("PROCESSING COMPLETE - FINAL STATISTICS")
            self.logger.info("=" * 60)
            
            stats_dict = stats.to_dict()
            for key, value in stats_dict.items():
                self.logger.info(f"{key}: {value}")
            
            self.logger.info("=" * 60)
        
        return stats
    
    def get_library_stats(self) -> Dict[str, Any]:
        """Get statistics about the current library."""
        organizer_stats = self.organizer.get_library_stats()
        scanner_stats = self.scanner.get_statistics()
        
        # Combine stats from both sources
        combined_stats = {
            **organizer_stats,
            'database_torrents': scanner_stats.get('total_torrents', 0),
            'matched_torrents': scanner_stats.get('matched_torrents', 0),
            'database_size_bytes': scanner_stats.get('total_size_bytes', 0)
        }
        
        return combined_stats
    
    def check_torrent_exists(self, info_hash: str) -> Optional[Path]:
        """Check if a torrent already exists in the library."""
        return self.organizer.check_existing_torrent(info_hash)
    
    def get_torrent_by_hash(self, info_hash: str) -> Optional[TorrentMatch]:
        """Retrieve torrent information from database."""
        return self.scanner.get_torrent_by_hash(info_hash)
    
    def list_all_torrents(self, filter_type: str = 'all') -> List[Dict[str, Any]]:
        """List torrents from database with filtering."""
        return self.scanner.list_all_torrents(filter_type)
    
    def cleanup_missing_torrents(self) -> int:
        """Remove torrents whose files no longer exist."""
        return self.scanner.cleanup_missing()
    
    def get_torrent_info(self, torrent_path: Union[str, Path]) -> Dict[str, Any]:
        """Get information about a specific torrent file."""
        return get_torrent_info(Path(torrent_path))
    
    def set_tmdb_api_key(self, api_key: str) -> None:
        """Set or update the TMDB API key."""
        self.tmdb_api_key = api_key
        self.tmdb_client = TMDBClient(api_key)
        self.metadata_processor = MetadataProcessor(self.tmdb_client)
        self.config['tmdb_configured'] = True
        self.logger.info("TMDB API key updated")
    
    def create_scan_report(self, matches: List[TorrentMatch]) -> Dict[str, Any]:
        """Create detailed scan report."""
        return create_scan_report(matches)
    
    def create_organize_report(self, results: List[OrganizeResult]) -> Dict[str, Any]:
        """Create detailed organization report."""
        return create_organize_report(results)
    
    def __repr__(self) -> str:
        """String representation of MediaData instance."""
        return f"MediaData(archive_dir='{self.archive_dir}', configured={self.config['tmdb_configured']})"
    
    def __str__(self) -> str:
        """Human-readable string representation."""
        stats = self.get_library_stats()
        return (f"MediaData Library\n"
               f"  Archive: {self.archive_dir}\n"
               f"  Torrents: {stats.get('total_torrents', 0)}\n"
               f"  Files: {stats.get('total_files', 0)}\n" 
               f"  Size: {stats.get('total_size_human', '0 B')}\n"
               f"  TMDB: {'✓' if self.config['tmdb_configured'] else '✗'}")
    
    # Context manager support
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup if needed."""
        if exc_type:
            self.logger.error(f"Error in MediaData context: {exc_val}")
        
        # Log final library state
        self.logger.info(f"Final library state: {self}")


# Convenience function for quick usage
def process_media(folder_paths: List[Union[str, Path]],
                 archive_dir: Union[str, Path],
                 tmdb_api_key: Optional[str] = None,
                 dry_run: bool = False,
                 verify_hashes: bool = False,
                 organize_action: OrganizeAction = OrganizeAction.MOVE) -> ProcessingStats:
    """
    Convenience function for complete media processing workflow.
    
    Args:
        folder_paths: List of directories to scan for torrents and media files
        archive_dir: Directory where organized library will be created
        tmdb_api_key: TMDB API key (optional)
        dry_run: If True, don't actually move files
        verify_hashes: Whether to verify file integrity
        organize_action: How to handle files (move, copy, symlink, hardlink)
        
    Returns:
        ProcessingStats with results
    """
    with MediaData(
        archive_dir=archive_dir,
        tmdb_api_key=tmdb_api_key,
        verify_hashes=verify_hashes,
        organize_action=organize_action
    ) as media:
        return media.process(
            folder_paths=folder_paths,
            dry_run=dry_run
        )