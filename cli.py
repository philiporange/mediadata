#!/usr/bin/env python3
"""
MediaData CLI - Command-line interface for media metadata management.

This CLI provides access to all MediaData functionality:
- Complete processing workflows
- Individual step control (scan, organize, metadata)
- Library management and status
- Progress reporting and verbose output

Usage:
    mediadata process /torrents /data /archive --tmdb-key YOUR_KEY
    mediadata scan /torrents /data --verify-hashes
    mediadata organize /torrents /data /archive --action copy
    mediadata metadata /archive --tmdb-key YOUR_KEY
    mediadata status /archive
    mediadata info /path/to/file.torrent
"""

import os
import sys
import argparse
import json
from pathlib import Path
from typing import Optional, Dict, Any
import time
from datetime import datetime

try:
    # Try to import colorama for colored output
    from colorama import init as colorama_init, Fore, Back, Style
    colorama_init()
    COLORS_AVAILABLE = True
except ImportError:
    # Fallback if colorama not available
    class _FakeColorama:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ''
    Fore = Back = Style = _FakeColorama()
    COLORS_AVAILABLE = False

from mediadata import (
    MediaData, 
    ProcessingStats, 
    process_media_directory,
    OrganizeAction,
    CollisionStrategy,
    TorrentScanner,
    get_torrent_info
)


class CLIProgressReporter:
    """Progress reporter for CLI operations."""
    
    def __init__(self, verbose: bool = False, use_colors: bool = True):
        self.verbose = verbose
        self.use_colors = use_colors and COLORS_AVAILABLE
        self.start_time = time.time()
        self.last_percent = 0
    
    def info(self, message: str) -> None:
        """Print info message."""
        if self.use_colors:
            print(f"{Fore.CYAN}ℹ{Style.RESET_ALL} {message}")
        else:
            print(f"[INFO] {message}")
    
    def success(self, message: str) -> None:
        """Print success message."""
        if self.use_colors:
            print(f"{Fore.GREEN}✓{Style.RESET_ALL} {message}")
        else:
            print(f"[SUCCESS] {message}")
    
    def warning(self, message: str) -> None:
        """Print warning message."""
        if self.use_colors:
            print(f"{Fore.YELLOW}⚠{Style.RESET_ALL} {message}")
        else:
            print(f"[WARNING] {message}")
    
    def error(self, message: str) -> None:
        """Print error message."""
        if self.use_colors:
            print(f"{Fore.RED}✗{Style.RESET_ALL} {message}")
        else:
            print(f"[ERROR] {message}")
    
    def progress(self, message: str, percent: float = 0.0) -> None:
        """Print progress update."""
        # Only show progress if it's increased significantly or is verbose
        if self.verbose or (percent - self.last_percent) >= 5.0 or percent >= 100.0:
            elapsed = time.time() - self.start_time
            if self.use_colors:
                bar_length = 30
                filled = int(bar_length * percent / 100)
                bar = '█' * filled + '░' * (bar_length - filled)
                print(f"\r{Fore.BLUE}[{bar}]{Style.RESET_ALL} {percent:5.1f}% | {message} | {elapsed:.1f}s", end='', flush=True)
                if percent >= 100.0:
                    print()  # New line when complete
            else:
                print(f"[{percent:5.1f}%] {message} ({elapsed:.1f}s)")
            
            self.last_percent = percent
    
    def print_stats(self, stats: ProcessingStats) -> None:
        """Print processing statistics."""
        print()
        self.info("Processing Statistics:")
        
        stats_dict = stats.to_dict()
        
        # Success/failure summary
        if stats.total_torrents_found > 0:
            self.success(f"Torrents Found: {stats.total_torrents_found}")
            
            if stats.successful_matches > 0:
                self.success(f"Successfully Matched: {stats.successful_matches} ({stats.match_rate:.1%})")
            else:
                self.warning("No torrents successfully matched to data files")
            
            if stats.organized_torrents > 0:
                self.success(f"Organized into Library: {stats.organized_torrents}")
            
            if stats.metadata_processed > 0:
                self.success(f"Metadata Added: {stats.metadata_processed}")
        else:
            self.warning("No torrent files found")
        
        # File and size info
        if stats.total_files > 0:
            self.info(f"Total Files: {stats.total_files:,}")
            self.info(f"Total Size: {stats_dict['total_size_human']}")
        
        # Timing
        if stats.processing_time_seconds > 0:
            self.info(f"Processing Time: {stats.processing_time_seconds:.1f} seconds")


def create_base_parser() -> argparse.ArgumentParser:
    """Create the base argument parser."""
    parser = argparse.ArgumentParser(
        prog='mediadata',
        description='MediaData - Media metadata management system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Complete workflow - scan, organize, and fetch metadata
  mediadata process /path/to/torrents /path/to/media /path/to/archive
  
  # Just scan and match torrents to files
  mediadata scan /path/to/torrents /path/to/media --verbose
  
  # Organize matched torrents into library (dry run)
  mediadata organize /path/to/torrents /path/to/media /path/to/archive --dry-run
  
  # Fetch metadata for existing library
  mediadata metadata /path/to/archive --tmdb-key YOUR_API_KEY
  
  # Check library status
  mediadata status /path/to/archive
  
  # Get info about a specific torrent
  mediadata info /path/to/movie.torrent

Environment Variables:
  TMDB_API_KEY    TMDB API key for metadata fetching
  MEDIADATA_ARCHIVE    Default archive directory
        """
    )
    
    # Global options
    parser.add_argument('-v', '--verbose', action='store_true', 
                       help='Enable verbose output')
    parser.add_argument('--no-color', action='store_true',
                       help='Disable colored output')
    parser.add_argument('--config', type=Path,
                       help='Configuration file path')
    
    return parser


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments to a parser."""
    parser.add_argument('--tmdb-key', type=str,
                       help='TMDB API key (or set TMDB_API_KEY env var)')
    parser.add_argument('--max-workers', type=int, default=4,
                       help='Number of parallel workers (default: 4)')


def add_organize_args(parser: argparse.ArgumentParser) -> None:
    """Add organization-specific arguments."""
    parser.add_argument('--action', type=str, 
                       choices=['move', 'copy', 'symlink', 'hardlink'],
                       default='move',
                       help='How to handle files (default: move)')
    parser.add_argument('--collision', type=str,
                       choices=['skip', 'overwrite', 'rename', 'compare'],
                       default='compare',
                       help='How to handle file collisions (default: compare)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without actually doing it')


def command_process(args: argparse.Namespace) -> int:
    """Handle the 'process' command - complete workflow."""
    reporter = CLIProgressReporter(args.verbose, not args.no_color)
    
    reporter.info(f"Starting complete MediaData processing workflow")
    reporter.info(f"Torrents: {args.torrent_dir}")
    reporter.info(f"Data: {args.data_dir}")  
    reporter.info(f"Archive: {args.archive_dir}")
    
    if args.dry_run:
        reporter.warning("DRY RUN MODE - No files will be moved")
    
    try:
        # Get action and collision strategy
        action = getattr(OrganizeAction, args.action.upper())
        collision = getattr(CollisionStrategy, args.collision.upper())
        
        def progress_callback(message: str, percent: float):
            reporter.progress(message, percent)
        
        # Initialize MediaData
        with MediaData(
            archive_dir=args.archive_dir,
            tmdb_api_key=args.tmdb_key,
            verify_hashes=args.verify_hashes,
            organize_action=action,
            collision_strategy=collision,
            max_workers=args.max_workers
        ) as media:
            
            # Execute complete workflow
            stats = media.process_directory(
                torrent_dir=args.torrent_dir,
                data_dir=args.data_dir,
                dry_run=args.dry_run,
                progress_callback=progress_callback
            )
            
            # Print results
            reporter.print_stats(stats)
            
            # Return appropriate exit code
            if stats.total_torrents_found == 0:
                return 1
            elif stats.successful_matches == 0:
                return 2
            else:
                return 0
                
    except Exception as e:
        reporter.error(f"Processing failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def command_scan(args: argparse.Namespace) -> int:
    """Handle the 'scan' command - torrent matching only."""
    reporter = CLIProgressReporter(args.verbose, not args.no_color)
    
    reporter.info(f"Scanning torrents and matching to data files")
    reporter.info(f"Torrents: {args.torrent_dir}")
    reporter.info(f"Data: {args.data_dir}")
    
    try:
        def progress_callback(message: str, percent: float):
            reporter.progress(message, percent)
        
        # Initialize scanner
        scanner = TorrentScanner(
            verify_hashes=args.verify_hashes,
            max_workers=args.max_workers
        )
        
        # Find torrents
        from src.utils import scan_torrent_files
        torrent_files = scan_torrent_files(Path(args.torrent_dir))
        
        if not torrent_files:
            reporter.warning("No torrent files found")
            return 1
        
        reporter.info(f"Found {len(torrent_files)} torrent files")
        
        # Match torrents
        matches = scanner.scan_directory(
            Path(args.data_dir),
            torrent_files,
            progress_callback
        )
        
        # Analyze results
        complete_matches = [m for m in matches if m.complete]
        partial_matches = [m for m in matches if m.files and not m.complete]
        failed_matches = [m for m in matches if not m.files]
        
        # Print results
        print()
        reporter.success(f"Complete Matches: {len(complete_matches)}")
        if partial_matches:
            reporter.warning(f"Partial Matches: {len(partial_matches)}")
        if failed_matches:
            reporter.warning(f"Failed Matches: {len(failed_matches)}")
        
        # Show details if verbose
        if args.verbose:
            print()
            for match in complete_matches[:10]:  # Show first 10
                reporter.success(f"✓ {match.name} ({len(match.files)} files)")
            
            for match in partial_matches[:5]:  # Show first 5
                reporter.warning(f"⚠ {match.name} ({len(match.files)}/{len(match.files) + 1} files)")
            
            for match in failed_matches[:5]:  # Show first 5
                reporter.error(f"✗ {match.name} (no files found)")
        
        return 0 if complete_matches else 1
        
    except Exception as e:
        reporter.error(f"Scan failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def command_organize(args: argparse.Namespace) -> int:
    """Handle the 'organize' command - library organization only."""
    reporter = CLIProgressReporter(args.verbose, not args.no_color)
    
    reporter.info(f"Organizing torrents into library structure")
    if args.dry_run:
        reporter.warning("DRY RUN MODE - No files will be moved")
    
    try:
        # Get action and collision strategy
        action = getattr(OrganizeAction, args.action.upper())
        collision = getattr(CollisionStrategy, args.collision.upper())
        
        def progress_callback(message: str, percent: float):
            reporter.progress(message, percent)
        
        # Initialize MediaData
        with MediaData(
            archive_dir=args.archive_dir,
            organize_action=action,
            collision_strategy=collision,
            max_workers=args.max_workers
        ) as media:
            
            # First scan and match
            matches = media.scan_and_match(
                args.torrent_dir, 
                args.data_dir,
                progress_callback
            )
            
            complete_matches = [m for m in matches if m.complete]
            if not complete_matches:
                reporter.warning("No complete matches found to organize")
                return 1
            
            reporter.info(f"Found {len(complete_matches)} complete matches to organize")
            
            # Organize torrents
            results = media.organize_torrents(
                complete_matches,
                dry_run=args.dry_run,
                progress_callback=progress_callback
            )
            
            # Print results
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            
            print()
            reporter.success(f"Successfully organized: {len(successful)}")
            if failed:
                reporter.warning(f"Failed to organize: {len(failed)}")
            
            # Show total bytes processed
            total_bytes = sum(r.bytes_processed for r in successful)
            if total_bytes > 0:
                size_str = ProcessingStats()._format_size(total_bytes)
                reporter.info(f"Total size processed: {size_str}")
            
            return 0 if successful else 1
            
    except Exception as e:
        reporter.error(f"Organization failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def command_metadata(args: argparse.Namespace) -> int:
    """Handle the 'metadata' command - fetch metadata for library."""
    reporter = CLIProgressReporter(args.verbose, not args.no_color)
    
    if not args.tmdb_key and not os.environ.get('TMDB_API_KEY'):
        reporter.error("TMDB API key required. Use --tmdb-key or set TMDB_API_KEY environment variable")
        return 1
    
    reporter.info(f"Fetching metadata for library: {args.archive_dir}")
    
    try:
        # Initialize MediaData
        media = MediaData(
            archive_dir=args.archive_dir,
            tmdb_api_key=args.tmdb_key,
            max_workers=args.max_workers
        )
        
        # Get library stats to find organized torrents
        library_stats = media.get_library_stats()
        if library_stats['total_torrents'] == 0:
            reporter.warning("No torrents found in library")
            return 1
        
        reporter.info(f"Found {library_stats['total_torrents']} torrents in library")
        
        # TODO: This would require finding organized torrents and processing metadata
        # For now, show what we would do
        reporter.info("Metadata processing for existing library not yet implemented")
        reporter.info("Use 'process' command for complete workflow including metadata")
        
        return 0
        
    except Exception as e:
        reporter.error(f"Metadata processing failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def command_status(args: argparse.Namespace) -> int:
    """Handle the 'status' command - show library information."""
    reporter = CLIProgressReporter(args.verbose, not args.no_color)
    
    try:
        archive_path = Path(args.archive_dir)
        
        if not archive_path.exists():
            reporter.warning(f"Archive directory does not exist: {archive_path}")
            return 1
        
        # Initialize MediaData to get stats
        media = MediaData(archive_dir=archive_path)
        stats = media.get_library_stats()
        
        # Print library information
        print()
        reporter.info(f"MediaData Library Status")
        print(f"📁 Archive Directory: {archive_path}")
        print(f"🎬 Total Torrents: {stats['total_torrents']:,}")
        print(f"📄 Total Files: {stats['total_files']:,}")
        print(f"💾 Total Size: {stats['total_size_human']}")
        
        # Check for logs
        logs_dir = archive_path / 'logs'
        if logs_dir.exists():
            log_files = list(logs_dir.glob('*.log'))
            print(f"📋 Log Files: {len(log_files)}")
        
        # TMDB configuration
        tmdb_configured = bool(os.environ.get('TMDB_API_KEY'))
        tmdb_status = "✓ Configured" if tmdb_configured else "✗ Not configured"
        print(f"🎭 TMDB API: {tmdb_status}")
        
        print()
        return 0
        
    except Exception as e:
        reporter.error(f"Failed to get status: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def command_info(args: argparse.Namespace) -> int:
    """Handle the 'info' command - show torrent file information."""
    reporter = CLIProgressReporter(args.verbose, not args.no_color)
    
    try:
        torrent_path = Path(args.torrent_file)
        
        if not torrent_path.exists():
            reporter.error(f"Torrent file not found: {torrent_path}")
            return 1
        
        # Get torrent info
        info = get_torrent_info(torrent_path)
        
        # Print torrent information
        print()
        reporter.info(f"Torrent Information")
        print(f"📁 File: {torrent_path}")
        print(f"🏷️  Name: {info['name']}")
        print(f"🔑 Info Hash: {info['info_hash']}")
        print(f"📄 Files: {len(info['files'])}")
        print(f"💾 Size: {ProcessingStats()._format_size(info['total_size'])}")
        
        if info.get('announce'):
            print(f"📡 Tracker: {info['announce']}")
        
        if info.get('creation_date'):
            created = datetime.fromtimestamp(info['creation_date'])
            print(f"📅 Created: {created.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if info.get('created_by'):
            print(f"👤 Created by: {info['created_by']}")
        
        # Show files if verbose
        if args.verbose and len(info['files']) <= 20:
            print(f"\n📋 Files:")
            for i, file_info in enumerate(info['files'], 1):
                size_str = ProcessingStats()._format_size(file_info['size'])
                print(f"  {i:2d}. {file_info['path']} ({size_str})")
        elif len(info['files']) > 20:
            print(f"\n📋 Files: {len(info['files'])} files (use --verbose to list)")
        
        print()
        return 0
        
    except Exception as e:
        reporter.error(f"Failed to get torrent info: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def main() -> int:
    """Main CLI entry point."""
    # Create main parser
    parser = create_base_parser()
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Process command - complete workflow
    process_parser = subparsers.add_parser(
        'process', 
        help='Complete workflow: scan, organize, and fetch metadata'
    )
    process_parser.add_argument('torrent_dir', type=Path, help='Directory containing torrent files')
    process_parser.add_argument('data_dir', type=Path, help='Directory containing media files')
    process_parser.add_argument('archive_dir', type=Path, help='Archive directory for organized library')
    process_parser.add_argument('--verify-hashes', action='store_true',
                               help='Verify file integrity using torrent hashes')
    add_common_args(process_parser)
    add_organize_args(process_parser)
    
    # Scan command - torrent matching only
    scan_parser = subparsers.add_parser(
        'scan',
        help='Scan torrents and match to data files'
    )
    scan_parser.add_argument('torrent_dir', type=Path, help='Directory containing torrent files')
    scan_parser.add_argument('data_dir', type=Path, help='Directory containing media files')
    scan_parser.add_argument('--verify-hashes', action='store_true',
                            help='Verify file integrity using torrent hashes')
    add_common_args(scan_parser)
    
    # Organize command - library organization
    organize_parser = subparsers.add_parser(
        'organize',
        help='Organize matched torrents into library structure'
    )
    organize_parser.add_argument('torrent_dir', type=Path, help='Directory containing torrent files')
    organize_parser.add_argument('data_dir', type=Path, help='Directory containing media files')  
    organize_parser.add_argument('archive_dir', type=Path, help='Archive directory for organized library')
    add_common_args(organize_parser)
    add_organize_args(organize_parser)
    
    # Metadata command - fetch metadata
    metadata_parser = subparsers.add_parser(
        'metadata',
        help='Fetch metadata for library torrents'
    )
    metadata_parser.add_argument('archive_dir', type=Path, help='Archive directory')
    add_common_args(metadata_parser)
    
    # Status command - library information
    status_parser = subparsers.add_parser(
        'status',
        help='Show library status and information'
    )
    status_parser.add_argument('archive_dir', type=Path, help='Archive directory')
    
    # Info command - torrent file information
    info_parser = subparsers.add_parser(
        'info',
        help='Show information about a torrent file'
    )
    info_parser.add_argument('torrent_file', type=Path, help='Path to torrent file')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Show help if no command specified
    if not args.command:
        parser.print_help()
        return 1
    
    # Set default archive from environment if not provided
    if hasattr(args, 'archive_dir') and not getattr(args, 'archive_dir', None):
        env_archive = os.environ.get('MEDIADATA_ARCHIVE')
        if env_archive:
            args.archive_dir = Path(env_archive)
    
    # Route to appropriate command handler
    command_handlers = {
        'process': command_process,
        'scan': command_scan,
        'organize': command_organize,
        'metadata': command_metadata,
        'status': command_status,
        'info': command_info,
    }
    
    handler = command_handlers.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())