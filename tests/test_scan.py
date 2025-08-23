"""Tests for scanning functionality."""

import pytest
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

from src.scan import (
    TorrentScanner, 
    FileMatch, 
    TorrentMatch,
    create_scan_report,
    _format_size
)
from src.utils import _encode_bencode


class TestTorrentScanner:
    """Test TorrentScanner functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.scanner = TorrentScanner(verify_hashes=False)
    
    def test_build_file_cache(self):
        """Test building file cache by size."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test files
            (temp_path / 'file1.txt').write_text('hello')
            (temp_path / 'file2.txt').write_text('world')
            (temp_path / 'file3.txt').write_text('hello')  # Same size as file1
            
            self.scanner._build_file_cache(temp_path)
            
            # Check cache structure
            assert 5 in self.scanner._file_cache  # "hello" and "world" are 5 chars
            assert len(self.scanner._file_cache[5]) == 3  # All three files
    
    def test_is_path_under(self):
        """Test path hierarchy checking."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            subdir = temp_path / 'subdir'
            subdir.mkdir()
            file_path = subdir / 'file.txt'
            file_path.touch()
            
            assert self.scanner._is_path_under(file_path, temp_path)
            assert self.scanner._is_path_under(subdir, temp_path)
            assert not self.scanner._is_path_under(temp_path, subdir)
    
    def test_infer_root_path(self):
        """Test root path inference from file matches."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create directory structure
            movie_dir = temp_path / 'Movie (2023)'
            movie_dir.mkdir()
            
            file1 = movie_dir / 'movie.mkv'
            file2 = movie_dir / 'extras' / 'trailer.mp4'
            file2.parent.mkdir()
            file1.touch()
            file2.touch()
            
            # Create file matches
            matches = [
                FileMatch('movie.mkv', file1, 1000),
                FileMatch('extras/trailer.mp4', file2, 500)
            ]
            
            root = self.scanner._infer_root_path(matches)
            assert root == movie_dir
    
    def test_select_best_candidate(self):
        """Test candidate selection logic."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create candidates with different path structures
            candidate1 = temp_path / 'random' / 'movie.mkv'
            candidate2 = temp_path / 'Movie (2023)' / 'movie.mkv'
            candidate3 = temp_path / 'Movie (2023)' / 'extras' / 'movie.mkv'  # Wrong location
            
            candidate1.parent.mkdir(parents=True)
            candidate2.parent.mkdir(parents=True)
            candidate3.parent.mkdir(parents=True)
            candidate1.touch()
            candidate2.touch()
            candidate3.touch()
            
            candidates = [candidate1, candidate2, candidate3]
            
            # Should prefer the one with better path structure
            best = self.scanner._select_best_candidate(candidates, 'Movie (2023)/movie.mkv')
            assert best == candidate2
    
    @patch('src.scan.get_torrent_info')
    @patch('src.scan.read_torrent_file')
    def test_match_torrent_complete_match(self, mock_read_torrent, mock_get_info):
        """Test complete torrent matching."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            torrent_path = temp_path / 'test.torrent'
            torrent_path.touch()
            
            # Create actual file structure
            movie_dir = temp_path / 'data' / 'Test Movie'
            movie_dir.mkdir(parents=True)
            movie_file = movie_dir / 'movie.mkv'
            movie_file.write_bytes(b'x' * 1000)  # 1000 bytes
            
            # Mock torrent info
            mock_get_info.return_value = {
                'info_hash': 'abc123',
                'name': 'Test Movie',
                'files': [{'path': 'Test Movie/movie.mkv', 'size': 1000}]
            }
            mock_read_torrent.return_value = {'info': {'name': 'Test Movie'}}
            
            # Build cache and match
            self.scanner._build_file_cache(temp_path / 'data')
            match = self.scanner._match_torrent(torrent_path, temp_path / 'data')
            
            assert match.complete
            assert len(match.files) == 1
            assert match.files[0].filesystem_path == movie_file
            assert match.root_path == movie_dir  # Should be the movie directory itself
    
    def test_calculate_match_score(self):
        """Test match quality scoring."""
        # Complete match
        complete_match = TorrentMatch(
            torrent_file=Path('test.torrent'),
            info_hash='abc123',
            name='Test',
            root_path=Path('/test'),
            files=[FileMatch('file1.txt', Path('/test/file1.txt'), 100)],
            complete=True,
            verified=True
        )
        
        score = self.scanner._calculate_match_score(complete_match)
        assert score > 0.8  # Should be high score
        
        # Incomplete match
        incomplete_match = TorrentMatch(
            torrent_file=Path('test.torrent'),
            info_hash='abc123', 
            name='Test',
            root_path=None,
            files=[],
            complete=False
        )
        
        score = self.scanner._calculate_match_score(incomplete_match)
        assert score == 0.0


class TestReporting:
    """Test reporting functionality."""
    
    def test_format_size(self):
        """Test size formatting."""
        assert _format_size(1024) == '1.0 KB'
        assert _format_size(1024 * 1024) == '1.0 MB'
        assert _format_size(1024 * 1024 * 1024) == '1.0 GB'
        assert _format_size(500) == '500.0 B'
    
    def test_create_scan_report(self):
        """Test scan report creation."""
        # Create test matches
        complete_match = TorrentMatch(
            torrent_file=Path('test1.torrent'),
            info_hash='abc123',
            name='Test1',
            root_path=Path('/test1'),
            files=[
                FileMatch('file1.txt', Path('/test1/file1.txt'), 1000),
                FileMatch('file2.txt', Path('/test1/file2.txt'), 2000)
            ],
            complete=True,
            verified=True
        )
        
        incomplete_match = TorrentMatch(
            torrent_file=Path('test2.torrent'),
            info_hash='def456',
            name='Test2',
            root_path=Path('/test2'),
            files=[FileMatch('file3.txt', Path('/test2/file3.txt'), 500)],
            complete=False
        )
        
        failed_match = TorrentMatch(
            torrent_file=Path('test3.torrent'),
            info_hash='ghi789',
            name='Test3',
            root_path=None,
            files=[],
            complete=False
        )
        
        matches = [complete_match, incomplete_match, failed_match]
        report = create_scan_report(matches)
        
        summary = report['summary']
        assert summary['total_torrents'] == 3
        assert summary['complete_matches'] == 1
        assert summary['verified_matches'] == 1
        assert summary['failed_matches'] == 1
        assert summary['completion_rate'] == 1/3
        assert summary['total_files'] == 3
        assert summary['total_size_bytes'] == 3500
        assert 'KB' in summary['total_size_human']


class TestFileMatch:
    """Test FileMatch dataclass."""
    
    def test_file_match_creation(self):
        """Test FileMatch creation."""
        match = FileMatch(
            torrent_path='movie/file.mkv',
            filesystem_path=Path('/data/movie/file.mkv'),
            size=1000000,
            verified=True
        )
        
        assert match.torrent_path == 'movie/file.mkv'
        assert match.filesystem_path == Path('/data/movie/file.mkv')
        assert match.size == 1000000
        assert match.verified is True


class TestTorrentMatch:
    """Test TorrentMatch dataclass."""
    
    def test_torrent_match_creation(self):
        """Test TorrentMatch creation."""
        files = [
            FileMatch('file1.txt', Path('/data/file1.txt'), 100),
            FileMatch('file2.txt', Path('/data/file2.txt'), 200)
        ]
        
        match = TorrentMatch(
            torrent_file=Path('/torrents/test.torrent'),
            info_hash='abcdef123456',
            name='Test Torrent',
            root_path=Path('/data'),
            files=files,
            complete=True,
            verified=False
        )
        
        assert match.torrent_file == Path('/torrents/test.torrent')
        assert match.info_hash == 'abcdef123456'
        assert match.name == 'Test Torrent'
        assert match.root_path == Path('/data')
        assert len(match.files) == 2
        assert match.complete is True
        assert match.verified is False