# MediaData

A media metadata management system that uses torrent files as the primary organizational structure. MediaData creates immutable libraries with hash-based directories while generating Kodi/Jellyfin-compatible NFO metadata files.

## Features

- **Immutable Library Organization**: Uses torrent info hashes to create permanent, collision-free directory structures
- **Multi-Source Metadata**: Hierarchical identification from NFO files → torrent names → filenames → media tags
- **TMDB Integration**: Automatic metadata fetching for movies and TV shows
- **Professional Filename Parsing**: Uses guessit library for accurate media file identification
- **NFO Compatibility**: Generates Kodi/Jellyfin-compatible XML metadata files
- **Comprehensive CLI**: Full command-line interface for all operations
- **Progress Reporting**: Real-time progress updates with colored output
- **Audit Trails**: Complete logging of all operations with JSON audit logs

## Directory Structure

MediaData organizes media using a hash-based immutable structure:

```
/archive/
  └── <infohash>/
       ├── data/                     # exact torrent payload (immutable)
       │    ├── <files...>           # media files
       │    └── movie.nfo            # consumed metadata (optional)
       ├── source.torrent            # original torrent file
       └── metadata/                 # archival sidecars
            ├── tmdb.nfo
            ├── manual.json
            └── audit/
```

## Installation

```bash
# Clone repository
git clone https://github.com/philiporange/mediadata
cd mediadata

# Install dependencies
pip install -r requirements.txt

# Make executable
chmod +x mediadata
```

Or install as a package:

```bash
pip install -e .
```

## Quick Start

```bash
# Complete workflow - scan torrents, organize files, fetch metadata
./mediadata process /path/to/torrents /path/to/media /path/to/archive

# Set TMDB API key
export TMDB_API_KEY="your_api_key_here"

# Dry run to see what would happen
./mediadata process /torrents /media /archive --dry-run --verbose
```

## Commands

### Process (Complete Workflow)
```bash
# Scan torrents, organize files, and fetch metadata in one command
mediadata process /torrents /media /archive
mediadata process /torrents /media /archive --tmdb-key YOUR_KEY --dry-run
```

### Scan (Torrent Matching)
```bash
# Scan for torrents and match to media files
mediadata scan /torrents /media
mediadata scan /torrents /media --verify-hashes --verbose
```

### Organize (Library Organization) 
```bash
# Organize matched torrents into hash-based library structure
mediadata organize /torrents /media /archive
mediadata organize /torrents /media /archive --action copy --collision compare
```

### Metadata (TMDB Fetching)
```bash
# Fetch metadata for existing library torrents
mediadata metadata /archive --tmdb-key YOUR_KEY
mediadata metadata /archive --max-workers 8 --verbose
```

### Status (Library Information)
```bash
# Show library statistics and status
mediadata status /archive
mediadata status /archive --verbose
```

### Info (Torrent Details)
```bash
# Display information about a torrent file
mediadata info /path/to/movie.torrent
```

## Configuration

### Environment Variables
- `TMDB_API_KEY`: Your TMDB API key for metadata fetching
- `MEDIADATA_ARCHIVE`: Default archive directory path

### Global Options
- `--verbose, -v`: Enable detailed logging output
- `--no-color`: Disable colored terminal output
- `--config CONFIG`: Specify configuration file path

### Organization Options
- `--action {move,copy,symlink,hardlink}`: How to handle files (default: move)
- `--collision {skip,overwrite,rename,compare}`: Handle file conflicts (default: compare)
- `--verify-hashes`: Enable torrent piece hash verification
- `--dry-run`: Preview operations without making changes

## Python API

```python
from mediadata import MediaData, process_media_directory

# Using the main class
with MediaData(
    archive_dir='/path/to/archive',
    tmdb_api_key='your_key',
    verify_hashes=True
) as media:
    
    # Scan for torrents and matches
    matches = media.scan_and_match('/torrents', '/media')
    
    # Organize into library
    results = media.organize_torrents(matches)
    
    # Fetch metadata
    metadata = media.fetch_metadata(results)

# Using convenience function
stats = process_media_directory(
    torrent_dir='/path/to/torrents',
    data_dir='/path/to/media', 
    archive_dir='/path/to/archive',
    tmdb_api_key='your_key',
    dry_run=False
)

print(f"Processed {stats.successful_matches} torrents")
```

## Media Type Support

- **Movies**: Single files or folders with multiple editions
- **TV Series**: Season/episode organization with specials support  
- **Music**: Artist/album/track hierarchy
- **Music Videos**: Individual video files with artist metadata
- **Books**: EPUB, PDF, and other text formats
- **Audiobooks**: Single-file or multi-disc collections with chapter support

## Metadata Sources

MediaData uses a hierarchical identification system:

1. **Existing NFO files** (highest priority)
2. **Torrent names** parsed with guessit
3. **Directory and file names**
4. **Media file tags** (lowest priority)

External metadata sources:
- **TMDB** (The Movie Database) - Movies and TV shows
- **Manual entries** - User-provided metadata
- **Scanner detection** - Automatic filename parsing

## Requirements

- Python 3.8+
- guessit >= 3.8.0
- requests >= 2.25.0
- colorama >= 0.4.0

## Development

```bash
# Install development dependencies
pip install -e .
pip install pytest

# Run tests
pytest tests/

# Run specific test file
pytest tests/test_mediadata.py -v
```

## License

CC0 1.0 Universal (CC0 1.0) Public Domain Dedication

This work has been dedicated to the public domain.