"""Tests for utils module functionality."""

import pytest
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from mediadata.utils import (
    BencodeDecoder,
    _encode_bencode,
    extract_metadata_source,
    is_media_file,
    read_nfo_file,
    write_nfo_file
)


class TestBencodeDecoder:
    """Test bencode encoding and decoding functionality."""
    
    def test_decode_integer(self):
        """Test decoding integers."""
        decoder = BencodeDecoder(b'i42e')
        assert decoder.decode() == 42
        
        decoder = BencodeDecoder(b'i-42e')
        assert decoder.decode() == -42
        
        decoder = BencodeDecoder(b'i0e')
        assert decoder.decode() == 0
    
    def test_decode_string(self):
        """Test decoding strings."""
        decoder = BencodeDecoder(b'5:hello')
        assert decoder.decode() == b'hello'
        
        decoder = BencodeDecoder(b'0:')
        assert decoder.decode() == b''
    
    def test_decode_list(self):
        """Test decoding lists."""
        decoder = BencodeDecoder(b'li42e5:helloe')
        result = decoder.decode()
        assert result == [42, b'hello']
        
        decoder = BencodeDecoder(b'le')
        assert decoder.decode() == []
    
    def test_decode_dict(self):
        """Test decoding dictionaries."""
        decoder = BencodeDecoder(b'd5:helloi42ee')
        result = decoder.decode()
        assert result == {b'hello': 42}
        
        decoder = BencodeDecoder(b'de')
        assert decoder.decode() == {}
    
    def test_encode_bencode(self):
        """Test encoding to bencode format."""
        assert _encode_bencode(42) == b'i42e'
        assert _encode_bencode('hello') == b'5:hello'
        assert _encode_bencode([42, 'hello']) == b'li42e5:helloe'
        assert _encode_bencode({'hello': 42}) == b'd5:helloi42ee'


class TestNFOHandling:
    """Test NFO file reading and writing."""
    
    def test_read_nonexistent_nfo(self):
        """Test reading non-existent NFO file."""
        result = read_nfo_file('/nonexistent/file.nfo')
        assert result is None
    
    def test_write_and_read_nfo(self):
        """Test writing and reading NFO file."""
        with tempfile.NamedTemporaryFile(suffix='.nfo', delete=False) as tmp:
            tmp_path = Path(tmp.name)
        
        try:
            # Create test NFO
            root = ET.Element('movie')
            title = ET.SubElement(root, 'title')
            title.text = 'Test Movie'
            year = ET.SubElement(root, 'year')
            year.text = '2023'
            
            # Write NFO
            write_nfo_file(root, tmp_path)
            assert tmp_path.exists()
            
            # Read NFO back
            read_root = read_nfo_file(tmp_path)
            assert read_root is not None
            assert read_root.tag == 'movie'
            assert read_root.find('title').text == 'Test Movie'
            assert read_root.find('year').text == '2023'
            
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


class TestMetadataSourceExtraction:
    """Test metadata source extraction from filenames."""
    
    def test_extract_source_from_folder_nfo(self):
        """Test extracting source from folder-level NFO files."""
        assert extract_metadata_source('tmdb.nfo') == 'tmdb'
        assert extract_metadata_source('imdb.nfo') == 'imdb'
        assert extract_metadata_source('manual.nfo') == 'manual'
        assert extract_metadata_source('movie.nfo') == 'interop'
    
    def test_extract_source_from_file_nfo(self):
        """Test extracting source from file-level NFO files."""
        assert extract_metadata_source('Movie.mkv.tmdb.nfo') == 'tmdb'
        assert extract_metadata_source('Episode.S01E01.tvdb.nfo') == 'tvdb'
        assert extract_metadata_source('Book.epub.manual.nfo') == 'manual'
    
    def test_extract_source_unknown(self):
        """Test extracting source from unknown NFO files."""
        assert extract_metadata_source('random.nfo') == 'unknown'
        assert extract_metadata_source('something_else.nfo') == 'unknown'


class TestMediaFileDetection:
    """Test media file detection."""
    
    def test_video_files(self):
        """Test video file detection."""
        assert is_media_file('movie.mkv')
        assert is_media_file('episode.mp4')
        assert is_media_file('video.avi')
        assert is_media_file('show.webm')
    
    def test_audio_files(self):
        """Test audio file detection."""
        assert is_media_file('song.mp3')
        assert is_media_file('track.flac')
        assert is_media_file('audiobook.m4b')
        assert is_media_file('music.ogg')
    
    def test_book_files(self):
        """Test book file detection."""
        assert is_media_file('book.epub')
        assert is_media_file('document.pdf')
        assert is_media_file('ebook.mobi')
        assert is_media_file('text.azw3')
    
    def test_non_media_files(self):
        """Test non-media file detection."""
        assert not is_media_file('readme.txt')
        assert not is_media_file('data.json')
        assert not is_media_file('script.py')
        assert not is_media_file('config.ini')
    
    def test_case_insensitive(self):
        """Test case insensitive detection."""
        assert is_media_file('Movie.MKV')
        assert is_media_file('Song.MP3')
        assert is_media_file('Book.EPUB')