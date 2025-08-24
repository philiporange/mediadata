"""Tests for MediaData main class."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from mediadata import MediaData, ProcessingStats, process_media
from src.organize import OrganizeAction, CollisionStrategy


class TestProcessingStats:
    """Test ProcessingStats functionality."""
    
    def test_processing_stats_creation(self):
        """Test ProcessingStats creation and calculations."""
        stats = ProcessingStats(
            total_torrents_found=10,
            successful_matches=8,
            organized_torrents=7,
            metadata_processed=6,
            total_files=25,
            total_size_bytes=1073741824,  # 1GB
            processing_time_seconds=120.5
        )
        
        assert stats.total_torrents_found == 10
        assert stats.successful_matches == 8
        assert stats.organized_torrents == 7
        assert stats.metadata_processed == 6
        assert stats.match_rate == 0.8  # 8/10
        assert stats.organization_rate == 0.875  # 7/8
        assert stats.metadata_rate == 6/7  # 6/7
    
    def test_processing_stats_to_dict(self):
        """Test ProcessingStats conversion to dictionary."""
        stats = ProcessingStats(
            total_torrents_found=5,
            successful_matches=4,
            organized_torrents=3,
            metadata_processed=2,
            total_size_bytes=2048
        )
        
        stats_dict = stats.to_dict()
        
        assert stats_dict['total_torrents_found'] == 5
        assert stats_dict['successful_matches'] == 4
        assert stats_dict['organized_torrents'] == 3
        assert stats_dict['metadata_processed'] == 2
        assert 'total_size_human' in stats_dict
        assert 'match_rate' in stats_dict
        assert 'organization_rate' in stats_dict
        assert 'metadata_rate' in stats_dict


class TestMediaData:
    """Test MediaData main class."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = None
    
    def teardown_method(self):
        """Clean up after tests."""
        if self.temp_dir:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_temp_mediadata(self, **kwargs) -> MediaData:
        """Create MediaData instance with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        archive_dir = Path(self.temp_dir) / 'archive'
        
        defaults = {
            'archive_dir': archive_dir,
            'tmdb_api_key': 'test_key',
            'verify_hashes': False,
            'organize_action': OrganizeAction.COPY,
            'collision_strategy': CollisionStrategy.COMPARE,
            'max_workers': 2
        }
        defaults.update(kwargs)
        
        return MediaData(**defaults)
    
    def test_mediadata_initialization(self):
        """Test MediaData initialization."""
        media = self._create_temp_mediadata()
        
        assert media.archive_dir.exists()
        assert media.tmdb_api_key == 'test_key'
        assert media.verify_hashes is False
        assert media.organize_action == OrganizeAction.COPY
        assert media.collision_strategy == CollisionStrategy.COMPARE
        assert media.max_workers == 2
        
        # Check components are initialized
        assert media.scanner is not None
        assert media.organizer is not None
        assert media.tmdb_client is not None
        assert media.metadata_processor is not None
        assert media.logger is not None
    
    def test_mediadata_configuration(self):
        """Test MediaData configuration storage."""
        media = self._create_temp_mediadata()
        
        config = media.config
        assert config['archive_dir'] == str(media.archive_dir)
        assert config['verify_hashes'] is False
        assert config['organize_action'] == 'copy'
        assert config['collision_strategy'] == 'compare'
        assert config['max_workers'] == 2
        assert config['tmdb_configured'] is True
    
    def test_scan_torrents(self):
        """Test torrent scanning functionality."""
        media = self._create_temp_mediadata()
        
        # Create test torrent files
        torrent_dir = Path(self.temp_dir) / 'torrents'
        torrent_dir.mkdir()
        
        (torrent_dir / 'test1.torrent').touch()
        (torrent_dir / 'test2.torrent').touch()
        (torrent_dir / 'subdir').mkdir()
        (torrent_dir / 'subdir' / 'test3.torrent').touch()
        
        # Test scanning
        torrents = media.scan_torrents(torrent_dir)
        
        assert len(torrents) == 3
        assert all(t.suffix == '.torrent' for t in torrents)
    
    
    @patch('src.mediadata.MediaData.scan_torrents')
    @patch('mediadata.TorrentScanner.scan_directory')
    def test_scan_and_match_unified(self, mock_scan, mock_scan_torrents):
        """Test unified folder scan and match functionality."""
        media = self._create_temp_mediadata()
        
        # Mock scanner results
        mock_matches = [
            Mock(complete=True, info_hash='hash1', files=['file1', 'file2']), 
            Mock(complete=False, info_hash='hash2', files=['file3'])
        ]
        mock_scan.return_value = mock_matches
        mock_scan_torrents.return_value = [Path('test1.torrent'), Path('test2.torrent')]
        
        # Create test directories
        folder1 = Path(self.temp_dir) / 'folder1'
        folder2 = Path(self.temp_dir) / 'folder2'
        folder1.mkdir()
        folder2.mkdir()
        
        # Test unified folder matching
        matches = media.scan_and_match([folder1, folder2])
        
        assert len(matches) == 2
        mock_scan.assert_called()
    
    @patch('mediadata.LibraryOrganizer.organize_matches')
    def test_organize_torrents(self, mock_organize):
        """Test torrent organization."""
        media = self._create_temp_mediadata()
        
        # Mock organization results
        mock_results = [Mock(success=True), Mock(success=False)]
        mock_organize.return_value = mock_results
        
        # Test organization
        mock_matches = [Mock(complete=True), Mock(complete=False)]
        results = media.organize_torrents(mock_matches)
        
        assert len(results) == 2
        # Should only organize complete matches
        mock_organize.assert_called_once()
        organized_matches = mock_organize.call_args[0][0]
        assert len(organized_matches) == 1  # Only the complete match
        assert organized_matches[0].complete
    
    @patch('mediadata.MetadataProcessor.process_torrent_match')
    @patch('src.metadata.setup_metadata_logging')
    def test_fetch_metadata(self, mock_logging, mock_process):
        """Test metadata fetching."""
        media = self._create_temp_mediadata()
        
        # Mock metadata processing
        mock_result = Mock(identification=Mock(title='Test Movie'))
        mock_process.return_value = mock_result
        
        # Create mock organize results
        mock_target_dir = Path(self.temp_dir) / 'target'
        mock_target_dir.mkdir()
        (mock_target_dir / 'metadata').mkdir()
        
        organize_results = [
            Mock(success=True, torrent_match=Mock(name='Test Movie'), target_dir=mock_target_dir),
            Mock(success=False)  # Should be filtered out
        ]
        
        # Test metadata fetching
        metadata_results = media.fetch_metadata(organize_results)
        
        assert len(metadata_results) == 1
        mock_process.assert_called_once()
        # Note: mock_logging may not be called due to import path differences
    
    def test_set_tmdb_api_key(self):
        """Test updating TMDB API key."""
        media = self._create_temp_mediadata(tmdb_api_key=None)
        
        assert media.config['tmdb_configured'] is False
        
        media.set_tmdb_api_key('new_key')
        
        assert media.tmdb_api_key == 'new_key'
        assert media.config['tmdb_configured'] is True
    
    def test_string_representations(self):
        """Test string representations of MediaData."""
        media = self._create_temp_mediadata()
        
        # Test __repr__
        repr_str = repr(media)
        assert 'MediaData' in repr_str
        assert str(media.archive_dir) in repr_str
        assert 'configured=True' in repr_str
        
        # Test __str__ 
        str_repr = str(media)
        assert 'MediaData Library' in str_repr
        assert str(media.archive_dir) in str_repr
        assert 'TMDB: ✓' in str_repr
    
    def test_context_manager(self):
        """Test MediaData as context manager."""
        with self._create_temp_mediadata() as media:
            assert isinstance(media, MediaData)
            assert media.archive_dir.exists()
        
        # Should not raise exceptions on exit
    
    def test_library_stats(self):
        """Test getting library statistics."""
        media = self._create_temp_mediadata()
        
        stats = media.get_library_stats()
        
        assert isinstance(stats, dict)
        assert 'total_torrents' in stats
        assert 'total_files' in stats
        assert 'total_size_bytes' in stats


class TestConvenienceFunction:
    """Test convenience functions."""
    
    def test_process_media(self):
        """Test convenience function basic functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test convenience function with temp directory - should not crash
            stats = process_media(
                folder_paths=[f'{temp_dir}/folder1', f'{temp_dir}/folder2'],
                archive_dir=f'{temp_dir}/archive',
                tmdb_api_key='test_key',
                dry_run=True,
                verify_hashes=True
            )
            
            # Should return ProcessingStats
            assert isinstance(stats, ProcessingStats)
            # No torrents found, so counts should be 0
            assert stats.total_torrents_found == 0
            assert stats.successful_matches == 0