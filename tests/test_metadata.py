"""Tests for metadata functionality."""

import pytest
import tempfile
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.metadata import (
    MediaType,
    IdentificationSource,
    MediaIdentification,
    MetadataResult,
    TMDBClient,
    MediaIdentifier,
    MetadataProcessor,
    setup_metadata_logging,
    process_torrents_metadata
)
from src.scan import TorrentMatch, FileMatch


class TestMediaIdentification:
    """Test MediaIdentification dataclass."""
    
    def test_media_identification_creation(self):
        """Test creating MediaIdentification objects."""
        identification = MediaIdentification(
            title="Test Movie",
            year=2023,
            media_type=MediaType.MOVIE,
            source=IdentificationSource.TORRENT_NAME,
            confidence=0.8,
            additional_info={'test': 'data'}
        )
        
        assert identification.title == "Test Movie"
        assert identification.year == 2023
        assert identification.media_type == MediaType.MOVIE
        assert identification.source == IdentificationSource.TORRENT_NAME
        assert identification.confidence == 0.8
        assert identification.additional_info == {'test': 'data'}
    
    def test_media_identification_to_dict(self):
        """Test MediaIdentification to_dict method."""
        identification = MediaIdentification(
            title="Test Show",
            season=1,
            episode=5,
            media_type=MediaType.TV_EPISODE,
            source=IdentificationSource.FILENAME
        )
        
        data = identification.to_dict()
        
        assert data['title'] == "Test Show"
        assert data['season'] == 1
        assert data['episode'] == 5
        assert data['media_type'] == 'episode'
        assert data['source'] == 'filename'


class TestTMDBClient:
    """Test TMDB API client."""
    
    def setup_method(self):
        """Set up test environment."""
        self.client = TMDBClient(api_key='test_key')
    
    @patch('src.metadata.requests.Session.get')
    def test_search_movie_success(self, mock_get):
        """Test successful movie search."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'results': [
                {'id': 123, 'title': 'Test Movie', 'release_date': '2023-01-01'}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        results = self.client.search_movie('Test Movie', 2023)
        
        assert len(results) == 1
        assert results[0]['id'] == 123
        assert results[0]['title'] == 'Test Movie'
        
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert 'search/movie' in args[0]
        assert kwargs['params']['query'] == 'Test Movie'
        assert kwargs['params']['year'] == 2023
    
    @patch('src.metadata.requests.Session.get')
    def test_search_tv_success(self, mock_get):
        """Test successful TV search."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'results': [
                {'id': 456, 'name': 'Test Show', 'first_air_date': '2023-01-01'}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        results = self.client.search_tv('Test Show')
        
        assert len(results) == 1
        assert results[0]['id'] == 456
        assert results[0]['name'] == 'Test Show'
    
    @patch('src.metadata.requests.Session.get')
    def test_api_error_handling(self, mock_get):
        """Test API error handling."""
        mock_get.side_effect = Exception('API Error')
        
        results = self.client.search_movie('Test Movie')
        assert results == []
    
    def test_no_api_key(self):
        """Test behavior without API key."""
        client = TMDBClient(api_key=None)
        results = client.search_movie('Test Movie')
        assert results == []


class TestMediaIdentifier:
    """Test MediaIdentifier functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.identifier = MediaIdentifier()
    
    def test_parse_movie_name(self):
        """Test parsing movie names with guessit."""
        identification = self.identifier._parse_name_with_guessit(
            "The Dark Knight (2008) [1080p] BluRay x264", 
            IdentificationSource.TORRENT_NAME
        )
        
        assert identification is not None
        assert identification.title == "The Dark Knight"
        assert identification.year == 2008
        assert identification.media_type == MediaType.MOVIE
    
    def test_parse_tv_episode_name(self):
        """Test parsing TV episode names with guessit."""
        identification = self.identifier._parse_name_with_guessit(
            "Breaking Bad S01E01 Pilot 1080p", 
            IdentificationSource.FILENAME
        )
        
        assert identification is not None
        assert identification.title == "Breaking Bad"
        assert identification.season == 1
        assert identification.episode == 1
        assert identification.media_type == MediaType.TV_EPISODE
        # Check that guessit data is included
        assert 'guessit_data' in identification.additional_info
    
    def test_parse_tv_episode_alternate_format(self):
        """Test parsing alternate TV episode format with guessit."""
        identification = self.identifier._parse_name_with_guessit(
            "Game.of.Thrones.1x01.Winter.Is.Coming.HDTV", 
            IdentificationSource.FILENAME
        )
        
        assert identification is not None
        assert identification.title == "Game of Thrones"
        assert identification.season == 1
        assert identification.episode == 1
        assert identification.media_type == MediaType.TV_EPISODE
    
    def test_guessit_title_extraction(self):
        """Test title extraction with guessit."""
        test_cases = [
            ("Movie.Name.2023.1080p.BluRay.x264-GROUP", "Movie Name"),
            ("TV_Show_S01E01_HDTV_x264", "TV Show"),
            ("Some.Movie.2020.WEBRip.1080p", "Some Movie"),
            ("Breaking.Bad.S01E01.Pilot", "Breaking Bad"),
        ]
        
        for input_name, expected_title in test_cases:
            identification = self.identifier._parse_name_with_guessit(
                input_name, IdentificationSource.FILENAME
            )
            if identification:
                assert identification.title == expected_title
    
    def test_guessit_confidence_calculation(self):
        """Test confidence calculation with guessit results."""
        # High confidence case: complete movie info
        identification = self.identifier._parse_name_with_guessit(
            "The Matrix 1999 1080p BluRay x264-GROUP",
            IdentificationSource.TORRENT_NAME
        )
        
        assert identification is not None
        assert identification.confidence > 0.8  # Should be high confidence
        
        # Lower confidence case: minimal info
        identification = self.identifier._parse_name_with_guessit(
            "unknown_file",
            IdentificationSource.FILENAME
        )
        
        # May return None or low confidence depending on guessit parsing
    
    def test_guessit_type_mapping(self):
        """Test guessit type mapping to MediaType."""
        # Test movie
        assert self.identifier._map_guessit_type('movie') == MediaType.MOVIE
        
        # Test TV episode
        assert self.identifier._map_guessit_type('episode') == MediaType.TV_EPISODE
        
        # Test TV series
        assert self.identifier._map_guessit_type('tv') == MediaType.TV_SHOW
        assert self.identifier._map_guessit_type('series') == MediaType.TV_SHOW
        
        # Test unknown defaults to movie
        assert self.identifier._map_guessit_type('unknown') == MediaType.MOVIE
    
    def test_is_video_file(self):
        """Test video file detection."""
        assert self.identifier._is_video_file("movie.mkv")
        assert self.identifier._is_video_file("episode.mp4")
        assert self.identifier._is_video_file("show.avi")
        assert not self.identifier._is_video_file("subtitle.srt")
        assert not self.identifier._is_video_file("readme.txt")
    
    @patch('src.metadata.read_nfo_file')
    def test_parse_movie_nfo(self, mock_read_nfo):
        """Test parsing movie NFO files."""
        # Create mock XML
        root = ET.Element('movie')
        title_elem = ET.SubElement(root, 'title')
        title_elem.text = 'Test Movie'
        year_elem = ET.SubElement(root, 'year')
        year_elem.text = '2023'
        
        mock_read_nfo.return_value = root
        
        identification = self.identifier._parse_nfo_for_identification(
            Path('/test/movie.nfo'), IdentificationSource.DATA_NFO
        )
        
        assert identification is not None
        assert identification.title == 'Test Movie'
        assert identification.year == 2023
        assert identification.media_type == MediaType.MOVIE
    
    @patch('src.metadata.read_nfo_file')
    def test_parse_episode_nfo(self, mock_read_nfo):
        """Test parsing TV episode NFO files."""
        root = ET.Element('episode')
        title_elem = ET.SubElement(root, 'title')
        title_elem.text = 'Test Episode'
        season_elem = ET.SubElement(root, 'season')
        season_elem.text = '2'
        episode_elem = ET.SubElement(root, 'episode')
        episode_elem.text = '5'
        
        mock_read_nfo.return_value = root
        
        identification = self.identifier._parse_nfo_for_identification(
            Path('/test/episode.nfo'), IdentificationSource.METADATA_NFO
        )
        
        assert identification is not None
        assert identification.title == 'Test Episode'
        assert identification.season == 2
        assert identification.episode == 5
        assert identification.media_type == MediaType.TV_EPISODE


class TestMetadataProcessor:
    """Test MetadataProcessor functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.mock_tmdb = Mock(spec=TMDBClient)
        self.processor = MetadataProcessor(self.mock_tmdb)
    
    def test_create_movie_nfo(self):
        """Test creating movie NFO from TMDB data."""
        tmdb_data = {
            'id': 123,
            'title': 'Test Movie',
            'original_title': 'Test Movie Original',
            'overview': 'A test movie plot',
            'tagline': 'Test tagline',
            'release_date': '2023-05-15',
            'runtime': 120,
            'vote_average': 7.5,
            'vote_count': 1000,
            'genres': [{'name': 'Action'}, {'name': 'Drama'}],
            'credits': {
                'crew': [
                    {'job': 'Director', 'name': 'Test Director'},
                    {'job': 'Writer', 'name': 'Test Writer'}
                ],
                'cast': [
                    {'name': 'Test Actor', 'character': 'Main Character', 'order': 0}
                ]
            }
        }
        
        root = self.processor._create_movie_nfo(tmdb_data)
        
        assert root.tag == 'movie'
        assert root.find('title').text == 'Test Movie'
        assert root.find('originaltitle').text == 'Test Movie Original'
        assert root.find('plot').text == 'A test movie plot'
        assert root.find('year').text == '2023'
        assert root.find('runtime').text == '120'
        
        # Check ratings
        ratings = root.find('ratings')
        assert ratings is not None
        rating = ratings.find('rating')
        assert rating.get('name') == 'tmdb'
        assert rating.find('value').text == '7.5'
        assert rating.find('votes').text == '1000'
        
        # Check genres
        genres = root.findall('genre')
        assert len(genres) == 2
        assert genres[0].text == 'Action'
        assert genres[1].text == 'Drama'
        
        # Check crew
        directors = root.findall('director')
        assert len(directors) == 1
        assert directors[0].text == 'Test Director'
        
        # Check cast
        actors = root.findall('actor')
        assert len(actors) == 1
        actor = actors[0]
        assert actor.find('name').text == 'Test Actor'
        assert actor.find('role').text == 'Main Character'
    
    def test_create_tvshow_nfo(self):
        """Test creating TV show NFO from TMDB data."""
        tmdb_data = {
            'id': 456,
            'name': 'Test Show',
            'original_name': 'Test Show Original',
            'overview': 'A test TV show',
            'first_air_date': '2023-01-01',
            'status': 'Returning Series',
            'number_of_seasons': 3,
            'vote_average': 8.2,
            'vote_count': 500,
            'genres': [{'name': 'Drama'}],
            'networks': [{'name': 'Test Network'}]
        }
        
        root = self.processor._create_tvshow_nfo(tmdb_data)
        
        assert root.tag == 'tvshow'
        assert root.find('title').text == 'Test Show'
        assert root.find('originaltitle').text == 'Test Show Original'
        assert root.find('plot').text == 'A test TV show'
        assert root.find('premiered').text == '2023-01-01'
        assert root.find('year').text == '2023'
        assert root.find('status').text == 'Returning Series'
        assert root.find('seasoncount').text == '3'
        
        # Check studio/network
        studios = root.findall('studio')
        assert len(studios) == 1
        assert studios[0].text == 'Test Network'


class TestMetadataIntegration:
    """Test metadata processing integration."""
    
    @patch('src.metadata.setup_metadata_logging')
    @patch('src.metadata.TMDBClient')
    def test_process_torrents_metadata(self, mock_tmdb_class, mock_logging):
        """Test processing multiple torrents for metadata."""
        # Setup mocks
        mock_tmdb = Mock()
        mock_tmdb_class.return_value = mock_tmdb
        mock_logger = Mock()
        mock_logging.return_value = mock_logger
        
        # Create test torrent match
        torrent_match = TorrentMatch(
            torrent_file=Path('/test/movie.torrent'),
            info_hash='a' * 40,
            name='Test Movie (2023) 1080p',
            root_path=Path('/test'),
            files=[
                FileMatch('Test Movie.mkv', Path('/test/Test Movie.mkv'), 1000000)
            ],
            complete=True
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            library_path = Path(temp_dir)
            
            # Mock TMDB responses
            mock_tmdb.search_movie.return_value = [{'id': 123}]
            mock_tmdb.get_movie_details.return_value = {
                'id': 123,
                'title': 'Test Movie',
                'release_date': '2023-01-01'
            }
            
            results = process_torrents_metadata([torrent_match], library_path)
            
            assert len(results) == 1
            result = results[0]
            assert result.identification is not None
            assert result.identification.title == 'Test Movie'


class TestLogging:
    """Test metadata logging functionality."""
    
    def test_setup_metadata_logging(self):
        """Test metadata logging setup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / 'logs'
            logger = setup_metadata_logging(log_dir)
            
            assert logger.name == 'mediadata.metadata'
            assert log_dir.exists()
            
            # Test logging
            logger.info("Test message")
            
            # Check log file was created
            log_files = list(log_dir.glob("metadata_*.log"))
            assert len(log_files) == 1