"""
Media metadata management utilities for processing torrent files, NFO files, and metadata extraction.

This module provides core functionality for:
- Scanning and discovering torrent files
- Reading bencode-encoded torrent data
- Parsing and writing XML NFO files
- Computing info hashes for torrent identification
- File system utilities for media organization
"""

import os
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
import json


class BencodeDecoder:
    """Bencode decoder for reading torrent files."""
    
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
    
    def decode(self) -> Any:
        """Decode the bencode data starting from current position."""
        if self.pos >= len(self.data):
            raise ValueError("Unexpected end of data")
        
        char = chr(self.data[self.pos])
        
        if char == 'i':
            return self._decode_int()
        elif char == 'l':
            return self._decode_list()
        elif char == 'd':
            return self._decode_dict()
        elif char.isdigit():
            return self._decode_string()
        else:
            raise ValueError(f"Invalid bencode character: {char}")
    
    def _decode_int(self) -> int:
        """Decode integer from bencode format."""
        self.pos += 1  # skip 'i'
        end_pos = self.data.find(b'e', self.pos)
        if end_pos == -1:
            raise ValueError("Invalid integer encoding")
        
        int_str = self.data[self.pos:end_pos].decode('ascii')
        self.pos = end_pos + 1
        return int(int_str)
    
    def _decode_string(self) -> bytes:
        """Decode string from bencode format."""
        colon_pos = self.data.find(b':', self.pos)
        if colon_pos == -1:
            raise ValueError("Invalid string encoding")
        
        length_str = self.data[self.pos:colon_pos].decode('ascii')
        length = int(length_str)
        self.pos = colon_pos + 1
        
        if self.pos + length > len(self.data):
            raise ValueError("String length exceeds data")
        
        result = self.data[self.pos:self.pos + length]
        self.pos += length
        return result
    
    def _decode_list(self) -> List[Any]:
        """Decode list from bencode format."""
        self.pos += 1  # skip 'l'
        result = []
        
        while self.pos < len(self.data) and chr(self.data[self.pos]) != 'e':
            result.append(self.decode())
        
        if self.pos >= len(self.data):
            raise ValueError("Unterminated list")
        
        self.pos += 1  # skip 'e'
        return result
    
    def _decode_dict(self) -> Dict[bytes, Any]:
        """Decode dictionary from bencode format."""
        self.pos += 1  # skip 'd'
        result = {}
        
        while self.pos < len(self.data) and chr(self.data[self.pos]) != 'e':
            key = self.decode()
            if not isinstance(key, bytes):
                raise ValueError("Dictionary key must be a string")
            value = self.decode()
            result[key] = value
        
        if self.pos >= len(self.data):
            raise ValueError("Unterminated dictionary")
        
        self.pos += 1  # skip 'e'
        return result


def read_torrent_file(torrent_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Read and decode a torrent file.
    
    Args:
        torrent_path: Path to the .torrent file
        
    Returns:
        Decoded torrent data as dictionary with string keys
        
    Raises:
        FileNotFoundError: If torrent file doesn't exist
        ValueError: If torrent file is malformed
    """
    torrent_path = Path(torrent_path)
    
    if not torrent_path.exists():
        raise FileNotFoundError(f"Torrent file not found: {torrent_path}")
    
    with open(torrent_path, 'rb') as f:
        data = f.read()
    
    decoder = BencodeDecoder(data)
    raw_data = decoder.decode()
    
    # Convert byte keys to strings for easier handling
    def convert_keys(obj):
        if isinstance(obj, dict):
            return {k.decode('utf-8') if isinstance(k, bytes) else k: convert_keys(v) 
                   for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_keys(item) for item in obj]
        elif isinstance(obj, bytes):
            try:
                return obj.decode('utf-8')
            except UnicodeDecodeError:
                return obj
        return obj
    
    return convert_keys(raw_data)


def calculate_info_hash(torrent_data: Dict[str, Any]) -> str:
    """
    Calculate the info hash for a torrent.
    
    Args:
        torrent_data: Decoded torrent data
        
    Returns:
        Info hash as lowercase hexadecimal string
    """
    info_dict = torrent_data.get('info')
    if not info_dict:
        raise ValueError("Torrent data missing 'info' section")
    
    # Re-encode the info dict to bencode format for hashing
    info_bencode = _encode_bencode(info_dict)
    return hashlib.sha1(info_bencode).hexdigest().lower()


def _encode_bencode(obj: Any) -> bytes:
    """Encode object to bencode format."""
    if isinstance(obj, int):
        return f'i{obj}e'.encode('ascii')
    elif isinstance(obj, (str, bytes)):
        data = obj.encode('utf-8') if isinstance(obj, str) else obj
        return f'{len(data)}:'.encode('ascii') + data
    elif isinstance(obj, list):
        result = b'l'
        for item in obj:
            result += _encode_bencode(item)
        result += b'e'
        return result
    elif isinstance(obj, dict):
        result = b'd'
        # Sort keys for deterministic encoding
        for key in sorted(obj.keys()):
            result += _encode_bencode(key)
            result += _encode_bencode(obj[key])
        result += b'e'
        return result
    else:
        raise ValueError(f"Cannot encode type {type(obj)} to bencode")


def scan_torrent_files(directory: Union[str, Path], recursive: bool = True) -> List[Path]:
    """
    Scan directory for .torrent files.
    
    Args:
        directory: Directory to scan
        recursive: Whether to scan subdirectories
        
    Returns:
        List of paths to .torrent files
    """
    directory = Path(directory)
    pattern = '**/*.torrent' if recursive else '*.torrent'
    return list(directory.glob(pattern))


def get_torrent_info(torrent_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Extract useful information from a torrent file.
    
    Args:
        torrent_path: Path to torrent file
        
    Returns:
        Dictionary with torrent metadata including:
        - name: Main name from torrent
        - info_hash: SHA1 hash of info dict
        - files: List of files in torrent
        - total_size: Total size in bytes
        - announce: Primary tracker URL
        - creation_date: Unix timestamp if available
    """
    torrent_data = read_torrent_file(torrent_path)
    info_hash = calculate_info_hash(torrent_data)
    
    info = torrent_data.get('info', {})
    name = info.get('name', 'unknown')
    
    # Handle single-file vs multi-file torrents
    files = []
    total_size = 0
    
    if 'files' in info:
        # Multi-file torrent
        for file_info in info['files']:
            file_path = '/'.join(file_info.get('path', []))
            file_size = file_info.get('length', 0)
            files.append({'path': file_path, 'size': file_size})
            total_size += file_size
    else:
        # Single-file torrent
        file_size = info.get('length', 0)
        files.append({'path': name, 'size': file_size})
        total_size = file_size
    
    return {
        'name': name,
        'info_hash': info_hash,
        'files': files,
        'total_size': total_size,
        'announce': torrent_data.get('announce', ''),
        'creation_date': torrent_data.get('creation date'),
        'created_by': torrent_data.get('created by'),
        'comment': torrent_data.get('comment')
    }


def read_nfo_file(nfo_path: Union[str, Path]) -> Optional[ET.Element]:
    """
    Read and parse an XML NFO file.
    
    Args:
        nfo_path: Path to NFO file
        
    Returns:
        Parsed XML root element, or None if file doesn't exist or is invalid
    """
    nfo_path = Path(nfo_path)
    
    if not nfo_path.exists():
        return None
    
    try:
        tree = ET.parse(nfo_path)
        return tree.getroot()
    except ET.ParseError:
        return None


def write_nfo_file(root: ET.Element, nfo_path: Union[str, Path]) -> None:
    """
    Write XML NFO file with proper formatting.
    
    Args:
        root: XML root element to write
        nfo_path: Destination path for NFO file
    """
    nfo_path = Path(nfo_path)
    nfo_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Ensure UTF-8 encoding
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    
    with open(nfo_path, 'wb') as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding='utf-8', xml_declaration=False)


def create_library_structure(base_path: Union[str, Path], info_hash: str) -> Path:
    """
    Create the standard library directory structure for a torrent.
    
    Args:
        base_path: Base library directory
        info_hash: Torrent info hash
        
    Returns:
        Path to the created torrent directory
    """
    base_path = Path(base_path)
    torrent_dir = base_path / info_hash.lower()
    
    # Create standard directories
    (torrent_dir / 'data').mkdir(parents=True, exist_ok=True)
    (torrent_dir / 'metadata').mkdir(parents=True, exist_ok=True)
    (torrent_dir / 'metadata' / 'audit').mkdir(exist_ok=True)
    
    return torrent_dir


def find_nfo_files(directory: Union[str, Path], media_filename: Optional[str] = None) -> Dict[str, List[Path]]:
    """
    Find NFO files in a directory following the naming conventions.
    
    Args:
        directory: Directory to search
        media_filename: If provided, look for file-level NFO files for this media file
        
    Returns:
        Dictionary with 'folder' and 'file' keys containing lists of NFO paths
    """
    directory = Path(directory)
    result = {'folder': [], 'file': []}
    
    if not directory.exists():
        return result
    
    # Find folder-level NFO files
    for nfo_path in directory.glob('*.nfo'):
        # Skip if it looks like a file-level NFO
        if media_filename and nfo_path.stem.startswith(Path(media_filename).stem):
            continue
        result['folder'].append(nfo_path)
    
    # Find file-level NFO files if media filename provided
    if media_filename:
        media_stem = Path(media_filename).stem
        pattern = f"{media_stem}.*.nfo"
        result['file'].extend(directory.glob(pattern))
        
        # Also check for direct filename.nfo pattern
        direct_nfo = directory / f"{media_filename}.nfo"
        if direct_nfo.exists():
            result['file'].append(direct_nfo)
    
    return result


def extract_metadata_source(nfo_filename: str) -> str:
    """
    Extract the metadata source from an NFO filename.
    
    Args:
        nfo_filename: NFO filename (e.g., 'tmdb.nfo', 'Movie.mkv.imdb.nfo')
        
    Returns:
        Metadata source name or 'unknown'
    """
    filename = Path(nfo_filename).stem
    
    # Known sources
    sources = ['tmdb', 'imdb', 'tvdb', 'audible', 'openlibrary', 'goodreads', 
              'manual', 'override', 'scanner']
    
    for source in sources:
        if source in filename.lower():
            return source
    
    # Check for interop names
    interop_names = ['movie', 'tvshow', 'season', 'episode', 'artist', 'album', 'book', 'audiobook']
    for name in interop_names:
        if filename.lower() == name:
            return 'interop'
    
    return 'unknown'


def is_media_file(file_path: Union[str, Path]) -> bool:
    """
    Check if a file is a media file based on its extension.
    
    Args:
        file_path: Path to file
        
    Returns:
        True if file appears to be a media file
    """
    media_extensions = {
        # Video
        '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts',
        # Audio
        '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.wav', '.wma', '.m4b', '.opus',
        # Books
        '.epub', '.pdf', '.mobi', '.azw3', '.djvu', '.fb2', '.lit', '.pdb'
    }
    
    return Path(file_path).suffix.lower() in media_extensions