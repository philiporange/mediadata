"""
Library organization functionality for moving torrents and data into the planned structure.

This module provides tools for:
- Organizing matched torrents into hash-based directory structure
- Moving/copying data files while preserving structure
- Creating metadata directories and audit trails
- Handling collisions and existing data
- Dry-run mode for safe testing
"""

import os
import shutil
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set, Callable
from dataclasses import dataclass
from enum import Enum
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .scan import TorrentMatch, FileMatch
from .utils import create_library_structure
from .config.config import config


class OrganizeAction(Enum):
    """Actions that can be taken during organization."""
    MOVE = "move"
    COPY = "copy" 
    SYMLINK = "symlink"
    HARDLINK = "hardlink"


class CollisionStrategy(Enum):
    """Strategies for handling file collisions."""
    SKIP = "skip"          # Skip if target exists
    OVERWRITE = "overwrite"  # Replace existing file
    RENAME = "rename"      # Rename new file with suffix
    COMPARE = "compare"    # Compare and keep newer/larger


@dataclass
class OrganizeOperation:
    """Represents a single file operation during organization."""
    source_path: Path
    target_path: Path
    action: OrganizeAction
    size: int
    completed: bool = False
    error: Optional[str] = None


@dataclass
class OrganizeResult:
    """Result of organizing a single torrent."""
    torrent_match: TorrentMatch
    target_dir: Path
    operations: List[OrganizeOperation]
    success: bool
    error: Optional[str] = None
    bytes_processed: int = 0
    time_taken: float = 0.0


class LibraryOrganizer:
    """Organizes torrents and data into the planned library structure."""
    
    def __init__(self, 
                 library_path: Path = None,
                 default_action: OrganizeAction = OrganizeAction.MOVE,
                 collision_strategy: CollisionStrategy = CollisionStrategy.COMPARE,
                 dry_run: bool = False,
                 max_workers: int = 4):
        """
        Initialize the organizer.
        
        Args:
            library_path: Base library directory (uses config default if None)
            default_action: Default action for file operations
            collision_strategy: How to handle file collisions
            dry_run: If True, don't actually move files
            max_workers: Number of worker threads for parallel operations
        """
        self.library_path = Path(library_path) if library_path else config.library_path
        self.default_action = default_action
        self.collision_strategy = collision_strategy
        self.dry_run = dry_run
        self.max_workers = max_workers
        
        # Ensure library directory exists
        if not self.dry_run:
            self.library_path.mkdir(parents=True, exist_ok=True)
    
    def organize_matches(self, 
                        matches: List[TorrentMatch],
                        progress_callback: Optional[Callable[[str, float], None]] = None) -> List[OrganizeResult]:
        """
        Organize multiple torrent matches into the library.
        
        Args:
            matches: List of torrent matches to organize
            progress_callback: Optional callback for progress updates (message, percent)
            
        Returns:
            List of organize results
        """
        results = []
        total_matches = len(matches)
        total_bytes = sum(sum(f.size for f in m.files) for m in matches)
        processed_bytes = 0
        
        for i, match in enumerate(matches):
            if progress_callback:
                progress = (i / total_matches) * 100
                progress_callback(f"Organizing {match.name} ({i+1}/{total_matches})", progress)
            
            result = self.organize_match(match)
            results.append(result)
            processed_bytes += result.bytes_processed
            
            if progress_callback:
                byte_progress = (processed_bytes / total_bytes) * 100 if total_bytes > 0 else 0
                progress_callback(f"Completed {match.name}", byte_progress)
        
        return results
    
    def organize_match(self, match: TorrentMatch) -> OrganizeResult:
        """
        Organize a single torrent match into the library.
        
        Args:
            match: TorrentMatch to organize
            
        Returns:
            OrganizeResult with operation details
        """
        start_time = time.time()
        info_hash = match.info_hash
        
        # Create target directory structure
        target_dir = self.library_path / info_hash.lower()
        data_dir = target_dir / 'data'
        metadata_dir = target_dir / 'metadata'
        audit_dir = metadata_dir / 'audit'
        
        operations = []
        
        try:
            # Create directory structure (unless dry run)
            if not self.dry_run:
                data_dir.mkdir(parents=True, exist_ok=True)
                metadata_dir.mkdir(parents=True, exist_ok=True)
                audit_dir.mkdir(parents=True, exist_ok=True)
            
            # Plan torrent file operation
            torrent_target = target_dir / 'source.torrent'
            torrent_op = OrganizeOperation(
                source_path=match.torrent_file,
                target_path=torrent_target,
                action=OrganizeAction.COPY,  # Always copy torrent files
                size=match.torrent_file.stat().st_size if match.torrent_file.exists() else 0
            )
            operations.append(torrent_op)
            
            # Plan data file operations
            if match.complete:
                data_operations = self._plan_data_operations(match, data_dir)
                operations.extend(data_operations)
            
            # Execute operations
            bytes_processed = 0
            for operation in operations:
                try:
                    if not self.dry_run:
                        self._execute_operation(operation)
                    operation.completed = True
                    bytes_processed += operation.size
                except Exception as e:
                    operation.error = str(e)
                    operation.completed = False
            
            # Create audit log
            if not self.dry_run:
                self._create_audit_log(match, operations, audit_dir)
            
            # Determine success
            success = all(op.completed for op in operations)
            
            result = OrganizeResult(
                torrent_match=match,
                target_dir=target_dir,
                operations=operations,
                success=success,
                bytes_processed=bytes_processed,
                time_taken=time.time() - start_time
            )
            
        except Exception as e:
            result = OrganizeResult(
                torrent_match=match,
                target_dir=target_dir,
                operations=operations,
                success=False,
                error=str(e),
                time_taken=time.time() - start_time
            )
        
        return result
    
    def _plan_data_operations(self, match: TorrentMatch, data_dir: Path) -> List[OrganizeOperation]:
        """Plan the data file operations for a torrent match."""
        operations = []
        
        # Determine if this is a single-file or multi-file torrent
        is_single_file = len(match.files) == 1 and '/' not in match.files[0].torrent_path
        
        for file_match in match.files:
            if is_single_file:
                # Single file torrent - put file directly in data/
                target_path = data_dir / Path(file_match.torrent_path).name
            else:
                # Multi-file torrent - preserve directory structure
                target_path = data_dir / file_match.torrent_path
            
            # Handle collisions
            final_target = self._resolve_collision(target_path, file_match.filesystem_path)
            
            operation = OrganizeOperation(
                source_path=file_match.filesystem_path,
                target_path=final_target,
                action=self.default_action,
                size=file_match.size
            )
            operations.append(operation)
        
        return operations
    
    def _resolve_collision(self, target_path: Path, source_path: Path) -> Path:
        """Resolve file collision based on configured strategy."""
        if not target_path.exists():
            return target_path
        
        if self.collision_strategy == CollisionStrategy.SKIP:
            return target_path  # Will be handled in execution
        
        elif self.collision_strategy == CollisionStrategy.OVERWRITE:
            return target_path
        
        elif self.collision_strategy == CollisionStrategy.RENAME:
            counter = 1
            stem = target_path.stem
            suffix = target_path.suffix
            parent = target_path.parent
            
            while True:
                new_name = f"{stem}_{counter}{suffix}"
                new_path = parent / new_name
                if not new_path.exists():
                    return new_path
                counter += 1
        
        elif self.collision_strategy == CollisionStrategy.COMPARE:
            # Compare files and decide
            try:
                source_stat = source_path.stat()
                target_stat = target_path.stat()
                
                # Prefer newer file, then larger file
                if source_stat.st_mtime > target_stat.st_mtime:
                    return target_path  # Replace
                elif source_stat.st_mtime == target_stat.st_mtime:
                    if source_stat.st_size > target_stat.st_size:
                        return target_path  # Replace
                
                # Keep existing file (skip)
                return target_path
            except (OSError, FileNotFoundError):
                return target_path
        
        return target_path
    
    def _execute_operation(self, operation: OrganizeOperation) -> None:
        """Execute a single file operation."""
        source = operation.source_path
        target = operation.target_path
        
        # Create target directory
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle existing file based on collision strategy
        if target.exists() and self.collision_strategy == CollisionStrategy.SKIP:
            return  # Skip this operation
        
        # Execute the operation
        if operation.action == OrganizeAction.MOVE:
            shutil.move(str(source), str(target))
        
        elif operation.action == OrganizeAction.COPY:
            shutil.copy2(str(source), str(target))
        
        elif operation.action == OrganizeAction.SYMLINK:
            if target.exists():
                target.unlink()
            target.symlink_to(source.resolve())
        
        elif operation.action == OrganizeAction.HARDLINK:
            if target.exists():
                target.unlink()
            target.hardlink_to(source)
        
        else:
            raise ValueError(f"Unknown action: {operation.action}")
    
    def _create_audit_log(self, match: TorrentMatch, operations: List[OrganizeOperation], audit_dir: Path) -> None:
        """Create audit log for the organization operation."""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        audit_file = audit_dir / f'organize_{timestamp}.json'
        
        audit_data = {
            'timestamp': timestamp,
            'torrent_file': str(match.torrent_file),
            'info_hash': match.info_hash,
            'name': match.name,
            'complete': match.complete,
            'verified': match.verified,
            'operations': [
                {
                    'source': str(op.source_path),
                    'target': str(op.target_path),
                    'action': op.action.value,
                    'size': op.size,
                    'completed': op.completed,
                    'error': op.error
                }
                for op in operations
            ],
            'organizer_config': {
                'default_action': self.default_action.value,
                'collision_strategy': self.collision_strategy.value,
                'dry_run': self.dry_run
            }
        }
        
        with open(audit_file, 'w', encoding='utf-8') as f:
            json.dump(audit_data, f, indent=2, ensure_ascii=False)
    
    def check_existing_torrent(self, info_hash: str) -> Optional[Path]:
        """Check if a torrent already exists in the library."""
        torrent_dir = self.library_path / info_hash.lower()
        if torrent_dir.exists():
            return torrent_dir
        return None
    
    def get_library_stats(self) -> Dict:
        """Get statistics about the current library."""
        if not self.library_path.exists():
            return {
                'total_torrents': 0,
                'total_size_bytes': 0,
                'total_files': 0
            }
        
        total_torrents = 0
        total_size = 0
        total_files = 0
        
        for torrent_dir in self.library_path.iterdir():
            if torrent_dir.is_dir() and len(torrent_dir.name) == 40:  # Valid hash length
                total_torrents += 1
                
                data_dir = torrent_dir / 'data'
                if data_dir.exists():
                    for file_path in data_dir.rglob('*'):
                        if file_path.is_file():
                            total_files += 1
                            try:
                                total_size += file_path.stat().st_size
                            except (OSError, FileNotFoundError):
                                pass
        
        return {
            'total_torrents': total_torrents,
            'total_size_bytes': total_size,
            'total_size_human': _format_size(total_size),
            'total_files': total_files
        }


def create_organize_report(results: List[OrganizeResult]) -> Dict:
    """Create a comprehensive organization report."""
    total_torrents = len(results)
    successful = sum(1 for r in results if r.success)
    failed = total_torrents - successful
    
    total_bytes = sum(r.bytes_processed for r in results)
    total_time = sum(r.time_taken for r in results)
    total_operations = sum(len(r.operations) for r in results)
    
    # Categorize operations
    action_counts = {}
    for result in results:
        for op in result.operations:
            action = op.action.value
            action_counts[action] = action_counts.get(action, 0) + 1
    
    return {
        'summary': {
            'total_torrents': total_torrents,
            'successful': successful,
            'failed': failed,
            'success_rate': successful / total_torrents if total_torrents > 0 else 0,
            'total_operations': total_operations,
            'total_bytes_processed': total_bytes,
            'total_size_human': _format_size(total_bytes),
            'total_time_seconds': total_time,
            'average_time_per_torrent': total_time / total_torrents if total_torrents > 0 else 0,
            'action_counts': action_counts
        },
        'results': results
    }


def _format_size(size_bytes: int) -> str:
    """Format byte size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def organize_torrents_cli(matches: List[TorrentMatch],
                         library_path: Optional[Path] = None,
                         action: OrganizeAction = OrganizeAction.MOVE,
                         collision_strategy: CollisionStrategy = CollisionStrategy.COMPARE,
                         dry_run: bool = False,
                         max_workers: int = 4) -> Dict:
    """
    CLI function to organize torrents into the library.
    
    Args:
        matches: List of TorrentMatch objects to organize
        library_path: Library directory (uses config default if None)
        action: Action to take (move, copy, symlink, hardlink)
        collision_strategy: How to handle collisions
        dry_run: If True, don't actually move files
        max_workers: Number of worker threads
        
    Returns:
        Organization report dictionary
    """
    organizer = LibraryOrganizer(
        library_path=library_path,
        default_action=action,
        collision_strategy=collision_strategy,
        dry_run=dry_run,
        max_workers=max_workers
    )
    
    def progress_callback(message: str, percent: float):
        print(f"  {message} ({percent:.1f}%)")
    
    print(f"Organizing {len(matches)} torrents into library: {organizer.library_path}")
    if dry_run:
        print("DRY RUN MODE - No files will be moved")
    
    results = organizer.organize_matches(matches, progress_callback)
    
    return create_organize_report(results)