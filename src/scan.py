"""
Directory scanning and torrent matching functionality.

This module provides tools for:
- Scanning directories for media files and matching them to torrents
- Verifying file integrity using piece hashes
- Finding existing data for torrent files
- Organizing and reporting on scan results
"""

import os
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, NamedTuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .utils import read_torrent_file, get_torrent_info, is_media_file


@dataclass
class FileMatch:
    """Represents a matched file between torrent and filesystem."""
    torrent_path: str  # Path within torrent
    filesystem_path: Path  # Actual file path
    size: int
    verified: Optional[bool] = None  # None = not checked, True/False = hash verified


@dataclass 
class TorrentMatch:
    """Represents a complete torrent match result."""
    torrent_file: Path
    info_hash: str
    name: str
    root_path: Optional[Path]  # Root directory containing the files
    files: List[FileMatch]
    complete: bool  # All files found
    verified: Optional[bool] = None  # None = not checked, True/False = all pieces verified
    

class TorrentScanner:
    """Scanner for matching torrents to filesystem data."""
    
    def __init__(self, verify_hashes: bool = False, max_workers: int = 4):
        self.verify_hashes = verify_hashes
        self.max_workers = max_workers
        self._file_cache: Dict[int, Set[Path]] = {}  # size -> set of paths
    
    def scan_directory(self, directory: Path, torrents: List[Path], 
                      progress_callback=None) -> List[TorrentMatch]:
        """
        Scan directory for files matching the given torrents.
        
        Args:
            directory: Root directory to scan
            torrents: List of torrent file paths
            progress_callback: Optional callback function for progress updates
            
        Returns:
            List of TorrentMatch results
        """
        directory = Path(directory)
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        # Build file cache by size for faster matching
        if progress_callback:
            progress_callback(f"Building file index for {directory}")
        self._build_file_cache(directory)
        
        results = []
        total_torrents = len(torrents)
        
        for i, torrent_path in enumerate(torrents):
            if progress_callback:
                progress_callback(f"Processing torrent {i+1}/{total_torrents}: {torrent_path.name}")
            
            try:
                match = self._match_torrent(torrent_path, directory)
                results.append(match)
            except Exception as e:
                # Create failed match for error reporting
                match = TorrentMatch(
                    torrent_file=torrent_path,
                    info_hash="unknown",
                    name=torrent_path.stem,
                    root_path=None,
                    files=[],
                    complete=False
                )
                results.append(match)
                if progress_callback:
                    progress_callback(f"Error processing {torrent_path}: {e}")
        
        return results
    
    def _build_file_cache(self, directory: Path) -> None:
        """Build cache of files indexed by size for faster matching."""
        self._file_cache.clear()
        
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                try:
                    size = file_path.stat().st_size
                    if size not in self._file_cache:
                        self._file_cache[size] = set()
                    self._file_cache[size].add(file_path)
                except (OSError, PermissionError):
                    continue
    
    def _match_torrent(self, torrent_path: Path, search_directory: Path) -> TorrentMatch:
        """Match a single torrent to files in the directory."""
        torrent_info = get_torrent_info(torrent_path)
        torrent_data = read_torrent_file(torrent_path)
        
        info_hash = torrent_info['info_hash']
        name = torrent_info['name']
        torrent_files = torrent_info['files']
        
        # Find potential root directories
        potential_roots = self._find_potential_roots(name, search_directory, torrent_files)
        
        best_match = None
        best_score = 0
        
        # Try each potential root
        for root_path in potential_roots:
            match = self._try_match_in_root(torrent_path, root_path, torrent_files, 
                                          info_hash, name, torrent_data)
            score = self._calculate_match_score(match)
            
            if score > best_score:
                best_score = score
                best_match = match
        
        # If no good match found, try direct file matching
        if not best_match or best_score < 0.5:
            direct_match = self._try_direct_file_matching(torrent_path, search_directory, 
                                                        torrent_files, info_hash, name, torrent_data)
            direct_score = self._calculate_match_score(direct_match)
            
            if direct_score > best_score:
                best_match = direct_match
        
        return best_match or TorrentMatch(
            torrent_file=torrent_path,
            info_hash=info_hash,
            name=name,
            root_path=None,
            files=[],
            complete=False
        )
    
    def _find_potential_roots(self, torrent_name: str, search_directory: Path, 
                            torrent_files: List[Dict]) -> List[Path]:
        """Find potential root directories for this torrent."""
        potential_roots = [search_directory]  # Always try the root
        
        # Look for directories with similar names
        for item in search_directory.iterdir():
            if item.is_dir():
                dir_name = item.name.lower()
                torrent_name_lower = torrent_name.lower()
                
                # Exact match
                if dir_name == torrent_name_lower:
                    potential_roots.insert(0, item)  # Prioritize exact matches
                # Partial match (contains torrent name or vice versa)
                elif (torrent_name_lower in dir_name or dir_name in torrent_name_lower):
                    potential_roots.append(item)
        
        return potential_roots
    
    def _try_match_in_root(self, torrent_path: Path, root_path: Path, 
                          torrent_files: List[Dict], info_hash: str, name: str,
                          torrent_data: Dict) -> TorrentMatch:
        """Try to match torrent files within a specific root directory."""
        file_matches = []
        
        for torrent_file in torrent_files:
            torrent_file_path = torrent_file['path']
            torrent_file_size = torrent_file['size']
            
            # Try different path matching strategies
            candidates = self._find_file_candidates(root_path, torrent_file_path, torrent_file_size)
            
            best_candidate = None
            if candidates:
                # Prefer exact name matches, then size matches
                best_candidate = self._select_best_candidate(candidates, torrent_file_path)
            
            if best_candidate:
                file_match = FileMatch(
                    torrent_path=torrent_file_path,
                    filesystem_path=best_candidate,
                    size=torrent_file_size
                )
                file_matches.append(file_match)
        
        complete = len(file_matches) == len(torrent_files)
        
        match = TorrentMatch(
            torrent_file=torrent_path,
            info_hash=info_hash,
            name=name,
            root_path=root_path,
            files=file_matches,
            complete=complete
        )
        
        # Verify hashes if requested and match is complete
        if self.verify_hashes and complete:
            match.verified = self._verify_torrent_pieces(match, torrent_data)
        
        return match
    
    def _try_direct_file_matching(self, torrent_path: Path, search_directory: Path,
                                torrent_files: List[Dict], info_hash: str, name: str,
                                torrent_data: Dict) -> TorrentMatch:
        """Try to match torrent files directly by name and size across the entire directory."""
        file_matches = []
        
        for torrent_file in torrent_files:
            torrent_file_path = torrent_file['path']
            torrent_file_size = torrent_file['size']
            
            # Get filename from torrent path
            filename = Path(torrent_file_path).name
            
            # Look for files with this exact name and size
            candidates = []
            if torrent_file_size in self._file_cache:
                for candidate_path in self._file_cache[torrent_file_size]:
                    if candidate_path.name == filename:
                        candidates.append(candidate_path)
            
            if candidates:
                # If multiple candidates, prefer the one in a directory structure that makes sense
                best_candidate = self._select_best_candidate(candidates, torrent_file_path)
                
                file_match = FileMatch(
                    torrent_path=torrent_file_path,
                    filesystem_path=best_candidate,
                    size=torrent_file_size
                )
                file_matches.append(file_match)
        
        complete = len(file_matches) == len(torrent_files)
        
        # Try to determine root path from matched files
        root_path = self._infer_root_path(file_matches) if file_matches else None
        
        match = TorrentMatch(
            torrent_file=torrent_path,
            info_hash=info_hash,
            name=name,
            root_path=root_path,
            files=file_matches,
            complete=complete
        )
        
        # Verify hashes if requested and match is complete
        if self.verify_hashes and complete:
            match.verified = self._verify_torrent_pieces(match, torrent_data)
        
        return match
    
    def _find_file_candidates(self, root_path: Path, torrent_file_path: str, 
                            expected_size: int) -> List[Path]:
        """Find candidate files for a torrent file path."""
        candidates = []
        
        # Strategy 1: Direct path match
        direct_path = root_path / torrent_file_path
        if direct_path.exists() and direct_path.stat().st_size == expected_size:
            candidates.append(direct_path)
        
        # Strategy 2: Filename match with size verification
        filename = Path(torrent_file_path).name
        if expected_size in self._file_cache:
            for candidate_path in self._file_cache[expected_size]:
                if (candidate_path.name == filename and 
                    self._is_path_under(candidate_path, root_path)):
                    candidates.append(candidate_path)
        
        return candidates
    
    def _select_best_candidate(self, candidates: List[Path], torrent_path: str) -> Path:
        """Select the best candidate from multiple options."""
        if len(candidates) == 1:
            return candidates[0]
        
        # Prefer candidates with path structures closer to the torrent structure
        torrent_parts = Path(torrent_path).parts
        best_candidate = candidates[0]
        best_score = 0
        
        for candidate in candidates:
            score = 0
            candidate_parts = candidate.parts
            
            # Score based on matching path components
            for i, part in enumerate(reversed(torrent_parts)):
                if i < len(candidate_parts) and part == candidate_parts[-(i+1)]:
                    score += 1
                else:
                    break
            
            if score > best_score:
                best_score = score
                best_candidate = candidate
        
        return best_candidate
    
    def _infer_root_path(self, file_matches: List[FileMatch]) -> Optional[Path]:
        """Infer the root path from matched files."""
        if not file_matches:
            return None
        
        # Find the common parent directory
        paths = [match.filesystem_path.parent for match in file_matches]
        common_parent = paths[0]
        
        for path in paths[1:]:
            # Find common parent
            while not self._is_path_under(path, common_parent):
                common_parent = common_parent.parent
                if common_parent == common_parent.parent:  # Reached filesystem root
                    break
        
        return common_parent
    
    def _is_path_under(self, path: Path, parent: Path) -> bool:
        """Check if path is under parent directory."""
        try:
            path.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            return False
    
    def _calculate_match_score(self, match: TorrentMatch) -> float:
        """Calculate a match quality score (0.0 to 1.0)."""
        if not match.files:
            return 0.0
        
        # Base score on completeness
        total_files = len(match.files)
        if hasattr(match, '_expected_files'):
            completeness = total_files / match._expected_files
        else:
            completeness = 1.0 if match.complete else 0.8
        
        # Bonus for having a sensible root path
        root_bonus = 0.1 if match.root_path else 0.0
        
        # Bonus for hash verification
        verify_bonus = 0.1 if match.verified else 0.0
        
        return min(1.0, completeness + root_bonus + verify_bonus)
    
    def _verify_torrent_pieces(self, match: TorrentMatch, torrent_data: Dict) -> bool:
        """Verify torrent pieces against actual file data."""
        info = torrent_data.get('info', {})
        piece_length = info.get('piece length', 0)
        pieces = info.get('pieces', b'')
        
        if not piece_length or not pieces:
            return False
        
        # Create ordered list of files
        ordered_files = sorted(match.files, key=lambda f: f.torrent_path)
        
        piece_index = 0
        piece_offset = 0
        current_piece_hash = hashlib.sha1()
        
        for file_match in ordered_files:
            try:
                with open(file_match.filesystem_path, 'rb') as f:
                    while True:
                        # Calculate how much to read
                        remaining_in_piece = piece_length - piece_offset
                        chunk = f.read(min(8192, remaining_in_piece))
                        
                        if not chunk:
                            break
                        
                        current_piece_hash.update(chunk)
                        piece_offset += len(chunk)
                        
                        # Check if piece is complete
                        if piece_offset >= piece_length:
                            # Verify this piece
                            expected_hash = pieces[piece_index * 20:(piece_index + 1) * 20]
                            actual_hash = current_piece_hash.digest()
                            
                            if actual_hash != expected_hash:
                                return False
                            
                            # Move to next piece
                            piece_index += 1
                            piece_offset = 0
                            current_piece_hash = hashlib.sha1()
                        
            except (OSError, PermissionError):
                return False
        
        # Verify final piece if partial
        if piece_offset > 0:
            expected_hash = pieces[piece_index * 20:(piece_index + 1) * 20]
            actual_hash = current_piece_hash.digest()
            return actual_hash == expected_hash
        
        return True


def create_scan_report(matches: List[TorrentMatch]) -> Dict:
    """Create a comprehensive scan report."""
    total_torrents = len(matches)
    complete_matches = sum(1 for m in matches if m.complete)
    verified_matches = sum(1 for m in matches if m.verified is True)
    failed_matches = sum(1 for m in matches if not m.files)
    
    total_files = sum(len(m.files) for m in matches)
    total_size = sum(sum(f.size for f in m.files) for m in matches)
    
    return {
        'summary': {
            'total_torrents': total_torrents,
            'complete_matches': complete_matches,
            'verified_matches': verified_matches,
            'failed_matches': failed_matches,
            'completion_rate': complete_matches / total_torrents if total_torrents > 0 else 0,
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_human': _format_size(total_size)
        },
        'matches': matches
    }


def _format_size(size_bytes: int) -> str:
    """Format byte size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def scan_torrents_cli(torrent_dir: Path, data_dir: Path, verify_hashes: bool = False,
                     max_workers: int = 4) -> Dict:
    """
    CLI function to scan torrents against a data directory.
    
    Args:
        torrent_dir: Directory containing .torrent files
        data_dir: Directory containing media files
        verify_hashes: Whether to verify piece hashes
        max_workers: Number of worker threads
        
    Returns:
        Scan report dictionary
    """
    from .utils import scan_torrent_files
    
    print(f"Scanning for torrents in: {torrent_dir}")
    torrent_files = scan_torrent_files(torrent_dir)
    print(f"Found {len(torrent_files)} torrent files")
    
    if not torrent_files:
        return create_scan_report([])
    
    print(f"Scanning data directory: {data_dir}")
    scanner = TorrentScanner(verify_hashes=verify_hashes, max_workers=max_workers)
    
    def progress_callback(message: str):
        print(f"  {message}")
    
    matches = scanner.scan_directory(data_dir, torrent_files, progress_callback)
    
    return create_scan_report(matches)