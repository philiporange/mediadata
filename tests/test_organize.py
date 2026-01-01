"""Tests for organization functionality."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

from mediadata.organize import (
    LibraryOrganizer,
    OrganizeAction,
    CollisionStrategy,
    OrganizeOperation,
    OrganizeResult,
    create_organize_report,
    _format_size
)
from mediadata.scan import TorrentMatch, FileMatch


class TestLibraryOrganizer:
    """Test LibraryOrganizer functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = None
    
    def teardown_method(self):
        """Clean up after tests."""
        if self.temp_dir:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_test_organizer(self, **kwargs):
        """Create a test organizer with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        library_path = Path(self.temp_dir) / 'library'
        
        defaults = {
            'library_path': library_path,
            'default_action': OrganizeAction.COPY,  # Use copy for tests
            'collision_strategy': CollisionStrategy.COMPARE,
            'dry_run': False
        }
        defaults.update(kwargs)
        
        organizer = LibraryOrganizer(**defaults)
        return organizer, library_path
    
    def test_library_creation(self):
        """Test library directory creation."""
        organizer, library_path = self._create_test_organizer()
        assert library_path.exists()
        assert library_path.is_dir()
    
    def test_dry_run_mode(self):
        """Test dry run mode doesn't create directories."""
        organizer, library_path = self._create_test_organizer(dry_run=True)
        # Directory should not be created in dry run mode
        assert not library_path.exists()
    
    def test_organize_single_file_torrent(self):
        """Test organizing a single-file torrent."""
        organizer, library_path = self._create_test_organizer()
        
        with tempfile.TemporaryDirectory() as temp_data:
            temp_path = Path(temp_data)
            
            # Create test files
            torrent_file = temp_path / 'test.torrent'
            torrent_file.write_text('fake torrent data')
            
            data_file = temp_path / 'movie.mkv'
            data_file.write_bytes(b'x' * 1000)
            
            # Create torrent match
            match = TorrentMatch(
                torrent_file=torrent_file,
                info_hash='abcdef1234567890' * 2 + 'abcdef12',  # 40 char hash
                name='Test Movie',
                root_path=temp_path,
                files=[FileMatch('movie.mkv', data_file, 1000)],
                complete=True
            )
            
            # Organize
            result = organizer.organize_match(match)
            
            # Verify result
            assert result.success
            assert len(result.operations) == 2  # torrent + data file
            
            # Check library structure
            expected_dir = library_path / match.info_hash.lower()
            assert expected_dir.exists()
            assert (expected_dir / 'data').exists()
            assert (expected_dir / 'metadata').exists()
            assert (expected_dir / 'metadata' / 'audit').exists()
            
            # Check files
            assert (expected_dir / 'source.torrent').exists()
            assert (expected_dir / 'data' / 'movie.mkv').exists()
    
    def test_organize_multi_file_torrent(self):
        """Test organizing a multi-file torrent."""
        organizer, library_path = self._create_test_organizer()
        
        with tempfile.TemporaryDirectory() as temp_data:
            temp_path = Path(temp_data)
            
            # Create test structure
            torrent_file = temp_path / 'test.torrent'
            torrent_file.write_text('fake torrent data')
            
            movie_dir = temp_path / 'Test Movie'
            movie_dir.mkdir()
            
            main_file = movie_dir / 'movie.mkv'
            main_file.write_bytes(b'x' * 2000)
            
            extras_dir = movie_dir / 'extras'
            extras_dir.mkdir()
            trailer_file = extras_dir / 'trailer.mp4'
            trailer_file.write_bytes(b'y' * 500)
            
            # Create torrent match
            match = TorrentMatch(
                torrent_file=torrent_file,
                info_hash='fedcba0987654321' * 2 + 'fedcba09',
                name='Test Movie',
                root_path=temp_path,
                files=[
                    FileMatch('Test Movie/movie.mkv', main_file, 2000),
                    FileMatch('Test Movie/extras/trailer.mp4', trailer_file, 500)
                ],
                complete=True
            )
            
            # Organize
            result = organizer.organize_match(match)
            
            # Verify result
            assert result.success
            assert len(result.operations) == 3  # torrent + 2 data files
            
            # Check structure preservation
            expected_dir = library_path / match.info_hash.lower()
            assert (expected_dir / 'data' / 'Test Movie' / 'movie.mkv').exists()
            assert (expected_dir / 'data' / 'Test Movie' / 'extras' / 'trailer.mp4').exists()
    
    def test_collision_handling_rename(self):
        """Test collision handling with rename strategy."""
        organizer, library_path = self._create_test_organizer(
            collision_strategy=CollisionStrategy.RENAME
        )
        
        with tempfile.TemporaryDirectory() as temp_data:
            temp_path = Path(temp_data)
            
            # Create existing file in library
            info_hash = 'abc123def456' * 3 + 'abc123de'
            target_dir = library_path / info_hash.lower()
            data_dir = target_dir / 'data'
            data_dir.mkdir(parents=True)
            existing_file = data_dir / 'movie.mkv'
            existing_file.write_bytes(b'existing data')
            
            # Create new torrent file
            torrent_file = temp_path / 'test.torrent'
            torrent_file.write_text('fake torrent')
            
            new_file = temp_path / 'movie.mkv'
            new_file.write_bytes(b'new data')
            
            match = TorrentMatch(
                torrent_file=torrent_file,
                info_hash=info_hash,
                name='Test Movie',
                root_path=temp_path,
                files=[FileMatch('movie.mkv', new_file, 8)],
                complete=True
            )
            
            # Plan operations to see renamed target
            operations = organizer._plan_data_operations(match, data_dir)
            
            # Should rename the new file
            assert len(operations) == 1
            assert operations[0].target_path.name == 'movie_1.mkv'
    
    def test_collision_handling_skip(self):
        """Test collision handling with skip strategy."""
        organizer, library_path = self._create_test_organizer(
            collision_strategy=CollisionStrategy.SKIP
        )
        
        with tempfile.TemporaryDirectory() as temp_data:
            temp_path = Path(temp_data)
            
            # Create files
            torrent_file = temp_path / 'test.torrent'
            torrent_file.write_text('fake torrent')
            
            data_file = temp_path / 'movie.mkv'
            data_file.write_bytes(b'data')
            
            # Pre-create target with same name
            info_hash = 'skip123test456' * 2 + 'skip123t'
            target_dir = library_path / info_hash.lower()
            data_dir = target_dir / 'data'
            data_dir.mkdir(parents=True)
            (data_dir / 'movie.mkv').write_bytes(b'existing')
            
            match = TorrentMatch(
                torrent_file=torrent_file,
                info_hash=info_hash,
                name='Test',
                root_path=temp_path,
                files=[FileMatch('movie.mkv', data_file, 4)],
                complete=True
            )
            
            result = organizer.organize_match(match)
            
            # Should succeed but skip the data file operation
            assert result.success
            # Original content should be preserved
            assert (data_dir / 'movie.mkv').read_bytes() == b'existing'
    
    def test_audit_log_creation(self):
        """Test audit log creation."""
        organizer, library_path = self._create_test_organizer()
        
        with tempfile.TemporaryDirectory() as temp_data:
            temp_path = Path(temp_data)
            
            torrent_file = temp_path / 'test.torrent'
            torrent_file.write_text('fake torrent')
            
            data_file = temp_path / 'data.txt'
            data_file.write_text('test data')
            
            match = TorrentMatch(
                torrent_file=torrent_file,
                info_hash='audit123test456' * 2 + 'audit123',
                name='Test Audit',
                root_path=temp_path,
                files=[FileMatch('data.txt', data_file, 9)],
                complete=True,
                verified=True
            )
            
            result = organizer.organize_match(match)
            
            # Check audit log was created
            audit_dir = result.target_dir / 'metadata' / 'audit'
            audit_files = list(audit_dir.glob('organize_*.json'))
            assert len(audit_files) == 1
            
            # Check audit content
            with open(audit_files[0], 'r') as f:
                audit_data = json.load(f)
            
            assert audit_data['info_hash'] == match.info_hash
            assert audit_data['name'] == match.name
            assert audit_data['complete'] == True
            assert audit_data['verified'] == True
            assert len(audit_data['operations']) == 2
    
    def test_check_existing_torrent(self):
        """Test checking for existing torrents."""
        organizer, library_path = self._create_test_organizer()
        
        # Create existing torrent directory
        existing_hash = 'existing123456' * 2 + 'existing'
        existing_dir = library_path / existing_hash.lower()
        existing_dir.mkdir(parents=True)
        
        # Test existing
        result = organizer.check_existing_torrent(existing_hash)
        assert result == existing_dir
        
        # Test non-existing
        result = organizer.check_existing_torrent('nonexistent123')
        assert result is None
    
    def test_library_stats(self):
        """Test library statistics calculation."""
        organizer, library_path = self._create_test_organizer()
        
        # Empty library
        stats = organizer.get_library_stats()
        assert stats['total_torrents'] == 0
        assert stats['total_files'] == 0
        assert stats['total_size_bytes'] == 0
        
        # Add some test data
        hash1 = 'a' * 40
        hash2 = 'b' * 40
        
        # Create torrent directories with data
        (library_path / hash1 / 'data').mkdir(parents=True)
        (library_path / hash2 / 'data').mkdir(parents=True)
        
        (library_path / hash1 / 'data' / 'file1.txt').write_bytes(b'x' * 100)
        (library_path / hash1 / 'data' / 'file2.txt').write_bytes(b'y' * 200)
        (library_path / hash2 / 'data' / 'file3.txt').write_bytes(b'z' * 300)
        
        stats = organizer.get_library_stats()
        assert stats['total_torrents'] == 2
        assert stats['total_files'] == 3
        assert stats['total_size_bytes'] == 600


class TestOrganizeOperations:
    """Test organize operation classes."""
    
    def test_organize_operation(self):
        """Test OrganizeOperation dataclass."""
        op = OrganizeOperation(
            source_path=Path('/source/file.txt'),
            target_path=Path('/target/file.txt'),
            action=OrganizeAction.MOVE,
            size=1000,
            completed=True,
            error="Test error"
        )
        
        assert op.source_path == Path('/source/file.txt')
        assert op.target_path == Path('/target/file.txt')
        assert op.action == OrganizeAction.MOVE
        assert op.size == 1000
        assert op.completed is True
        assert op.error == "Test error"
    
    def test_organize_result(self):
        """Test OrganizeResult dataclass."""
        match = TorrentMatch(
            torrent_file=Path('/test.torrent'),
            info_hash='test123',
            name='Test',
            root_path=None,
            files=[],
            complete=False
        )
        
        result = OrganizeResult(
            torrent_match=match,
            target_dir=Path('/library/test123'),
            operations=[],
            success=True,
            error=None,
            bytes_processed=1000,
            time_taken=5.0
        )
        
        assert result.torrent_match == match
        assert result.target_dir == Path('/library/test123')
        assert result.success is True
        assert result.bytes_processed == 1000
        assert result.time_taken == 5.0


class TestReporting:
    """Test reporting functionality."""
    
    def test_format_size(self):
        """Test size formatting."""
        assert _format_size(512) == '512.0 B'
        assert _format_size(1536) == '1.5 KB'  # 1.5 * 1024
        assert _format_size(2097152) == '2.0 MB'  # 2 * 1024^2
    
    def test_create_organize_report(self):
        """Test organize report creation."""
        # Create mock results
        match1 = TorrentMatch(
            torrent_file=Path('/test1.torrent'),
            info_hash='hash1',
            name='Test1',
            root_path=None,
            files=[],
            complete=True
        )
        
        match2 = TorrentMatch(
            torrent_file=Path('/test2.torrent'), 
            info_hash='hash2',
            name='Test2',
            root_path=None,
            files=[],
            complete=False
        )
        
        op1 = OrganizeOperation(Path('/src1'), Path('/dst1'), OrganizeAction.MOVE, 1000, True)
        op2 = OrganizeOperation(Path('/src2'), Path('/dst2'), OrganizeAction.COPY, 2000, True)
        op3 = OrganizeOperation(Path('/src3'), Path('/dst3'), OrganizeAction.MOVE, 500, False, "Error")
        
        results = [
            OrganizeResult(match1, Path('/lib/hash1'), [op1, op2], True, None, 3000, 2.0),
            OrganizeResult(match2, Path('/lib/hash2'), [op3], False, "Failed", 0, 1.0)
        ]
        
        report = create_organize_report(results)
        
        summary = report['summary']
        assert summary['total_torrents'] == 2
        assert summary['successful'] == 1
        assert summary['failed'] == 1
        assert summary['success_rate'] == 0.5
        assert summary['total_operations'] == 3
        assert summary['total_bytes_processed'] == 3000
        assert summary['total_time_seconds'] == 3.0
        assert summary['average_time_per_torrent'] == 1.5
        assert summary['action_counts']['move'] == 2
        assert summary['action_counts']['copy'] == 1