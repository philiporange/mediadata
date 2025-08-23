"""
Metadata identification and import system.

This module provides tools for:
- Identifying media content through multiple hierarchical sources
- Fetching metadata from external APIs (TMDB, etc.)
- Creating and managing NFO files in the metadata directory
- Processing media files and extracting embedded metadata
- Comprehensive logging of metadata operations
"""

import os
import re
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
from urllib.parse import quote

from guessit import guessit

from .utils import read_nfo_file, write_nfo_file, find_nfo_files, extract_metadata_source
from .scan import TorrentMatch
from config.config import config


class MediaType(Enum):
    """Media content types."""
    MOVIE = "movie"
    TV_SHOW = "tvshow" 
    TV_EPISODE = "episode"
    MUSIC_ALBUM = "album"
    MUSIC_TRACK = "track"
    BOOK = "book"
    AUDIOBOOK = "audiobook"
    UNKNOWN = "unknown"


class IdentificationSource(Enum):
    """Sources for media identification."""
    METADATA_NFO = "metadata_nfo"      # NFO files in metadata directory
    DATA_NFO = "data_nfo"              # NFO files in data directory
    TORRENT_NAME = "torrent_name"      # Name from torrent file
    FILENAME = "filename"              # Media file names
    MEDIA_TAGS = "media_tags"          # Embedded tags in media files
    MANUAL = "manual"                  # Manually provided


@dataclass
class MediaIdentification:
    """Represents identification information for a piece of media."""
    title: str
    year: Optional[int] = None
    media_type: MediaType = MediaType.UNKNOWN
    season: Optional[int] = None
    episode: Optional[int] = None
    source: IdentificationSource = IdentificationSource.FILENAME
    confidence: float = 0.0  # 0.0 to 1.0
    additional_info: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'title': self.title,
            'year': self.year,
            'media_type': self.media_type.value,
            'season': self.season,
            'episode': self.episode,
            'source': self.source.value,
            'confidence': self.confidence,
            'additional_info': self.additional_info
        }


@dataclass
class MetadataResult:
    """Result of metadata processing."""
    identification: Optional[MediaIdentification]
    tmdb_data: Optional[Dict[str, Any]] = None
    nfo_written: bool = False
    nfo_path: Optional[Path] = None
    error: Optional[str] = None
    processing_time: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'identification': self.identification.to_dict() if self.identification else None,
            'tmdb_data_available': bool(self.tmdb_data),
            'nfo_written': self.nfo_written,
            'nfo_path': str(self.nfo_path) if self.nfo_path else None,
            'error': self.error,
            'processing_time': self.processing_time
        }


class TMDBClient:
    """TMDB API client for fetching movie and TV metadata."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('TMDB_API_KEY')
        self.base_url = "https://api.themoviedb.org/3"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'mediadata/0.1.0',
            'Accept': 'application/json'
        })
        
        if not self.api_key:
            logging.warning("No TMDB API key provided. Set TMDB_API_KEY environment variable.")
    
    def search_movie(self, title: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for movies by title and optional year."""
        if not self.api_key:
            return []
        
        params = {
            'api_key': self.api_key,
            'query': title,
            'language': 'en-US'
        }
        
        if year:
            params['year'] = year
        
        try:
            response = self.session.get(f"{self.base_url}/search/movie", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except Exception as e:
            logging.error(f"TMDB movie search failed for '{title}': {e}")
            return []
    
    def search_tv(self, title: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for TV shows by title and optional year."""
        if not self.api_key:
            return []
        
        params = {
            'api_key': self.api_key,
            'query': title,
            'language': 'en-US'
        }
        
        if year:
            params['first_air_date_year'] = year
        
        try:
            response = self.session.get(f"{self.base_url}/search/tv", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except requests.RequestException as e:
            logging.error(f"TMDB TV search failed for '{title}': {e}")
            return []
    
    def get_movie_details(self, movie_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed movie information."""
        if not self.api_key:
            return None
        
        params = {
            'api_key': self.api_key,
            'language': 'en-US',
            'append_to_response': 'credits,keywords,external_ids'
        }
        
        try:
            response = self.session.get(f"{self.base_url}/movie/{movie_id}", params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"TMDB movie details failed for ID {movie_id}: {e}")
            return None
    
    def get_tv_details(self, tv_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed TV show information."""
        if not self.api_key:
            return None
        
        params = {
            'api_key': self.api_key,
            'language': 'en-US',
            'append_to_response': 'credits,keywords,external_ids'
        }
        
        try:
            response = self.session.get(f"{self.base_url}/tv/{tv_id}", params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"TMDB TV details failed for ID {tv_id}: {e}")
            return None
    
    def get_tv_episode_details(self, tv_id: int, season: int, episode: int) -> Optional[Dict[str, Any]]:
        """Get detailed TV episode information."""
        if not self.api_key:
            return None
        
        params = {
            'api_key': self.api_key,
            'language': 'en-US'
        }
        
        try:
            url = f"{self.base_url}/tv/{tv_id}/season/{season}/episode/{episode}"
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"TMDB episode details failed for {tv_id} S{season}E{episode}: {e}")
            return None


class MediaIdentifier:
    """Identifies media content through hierarchical sources."""
    
    # Regex patterns for extracting information from filenames
    YEAR_PATTERN = re.compile(r'\b(19|20)\d{2}\b')
    TV_EPISODE_PATTERNS = [
        re.compile(r'[Ss](\d{1,2})[Ee](\d{1,2})'),           # S01E01
        re.compile(r'(\d{1,2})x(\d{1,2})'),                  # 1x01  
        re.compile(r'[Ss]eason\s*(\d+).*[Ee]pisode\s*(\d+)', re.IGNORECASE),  # Season 1 Episode 1
    ]
    
    # Common video/audio extensions to ignore in title extraction
    MEDIA_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', 
                       '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.wav', '.wma'}
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.MediaIdentifier")
    
    def identify_from_torrent_match(self, torrent_match: TorrentMatch, 
                                   metadata_dir: Path, data_dir: Path) -> Optional[MediaIdentification]:
        """
        Identify media using the hierarchical approach.
        
        Args:
            torrent_match: Matched torrent information
            metadata_dir: Metadata directory to check for existing NFOs
            data_dir: Data directory to check for NFOs and analyze files
            
        Returns:
            MediaIdentification or None if identification fails
        """
        # 1. Check existing NFO files in metadata directory
        identification = self._identify_from_metadata_nfos(metadata_dir)
        if identification:
            self.logger.info(f"Identified from metadata NFO: {identification.title}")
            return identification
        
        # 2. Check NFO files in data directory
        identification = self._identify_from_data_nfos(data_dir)
        if identification:
            self.logger.info(f"Identified from data NFO: {identification.title}")
            return identification
        
        # 3. Use torrent name
        identification = self._identify_from_torrent_name(torrent_match.name)
        if identification:
            self.logger.info(f"Identified from torrent name: {identification.title}")
            return identification
        
        # 4. Use media filenames
        identification = self._identify_from_filenames(torrent_match.files)
        if identification:
            self.logger.info(f"Identified from filenames: {identification.title}")
            return identification
        
        # 5. Extract from media tags (placeholder for future implementation)
        identification = self._identify_from_media_tags(torrent_match.files)
        if identification:
            self.logger.info(f"Identified from media tags: {identification.title}")
            return identification
        
        self.logger.warning(f"Failed to identify media for torrent: {torrent_match.name}")
        return None
    
    def _identify_from_metadata_nfos(self, metadata_dir: Path) -> Optional[MediaIdentification]:
        """Extract identification from existing NFO files in metadata directory."""
        if not metadata_dir.exists():
            return None
        
        # Look for NFO files, prioritizing known sources
        source_priority = ['manual', 'tmdb', 'tvdb', 'imdb', 'override']
        
        for source in source_priority:
            nfo_path = metadata_dir / f"{source}.nfo"
            if nfo_path.exists():
                return self._parse_nfo_for_identification(nfo_path, IdentificationSource.METADATA_NFO)
        
        # Check any other NFO files
        for nfo_path in metadata_dir.glob("*.nfo"):
            identification = self._parse_nfo_for_identification(nfo_path, IdentificationSource.METADATA_NFO)
            if identification:
                return identification
        
        return None
    
    def _identify_from_data_nfos(self, data_dir: Path) -> Optional[MediaIdentification]:
        """Extract identification from NFO files in data directory."""
        if not data_dir.exists():
            return None
        
        # Find all NFO files in data directory
        nfo_results = find_nfo_files(data_dir)
        
        # Try folder-level NFOs first
        for nfo_path in nfo_results['folder']:
            identification = self._parse_nfo_for_identification(nfo_path, IdentificationSource.DATA_NFO)
            if identification:
                return identification
        
        # Then try file-level NFOs
        for nfo_path in nfo_results['file']:
            identification = self._parse_nfo_for_identification(nfo_path, IdentificationSource.DATA_NFO)
            if identification:
                return identification
        
        return None
    
    def _parse_nfo_for_identification(self, nfo_path: Path, source: IdentificationSource) -> Optional[MediaIdentification]:
        """Parse an NFO file to extract identification information."""
        try:
            root = read_nfo_file(nfo_path)
            if root is None:
                return None
            
            # Determine media type from root element
            media_type_map = {
                'movie': MediaType.MOVIE,
                'tvshow': MediaType.TV_SHOW,
                'episode': MediaType.TV_EPISODE,
                'album': MediaType.MUSIC_ALBUM,
                'song': MediaType.MUSIC_TRACK,
                'book': MediaType.BOOK,
                'audiobook': MediaType.AUDIOBOOK
            }
            
            media_type = media_type_map.get(root.tag, MediaType.UNKNOWN)
            
            # Extract basic information
            title_elem = root.find('title')
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else None
            
            if not title:
                return None
            
            # Extract year
            year = None
            year_elem = root.find('year')
            if year_elem is not None and year_elem.text:
                try:
                    year = int(year_elem.text.strip())
                except ValueError:
                    pass
            
            # Extract season/episode for TV episodes
            season = None
            episode = None
            if media_type == MediaType.TV_EPISODE:
                season_elem = root.find('season')
                episode_elem = root.find('episode')
                
                if season_elem is not None and season_elem.text:
                    try:
                        season = int(season_elem.text.strip())
                    except ValueError:
                        pass
                
                if episode_elem is not None and episode_elem.text:
                    try:
                        episode = int(episode_elem.text.strip())
                    except ValueError:
                        pass
            
            return MediaIdentification(
                title=title,
                year=year,
                media_type=media_type,
                season=season,
                episode=episode,
                source=source,
                confidence=0.9,  # High confidence from existing NFO
                additional_info={'nfo_path': str(nfo_path)}
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing NFO {nfo_path}: {e}")
            return None
    
    def _identify_from_torrent_name(self, torrent_name: str) -> Optional[MediaIdentification]:
        """Extract identification from torrent name using guessit."""
        return self._parse_name_with_guessit(torrent_name, IdentificationSource.TORRENT_NAME, confidence=0.8)
    
    def _identify_from_filenames(self, file_matches: List) -> Optional[MediaIdentification]:
        """Extract identification from media filenames using guessit."""
        if not file_matches:
            return None
        
        # Try to find the main media file (largest video file)
        video_files = [f for f in file_matches if self._is_video_file(f.torrent_path)]
        if video_files:
            main_file = max(video_files, key=lambda f: f.size)
        else:
            main_file = max(file_matches, key=lambda f: f.size)
        
        # Use full path for better guessit parsing, but fallback to filename
        full_path = main_file.torrent_path
        filename = Path(full_path).name
        
        # Try full path first, then filename
        identification = self._parse_name_with_guessit(full_path, IdentificationSource.FILENAME, confidence=0.7)
        if not identification:
            identification = self._parse_name_with_guessit(filename, IdentificationSource.FILENAME, confidence=0.6)
        
        return identification
    
    def _identify_from_media_tags(self, file_matches: List) -> Optional[MediaIdentification]:
        """Extract identification from embedded media tags (placeholder)."""
        # TODO: Implement media tag extraction using libraries like mutagen, ffprobe, etc.
        # For now, return None to indicate this step is not implemented
        return None
    
    def _parse_name_with_guessit(self, name: str, source: IdentificationSource, 
                                confidence: float = 0.8) -> Optional[MediaIdentification]:
        """Parse a name string using guessit for identification."""
        if not name or not name.strip():
            return None
        
        try:
            # Use guessit to parse the name
            guess = guessit(name)
            
            if not guess:
                return None
            
            # Extract basic information
            title = guess.get('title')
            if not title:
                return None
            
            # Clean up title if it's a list (multiple parts)
            if isinstance(title, list):
                title = ' '.join(str(t) for t in title)
            title = str(title).strip()
            
            # Extract year
            year = guess.get('year')
            if isinstance(year, list):
                year = year[0] if year else None
            
            # Extract media type
            guess_type = guess.get('type', 'movie')
            media_type = self._map_guessit_type(guess_type)
            
            # Extract season/episode for TV content
            season = guess.get('season')
            episode = guess.get('episode')
            
            # Handle episode lists (multi-episode files)
            if isinstance(episode, list):
                episode = episode[0] if episode else None
            if isinstance(season, list):
                season = season[0] if season else None
            
            # Calculate confidence based on guessit match quality
            calculated_confidence = self._calculate_guessit_confidence(guess, base_confidence=confidence)
            
            # Build additional info from guessit results
            additional_info = {
                'guessit_data': dict(guess),
                'release_group': guess.get('release_group'),
                'source': guess.get('source'),
                'video_codec': guess.get('video_codec'),
                'resolution': guess.get('screen_size'),
            }
            
            return MediaIdentification(
                title=title,
                year=year,
                media_type=media_type,
                season=season,
                episode=episode,
                source=source,
                confidence=calculated_confidence,
                additional_info=additional_info
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing with guessit: {name} - {e}")
            # Fallback to manual parsing
            return self._parse_name_for_identification_manual(name, source, confidence * 0.5)
    
    def _map_guessit_type(self, guess_type: str) -> MediaType:
        """Map guessit type to MediaType enum."""
        type_mapping = {
            'movie': MediaType.MOVIE,
            'episode': MediaType.TV_EPISODE,
            'tv': MediaType.TV_SHOW,
            'series': MediaType.TV_SHOW,
            'season': MediaType.TV_SHOW,
        }
        
        return type_mapping.get(guess_type.lower(), MediaType.MOVIE)
    
    def _calculate_guessit_confidence(self, guess: dict, base_confidence: float) -> float:
        """Calculate confidence score based on guessit match quality."""
        confidence = base_confidence
        
        # Increase confidence for well-structured matches
        if guess.get('title'):
            confidence += 0.1
        
        if guess.get('year'):
            confidence += 0.1
        
        if guess.get('type') and guess.get('type') != 'unknown':
            confidence += 0.1
        
        # TV episodes get bonus for season/episode info
        if guess.get('type') == 'episode':
            if guess.get('season') and guess.get('episode'):
                confidence += 0.2
            elif guess.get('season') or guess.get('episode'):
                confidence += 0.1
        
        # High-quality releases get slight bonus
        if guess.get('source') in ['BluRay', 'DVD', 'WEB-DL']:
            confidence += 0.05
        
        # Cap at 1.0
        return min(1.0, confidence)
    
    def _is_video_file(self, filename: str) -> bool:
        """Check if filename is a video file."""
        video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', 
                           '.m4v', '.ts', '.m2ts', '.mpg', '.mpeg', '.ogv'}
        return Path(filename).suffix.lower() in video_extensions
    
    def _parse_name_for_identification_manual(self, name: str, source: IdentificationSource, 
                                     confidence: float = 0.7) -> Optional[MediaIdentification]:
        """Parse a name string to extract media identification."""
        if not name or not name.strip():
            return None
        
        name = name.strip()
        
        # Extract year
        year_match = self.YEAR_PATTERN.search(name)
        year = int(year_match.group()) if year_match else None
        
        # Check for TV episode patterns
        season = None
        episode = None
        media_type = MediaType.UNKNOWN
        
        for pattern in self.TV_EPISODE_PATTERNS:
            match = pattern.search(name)
            if match:
                season = int(match.group(1))
                episode = int(match.group(2))
                media_type = MediaType.TV_EPISODE
                break
        
        # If no episode pattern found, assume it's a movie or show
        if media_type == MediaType.UNKNOWN:
            # Simple heuristic: if it has a year and no episode info, likely a movie
            if year:
                media_type = MediaType.MOVIE
            else:
                # Could be TV show, but hard to determine without more info
                media_type = MediaType.MOVIE  # Default to movie
        
        # Extract title by removing year, episode info, and common suffixes
        title = name
        
        # Remove year
        if year_match:
            title = title[:year_match.start()] + title[year_match.end():]
        
        # Remove episode patterns
        for pattern in self.TV_EPISODE_PATTERNS:
            title = pattern.sub('', title)
        
        # Remove common release info patterns
        release_patterns = [
            r'\b(HDTV|BluRay|BDRip|DVDRip|WEBRip|WEB-DL)\b',
            r'\b(x264|x265|H\.264|H\.265|HEVC)\b',
            r'\b(1080p|720p|480p|4K|2160p)\b',
            r'\b(AAC|AC3|DTS|MP3|FLAC)\b',
            r'\b(YIFY|RARBG|YTS|FGT|GROUP)\b',  # Added GROUP
            r'\[.*?\]',  # Remove brackets
            r'\(.*?\)',  # Remove parentheses
            r'-\w+$',    # Remove trailing dash and group name
        ]
        
        for pattern in release_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        # For TV episodes, try to remove everything after the episode pattern
        if media_type == MediaType.TV_EPISODE:
            # Find the position of the episode pattern and cut there
            for pattern in self.TV_EPISODE_PATTERNS:
                match = pattern.search(name)
                if match:
                    # Take everything before the episode pattern
                    title = name[:match.start()]
                    # Apply basic cleaning
                    title = re.sub(r'[._-]+', ' ', title)
                    title = re.sub(r'\s+', ' ', title).strip()
                    break
        
        # Clean up title
        title = re.sub(r'[._-]+', ' ', title)  # Replace separators with spaces
        title = re.sub(r'\s+', ' ', title).strip()  # Normalize whitespace
        
        if not title:
            return None
        
        return MediaIdentification(
            title=title,
            year=year,
            media_type=media_type,
            season=season,
            episode=episode,
            source=source,
            confidence=confidence
        )


class MetadataProcessor:
    """Processes metadata for torrent matches and creates NFO files."""
    
    def __init__(self, tmdb_client: Optional[TMDBClient] = None):
        self.identifier = MediaIdentifier()
        self.tmdb = tmdb_client or TMDBClient()
        self.logger = logging.getLogger(f"{__name__}.MetadataProcessor")
    
    def process_torrent_match(self, torrent_match: TorrentMatch, 
                             target_dir: Path) -> MetadataResult:
        """
        Process metadata for a torrent match.
        
        Args:
            torrent_match: TorrentMatch to process
            target_dir: Target directory (contains data/ and metadata/)
            
        Returns:
            MetadataResult with processing information
        """
        start_time = time.time()
        
        metadata_dir = target_dir / 'metadata'
        data_dir = target_dir / 'data'
        
        try:
            # Step 1: Identify the media
            identification = self.identifier.identify_from_torrent_match(
                torrent_match, metadata_dir, data_dir
            )
            
            if not identification:
                return MetadataResult(
                    identification=None,
                    error="Could not identify media content",
                    processing_time=time.time() - start_time
                )
            
            # Step 2: Fetch metadata from TMDB
            tmdb_data = None
            if identification.media_type in [MediaType.MOVIE, MediaType.TV_SHOW, MediaType.TV_EPISODE]:
                tmdb_data = self._fetch_tmdb_data(identification)
            
            # Step 3: Create NFO file
            nfo_written = False
            nfo_path = None
            
            if tmdb_data:
                nfo_path = self._create_nfo_from_tmdb(tmdb_data, identification, metadata_dir)
                nfo_written = nfo_path is not None
            
            return MetadataResult(
                identification=identification,
                tmdb_data=tmdb_data,
                nfo_written=nfo_written,
                nfo_path=nfo_path,
                processing_time=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Error processing metadata for {torrent_match.name}: {e}")
            return MetadataResult(
                identification=None,
                error=str(e),
                processing_time=time.time() - start_time
            )
    
    def _fetch_tmdb_data(self, identification: MediaIdentification) -> Optional[Dict[str, Any]]:
        """Fetch data from TMDB based on identification."""
        if identification.media_type == MediaType.MOVIE:
            results = self.tmdb.search_movie(identification.title, identification.year)
            if results:
                # Take the first/best match
                movie_id = results[0]['id']
                return self.tmdb.get_movie_details(movie_id)
        
        elif identification.media_type in [MediaType.TV_SHOW, MediaType.TV_EPISODE]:
            results = self.tmdb.search_tv(identification.title, identification.year)
            if results:
                tv_id = results[0]['id']
                tv_data = self.tmdb.get_tv_details(tv_id)
                
                # If it's a specific episode, fetch episode details too
                if (identification.media_type == MediaType.TV_EPISODE and 
                    identification.season is not None and 
                    identification.episode is not None):
                    episode_data = self.tmdb.get_tv_episode_details(
                        tv_id, identification.season, identification.episode
                    )
                    if episode_data:
                        tv_data = tv_data or {}
                        tv_data['episode_details'] = episode_data
                
                return tv_data
        
        return None
    
    def _create_nfo_from_tmdb(self, tmdb_data: Dict[str, Any], 
                             identification: MediaIdentification,
                             metadata_dir: Path) -> Optional[Path]:
        """Create NFO file from TMDB data."""
        try:
            if identification.media_type == MediaType.MOVIE:
                root = self._create_movie_nfo(tmdb_data)
                nfo_filename = 'tmdb.nfo'
            elif identification.media_type in [MediaType.TV_SHOW, MediaType.TV_EPISODE]:
                if 'episode_details' in tmdb_data:
                    root = self._create_episode_nfo(tmdb_data, tmdb_data['episode_details'])
                    nfo_filename = 'tmdb.nfo'
                else:
                    root = self._create_tvshow_nfo(tmdb_data)
                    nfo_filename = 'tmdb.nfo'
            else:
                return None
            
            nfo_path = metadata_dir / nfo_filename
            write_nfo_file(root, nfo_path)
            self.logger.info(f"Created NFO file: {nfo_path}")
            return nfo_path
            
        except Exception as e:
            self.logger.error(f"Error creating NFO file: {e}")
            return None
    
    def _create_movie_nfo(self, tmdb_data: Dict[str, Any]) -> ET.Element:
        """Create movie NFO from TMDB data."""
        movie = ET.Element('movie')
        
        # Basic information
        self._add_element(movie, 'title', tmdb_data.get('title'))
        self._add_element(movie, 'originaltitle', tmdb_data.get('original_title'))
        self._add_element(movie, 'plot', tmdb_data.get('overview'))
        self._add_element(movie, 'tagline', tmdb_data.get('tagline'))
        
        # Dates and year
        if tmdb_data.get('release_date'):
            self._add_element(movie, 'premiered', tmdb_data['release_date'])
            try:
                year = datetime.strptime(tmdb_data['release_date'], '%Y-%m-%d').year
                self._add_element(movie, 'year', str(year))
            except ValueError:
                pass
        
        # Runtime
        if tmdb_data.get('runtime'):
            self._add_element(movie, 'runtime', str(tmdb_data['runtime']))
        
        # Ratings
        if tmdb_data.get('vote_average'):
            ratings = ET.SubElement(movie, 'ratings')
            rating = ET.SubElement(ratings, 'rating', name='tmdb', max='10', default='true')
            self._add_element(rating, 'value', str(tmdb_data['vote_average']))
            if tmdb_data.get('vote_count'):
                self._add_element(rating, 'votes', str(tmdb_data['vote_count']))
        
        # Genres
        for genre in tmdb_data.get('genres', []):
            self._add_element(movie, 'genre', genre.get('name'))
        
        # Cast and crew
        credits = tmdb_data.get('credits', {})
        
        # Directors
        for person in credits.get('crew', []):
            if person.get('job') == 'Director':
                self._add_element(movie, 'director', person.get('name'))
        
        # Writers
        for person in credits.get('crew', []):
            if person.get('job') in ['Writer', 'Screenplay', 'Story']:
                self._add_element(movie, 'writer', person.get('name'))
        
        # Actors
        for person in credits.get('cast', [])[:10]:  # Limit to top 10
            actor = ET.SubElement(movie, 'actor')
            self._add_element(actor, 'name', person.get('name'))
            self._add_element(actor, 'role', person.get('character'))
            if person.get('order') is not None:
                self._add_element(actor, 'order', str(person.get('order')))
        
        # Unique IDs
        uniqueid = ET.SubElement(movie, 'uniqueid', type='tmdb', default='true')
        uniqueid.text = str(tmdb_data.get('id'))
        
        if tmdb_data.get('imdb_id'):
            imdb_uniqueid = ET.SubElement(movie, 'uniqueid', type='imdb')
            imdb_uniqueid.text = tmdb_data['imdb_id']
        
        return movie
    
    def _create_tvshow_nfo(self, tmdb_data: Dict[str, Any]) -> ET.Element:
        """Create TV show NFO from TMDB data."""
        tvshow = ET.Element('tvshow')
        
        # Basic information
        self._add_element(tvshow, 'title', tmdb_data.get('name'))
        self._add_element(tvshow, 'originaltitle', tmdb_data.get('original_name'))
        self._add_element(tvshow, 'plot', tmdb_data.get('overview'))
        
        # Dates
        if tmdb_data.get('first_air_date'):
            self._add_element(tvshow, 'premiered', tmdb_data['first_air_date'])
            try:
                year = datetime.strptime(tmdb_data['first_air_date'], '%Y-%m-%d').year
                self._add_element(tvshow, 'year', str(year))
            except ValueError:
                pass
        
        # Status and counts
        self._add_element(tvshow, 'status', tmdb_data.get('status'))
        if tmdb_data.get('number_of_seasons'):
            self._add_element(tvshow, 'seasoncount', str(tmdb_data['number_of_seasons']))
        
        # Ratings
        if tmdb_data.get('vote_average'):
            ratings = ET.SubElement(tvshow, 'ratings')
            rating = ET.SubElement(ratings, 'rating', name='tmdb', max='10', default='true')
            self._add_element(rating, 'value', str(tmdb_data['vote_average']))
            if tmdb_data.get('vote_count'):
                self._add_element(rating, 'votes', str(tmdb_data['vote_count']))
        
        # Genres
        for genre in tmdb_data.get('genres', []):
            self._add_element(tvshow, 'genre', genre.get('name'))
        
        # Networks/Studios
        for network in tmdb_data.get('networks', []):
            self._add_element(tvshow, 'studio', network.get('name'))
        
        # Unique IDs
        uniqueid = ET.SubElement(tvshow, 'uniqueid', type='tmdb', default='true')
        uniqueid.text = str(tmdb_data.get('id'))
        
        return tvshow
    
    def _create_episode_nfo(self, show_data: Dict[str, Any], 
                           episode_data: Dict[str, Any]) -> ET.Element:
        """Create TV episode NFO from TMDB data."""
        episode = ET.Element('episode')
        
        # Basic information
        self._add_element(episode, 'title', episode_data.get('name'))
        self._add_element(episode, 'plot', episode_data.get('overview'))
        
        # Episode numbering
        if episode_data.get('season_number') is not None:
            self._add_element(episode, 'season', str(episode_data['season_number']))
        if episode_data.get('episode_number') is not None:
            self._add_element(episode, 'episode', str(episode_data['episode_number']))
        
        # Air date
        if episode_data.get('air_date'):
            self._add_element(episode, 'aired', episode_data['air_date'])
        
        # Runtime
        if episode_data.get('runtime'):
            self._add_element(episode, 'runtime', str(episode_data['runtime']))
        
        # Ratings
        if episode_data.get('vote_average'):
            ratings = ET.SubElement(episode, 'ratings')
            rating = ET.SubElement(ratings, 'rating', name='tmdb', max='10', default='true')
            self._add_element(rating, 'value', str(episode_data['vote_average']))
            if episode_data.get('vote_count'):
                self._add_element(rating, 'votes', str(episode_data['vote_count']))
        
        return episode
    
    def _add_element(self, parent: ET.Element, tag: str, text: Optional[str]) -> None:
        """Add element with text if text is not None/empty."""
        if text:
            elem = ET.SubElement(parent, tag)
            elem.text = str(text).strip()


def setup_metadata_logging(log_dir: Path) -> logging.Logger:
    """Setup logging for metadata operations."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"metadata_{datetime.now().strftime('%Y%m%d')}.log"
    
    # Create logger
    logger = logging.getLogger('mediadata.metadata')
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        # File handler
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


def process_torrents_metadata(torrent_matches: List[TorrentMatch],
                             library_path: Path,
                             tmdb_api_key: Optional[str] = None) -> List[MetadataResult]:
    """
    Process metadata for multiple torrent matches.
    
    Args:
        torrent_matches: List of TorrentMatch objects
        library_path: Base library directory
        tmdb_api_key: TMDB API key (optional, can use env var)
        
    Returns:
        List of MetadataResult objects
    """
    tmdb_client = TMDBClient(tmdb_api_key)
    processor = MetadataProcessor(tmdb_client)
    
    results = []
    
    for torrent_match in torrent_matches:
        # Setup logging for this torrent
        target_dir = library_path / torrent_match.info_hash.lower()
        log_dir = target_dir / 'metadata' / 'logs'
        logger = setup_metadata_logging(log_dir)
        
        logger.info(f"Processing metadata for: {torrent_match.name}")
        
        # Process metadata
        result = processor.process_torrent_match(torrent_match, target_dir)
        results.append(result)
        
        # Log result
        if result.identification:
            logger.info(f"Successfully identified: {result.identification.title}")
            logger.info(f"Result: {result.to_dict()}")
        else:
            logger.warning(f"Failed to identify media: {result.error}")
        
        # Log to audit trail
        audit_dir = target_dir / 'metadata' / 'audit'
        audit_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        audit_file = audit_dir / f'metadata_{timestamp}.json'
        
        with open(audit_file, 'w', encoding='utf-8') as f:
            audit_data = {
                'timestamp': timestamp,
                'torrent_info': {
                    'name': torrent_match.name,
                    'info_hash': torrent_match.info_hash,
                    'files': [f.torrent_path for f in torrent_match.files]
                },
                'result': result.to_dict()
            }
            json.dump(audit_data, f, indent=2, ensure_ascii=False)
    
    return results