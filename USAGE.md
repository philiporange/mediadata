# MediaData Usage Guide

MediaData is a media metadata management system that uses torrent files as the primary organizational structure. It creates immutable libraries with hash-based directories while generating Kodi/Jellyfin-compatible NFO metadata files.

## Quick Start

The fastest way to get started is using the `process` command with a unified folder approach:

```bash
# Process folders containing both torrents and media files
mediadata process /downloads /media/unsorted --archive /media/archive

# With TMDB metadata (requires API key)
export TMDB_API_KEY="your_api_key_here"
mediadata process /downloads /media --archive /archive --tmdb-key $TMDB_API_KEY
```

**Expected Output:**
```
ℹ Starting complete MediaData processing workflow
ℹ Folders to scan: ['/downloads', '/media/unsorted']
ℹ Archive: /media/archive
[████████████████████████████] 100.0% | Processing complete | 45.2s
✓ Complete Matches: 15
✓ Successfully Matched: 15 (100.0%)
✓ Organized into Library: 15
✓ Metadata Added: 12
```

## Installation

### Basic Installation

```bash
# Clone the repository
git clone https://github.com/philiporange/mediadata
cd mediadata

# Install dependencies
pip install -r requirements.txt

# Install as package (optional)
pip install -e .
```

### Dependencies

Required Python packages (automatically installed):
- Python 3.8+
- guessit >= 3.8.0
- requests >= 2.25.0
- colorama >= 0.4.0
- bencode.py
- lxml

### Optional Dependencies

For running the demo:
```bash
pip install torrentp requests
```

## Basic Usage

### Complete Workflow (Recommended)

Process everything in one command - scan folders for torrents and media, organize, and fetch metadata:

```bash
# Basic usage - process folders
mediadata process /torrents /media --archive /archive

# With all options
mediadata process /downloads /unsorted \
  --archive /library \
  --tmdb-key YOUR_KEY \
  --action copy \
  --collision compare \
  --dry-run \
  --verbose
```

**What this does:**
1. Scans specified folders for `.torrent` files
2. Matches torrents to media files in the same or other folders
3. Organizes matched files into hash-based archive structure
4. Fetches metadata from TMDB/Goodreads
5. Generates Kodi/Jellyfin-compatible NFO files

### Scan Only

Find and match torrents to media files without organizing:

```bash
# Scan folders for torrents and media
mediadata scan /downloads /media

# With hash verification (slower but ensures integrity)
mediadata scan /downloads /media --verify-hashes --verbose
```

**Expected Output:**
```
✓ Complete Matches: 12
⚠ Partial Matches: 3
⚠ Failed Matches: 1
```

### Organize Only

Organize already-matched torrents into library structure:

```bash
# Default - move files
mediadata organize /downloads /media --archive /archive

# Copy instead of move
mediadata organize /downloads /media --archive /archive --action copy

# Test first with dry-run
mediadata organize /downloads /media --archive /archive --dry-run
```

**Organization Actions:**
- `move` - Move files to archive (default)
- `copy` - Copy files, leaving originals
- `symlink` - Create symbolic links
- `hardlink` - Create hard links

**Collision Strategies:**
- `skip` - Skip existing files
- `overwrite` - Replace existing files
- `rename` - Rename new files
- `compare` - Compare and keep best (default)

### Metadata Only

Fetch metadata for existing library:

```bash
# Process metadata for archived torrents
mediadata metadata --archive /archive --tmdb-key YOUR_KEY

# With more workers for faster processing
mediadata metadata --archive /archive --max-workers 8 --verbose
```

### Library Status

Check library statistics:

```bash
mediadata status --archive /archive
```

**Expected Output:**
```
📁 Archive Directory: /media/archive
🎬 Total Torrents: 247
📄 Total Files: 1,582
💾 Total Size: 1.2 TB
🎭 TMDB API: ✓ Configured
📚 Goodreads: ✓ Available (no API key required)
```

### Torrent Information

Display details about a specific torrent file:

```bash
# Basic info
mediadata info /path/to/movie.torrent

# Detailed file list
mediadata info /path/to/movie.torrent --verbose
```

**Expected Output:**
```
📁 File: /downloads/movie.torrent
🏷️  Name: Big Buck Bunny (2008)
🔑 Info Hash: dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c
📄 Files: 1
💾 Size: 276.4 MB
📅 Created: 2008-05-09 14:30:45
```

## Python API Reference

### MediaData Class

Main interface for all operations.

```python
from mediadata import MediaData

# Initialize
media = MediaData(
    archive_dir='/path/to/archive',
    tmdb_api_key='your_key',           # Optional
    goodreads_cache_expire=3600,       # Cache time in seconds
    verify_hashes=False,                # Enable hash verification
    organize_action=OrganizeAction.MOVE,
    collision_strategy=CollisionStrategy.COMPARE,
    max_workers=4
)
```

**Parameters:**
- `archive_dir` (str|Path): Archive directory for organized library
- `tmdb_api_key` (str, optional): TMDB API key for movie/TV metadata
- `goodreads_cache_expire` (int): Cache expiration seconds (default: 3600)
- `verify_hashes` (bool): Verify file integrity using torrent hashes
- `organize_action` (OrganizeAction): How to handle files
- `collision_strategy` (CollisionStrategy): How to handle collisions
- `max_workers` (int): Number of parallel workers

### Complete Processing

```python
from mediadata import MediaData

with MediaData(archive_dir='/archive') as media:
    # Complete workflow in one call
    stats = media.process(
        folder_paths=['/downloads', '/media'],
        dry_run=False,
        progress_callback=lambda msg, pct: print(f"{pct}% - {msg}")
    )

    print(f"Processed {stats.successful_matches} torrents")
    print(f"Organized {stats.organized_torrents} files")
    print(f"Metadata: {stats.metadata_processed}")
```

**Returns:** ProcessingStats object with:
- `total_torrents_found`: Number of torrents discovered
- `successful_matches`: Torrents matched to files
- `organized_torrents`: Successfully organized torrents
- `metadata_processed`: Torrents with metadata added
- `total_files`: Total files processed
- `total_size_bytes`: Total size in bytes
- `processing_time_seconds`: Time taken
- `match_rate`: Percentage of torrents matched
- `organization_rate`: Percentage organized
- `metadata_rate`: Percentage with metadata

### Step-by-Step Processing

```python
from mediadata import MediaData

with MediaData(archive_dir='/archive', tmdb_api_key='KEY') as media:
    # Step 1: Scan and match
    matches = media.scan_and_match(
        folder_paths=['/downloads', '/media']
    )

    # Step 2: Organize
    organize_results = media.organize_torrents(
        torrent_matches=matches,
        dry_run=False
    )

    # Step 3: Fetch metadata
    metadata_results = media.fetch_metadata(
        organize_results=organize_results
    )
```

**Match Objects:**
```python
for match in matches:
    print(f"Name: {match.name}")
    print(f"Hash: {match.info_hash}")
    print(f"Complete: {match.complete}")
    print(f"Files: {len(match.files)}")
    for file in match.files:
        print(f"  - {file.torrent_path} -> {file.filesystem_path}")
```

**Organization Results:**
```python
for result in organize_results:
    if result.success:
        print(f"✓ {result.torrent_match.name}")
        print(f"  Target: {result.target_dir}")
        print(f"  Bytes: {result.bytes_processed}")
    else:
        print(f"✗ {result.error_message}")
```

**Metadata Results:**
```python
for result in metadata_results:
    if result.identification:
        print(f"Title: {result.identification.title}")
        print(f"Type: {result.identification.media_type}")
        print(f"Source: {result.identification.source}")
        print(f"IDs: {result.identification.external_ids}")
    if result.nfo_path:
        print(f"NFO: {result.nfo_path}")
```

### Convenience Function

Quick processing without creating MediaData instance:

```python
from mediadata import process_media, OrganizeAction

stats = process_media(
    folder_paths=['/downloads', '/media'],
    archive_dir='/archive',
    tmdb_api_key='YOUR_KEY',
    dry_run=False,
    verify_hashes=False,
    organize_action=OrganizeAction.COPY
)

print(f"Success rate: {stats.match_rate:.1%}")
```

### Library Management

```python
from mediadata import MediaData

media = MediaData('/archive')

# Get library statistics
stats = media.get_library_stats()
print(f"Torrents: {stats['total_torrents']}")
print(f"Size: {stats['total_size_human']}")

# Check if torrent exists
exists = media.check_torrent_exists('dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c')

# Get torrent by hash
torrent = media.get_torrent_by_hash('dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c')

# List all torrents
all_torrents = media.list_all_torrents(filter_type='matched')

# Clean up missing torrents
removed = media.cleanup_missing_torrents()
```

### Utility Functions

```python
from mediadata import (
    get_torrent_info,
    scan_torrent_files,
    read_nfo_file,
    write_nfo_file,
    is_media_file
)

# Get torrent information
info = get_torrent_info('/path/to/file.torrent')
print(info['name'])
print(info['info_hash'])
print(info['total_size'])
print(info['files'])  # List of file dictionaries

# Scan for torrent files
torrents = scan_torrent_files('/downloads', recursive=True)

# Read NFO file
nfo_data = read_nfo_file('/path/to/movie.nfo')

# Write NFO file
write_nfo_file('/path/to/output.nfo', nfo_dict)

# Check if file is media
if is_media_file('/path/to/file.mp4'):
    print("This is a media file")
```

## Configuration

### Environment Variables

```bash
# TMDB API key for movie/TV metadata
export TMDB_API_KEY="your_api_key_here"

# Default archive directory
export MEDIADATA_ARCHIVE="/path/to/archive"
```

### Configuration File

MediaData uses `~/.mediadata/` as the base directory for configuration and data storage.

**Default Paths:**
- Archive: `~/.mediadata/archive`
- Database: `~/.mediadata/scanner.db`
- Redis DB: `~/.mediadata/redis.rdb`
- Torrents: `~/.mediadata/torrents`
- Temp: `~/.mediadata/temp`

### Command-Line Options

**Global Options** (all commands):
```bash
--verbose, -v          # Enable detailed logging
--no-color             # Disable colored output
--config CONFIG        # Specify configuration file
```

**Processing Options:**
```bash
--archive PATH         # Archive directory (default: ~/.mediadata/archive)
--tmdb-key KEY         # TMDB API key
--goodreads-cache-expire SECONDS  # Cache time (default: 3600)
--max-workers N        # Parallel workers (default: 4)
--verify-hashes        # Enable hash verification
```

**Organization Options:**
```bash
--action {move,copy,symlink,hardlink}  # File handling (default: move)
--collision {skip,overwrite,rename,compare}  # Collision handling (default: compare)
--dry-run              # Preview without changes
```

## Archive Directory Structure

MediaData organizes media using a hash-based immutable structure:

```
/archive/
  └── dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c/  # Info hash directory
       ├── data/                                   # Immutable torrent payload
       │    ├── Big.Buck.Bunny.2008.mkv           # Media files
       │    └── poster.jpg                        # Optional art
       ├── source.torrent                         # Original torrent file
       └── metadata/                              # Archival sidecars
            ├── tmdb.nfo                          # TMDB metadata
            ├── manual.json                       # Manual overrides
            ├── logs/                             # Processing logs
            └── audit/                            # Audit trails
```

### NFO File Structure

MediaData generates Kodi/Jellyfin-compatible NFO files:

**Movie NFO** (`metadata/tmdb.nfo`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>Big Buck Bunny</title>
  <year>2008</year>
  <uniqueid type="tmdb" default="true">10378</uniqueid>
  <plot>A large buck bunny...</plot>
  <runtime>10</runtime>
  <director>Sacha Goedegebure</director>
  <ratings>
    <rating name="tmdb" max="10" default="true">
      <value>6.2</value>
      <votes>123</votes>
    </rating>
  </ratings>
  <art>
    <poster>file:poster.jpg</poster>
    <fanart>file:fanart.jpg</fanart>
  </art>
</movie>
```

**Audiobook NFO** (`metadata/manual.nfo`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<audiobook>
  <title>Sample Audiobook (Unabridged)</title>
  <author>Jane Author</author>
  <narrator>John Narrator</narrator>
  <publisher>AudioPub</publisher>
  <released>2023-04-15</released>
  <runtime>PT11H20M</runtime>
  <uniqueid type="audible" default="true">B012345678</uniqueid>
  <chapters relative="program">
    <chapter><number>1</number><title>Prologue</title><start>PT0H0M0S</start></chapter>
    <chapter><number>2</number><title>Chapter 1</title><start>PT0H12M30S</start></chapter>
  </chapters>
</audiobook>
```

## Common Patterns

### Processing Downloaded Media

```python
from mediadata import MediaData

# Process downloads folder with archive
with MediaData(archive_dir='/media/archive') as media:
    stats = media.process(
        folder_paths=['/downloads/complete'],
        dry_run=False
    )
```

### Copy Instead of Move

```python
from mediadata import MediaData, OrganizeAction

# Keep originals in downloads
with MediaData(
    archive_dir='/archive',
    organize_action=OrganizeAction.COPY
) as media:
    stats = media.process(folder_paths=['/downloads'])
```

### Test Before Organizing

```python
from mediadata import MediaData

with MediaData(archive_dir='/archive') as media:
    # Dry run first
    stats = media.process(
        folder_paths=['/downloads'],
        dry_run=True
    )

    # Review results, then run for real
    if stats.match_rate > 0.8:  # 80% success
        stats = media.process(
            folder_paths=['/downloads'],
            dry_run=False
        )
```

### Processing Multiple Sources

```python
from mediadata import MediaData

# Scan multiple directories at once
with MediaData(archive_dir='/archive') as media:
    stats = media.process(
        folder_paths=[
            '/downloads/movies',
            '/downloads/tv',
            '/unsorted/media',
            '/downloads/audiobooks'
        ]
    )
```

### Custom Progress Tracking

```python
from mediadata import MediaData

def progress_handler(message, percent):
    print(f"[{percent:5.1f}%] {message}")

with MediaData(archive_dir='/archive') as media:
    stats = media.process(
        folder_paths=['/downloads'],
        progress_callback=progress_handler
    )
```

### Verify File Integrity

```python
from mediadata import MediaData

# Enable hash verification (slower but ensures data integrity)
with MediaData(
    archive_dir='/archive',
    verify_hashes=True
) as media:
    stats = media.process(folder_paths=['/downloads'])
```

## Examples

### Example 1: Complete Movie Processing

```bash
# Set up API key
export TMDB_API_KEY="abc123def456"

# Process movie downloads
mediadata process /downloads/movies --archive /media/movies --verbose
```

**Input:**
```
/downloads/movies/
  ├── BigBuckBunny.torrent
  └── big-buck-bunny/
      └── Big.Buck.Bunny.2008.mkv
```

**Output:**
```
/media/movies/
  └── dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c/
       ├── data/
       │    └── Big.Buck.Bunny.2008.mkv
       ├── source.torrent
       └── metadata/
            └── tmdb.nfo
```

### Example 2: Audiobook Organization

```python
from mediadata import MediaData, OrganizeAction

# Copy audiobooks to archive (keep originals)
with MediaData(
    archive_dir='/media/audiobooks',
    organize_action=OrganizeAction.COPY
) as media:
    stats = media.process(
        folder_paths=['/downloads/audiobooks'],
        dry_run=False
    )

    print(f"Organized {stats.organized_torrents} audiobooks")
    print(f"Total size: {stats.total_size_bytes / 1024**3:.1f} GB")
```

### Example 3: Batch Processing with Retry

```python
from mediadata import MediaData
import time

folders = ['/downloads/batch1', '/downloads/batch2', '/downloads/batch3']

with MediaData(archive_dir='/archive', tmdb_api_key='KEY') as media:
    for folder in folders:
        print(f"Processing {folder}...")

        try:
            stats = media.process(
                folder_paths=[folder],
                dry_run=False
            )

            print(f"  Success: {stats.successful_matches} torrents")

        except Exception as e:
            print(f"  Error: {e}")
            continue

        time.sleep(1)  # Rate limiting
```

### Example 4: Database Queries

```python
from mediadata import MediaData

media = MediaData('/archive')

# Get all matched torrents
matched = media.list_all_torrents(filter_type='matched')

for torrent in matched:
    print(f"{torrent['name']}: {torrent['info_hash'][:8]}...")

# Find specific torrent
info_hash = 'dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c'
torrent = media.get_torrent_by_hash(info_hash)

if torrent:
    print(f"Found: {torrent.name}")
    print(f"Files: {len(torrent.files)}")
    print(f"Complete: {torrent.complete}")
```

### Example 5: Running the Demo

```bash
# Install demo dependencies
pip install torrentp requests

# Run the full demo (downloads sample torrents)
python demo.py
```

The demo:
1. Uses local torrent files from `assets/` folder
2. Downloads media content (Big Buck Bunny movie + audiobook)
3. Processes through complete MediaData workflow
4. Shows results in `/tmp/mediadata_test/archive/`

## Database Management

### View Database Statistics

```bash
mediadata db stats --archive /archive
```

**Output:**
```
📊 Total torrents: 247
✓ Matched torrents: 238
📈 Total matches: 1,582
📄 Single-file torrents: 156
📁 Multi-file torrents: 91
💾 Total size: 1.2 TB
```

### Clean Missing Torrents

```bash
# Dry run first
mediadata db clean --archive /archive --dry-run

# Actually clean
mediadata db clean --archive /archive
```

### Export Database

```bash
# Export to JSON
mediadata db export --archive /archive --format json -o torrents.json

# Export to CSV
mediadata db export --archive /archive --format csv -o torrents.csv
```

### Query Specific Torrent

```bash
mediadata query dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c \
  --archive /archive \
  --show-files \
  --show-locations
```

## Media Type Support

MediaData supports all major media types:

### Movies
- Single files or multi-file torrents
- Multiple editions (Director's Cut, Extended, etc.)
- TMDB metadata integration

### TV Series
- Season/episode organization
- Specials support
- TMDB metadata

### Audiobooks
- Single-file (`.m4b`) or multi-disc
- Chapter information
- Goodreads metadata

### Music
- Artist/album/track hierarchy
- MusicBrainz IDs
- Album art

### Books
- EPUB, PDF, MOBI, AZW3
- Series information
- Goodreads metadata

## Troubleshooting

### No torrents found

**Problem:** `mediadata scan` finds no torrents

**Solution:**
```bash
# Check that .torrent files exist
find /downloads -name "*.torrent"

# Ensure files have .torrent extension
ls -la /downloads/*.torrent
```

### No matches found

**Problem:** Torrents don't match to media files

**Solution:**
```bash
# Verify media files exist in scanned folders
mediadata scan /torrents /media --verbose

# Check that torrent name matches directory/file structure
mediadata info /path/to/file.torrent
```

### TMDB API errors

**Problem:** `TMDB API key required` or rate limit errors

**Solution:**
```bash
# Set API key
export TMDB_API_KEY="your_key_here"

# Reduce workers to avoid rate limits
mediadata process /downloads --archive /archive --max-workers 2

# Get free API key from https://www.themoviedb.org/settings/api
```

### Files not moved

**Problem:** Organize command doesn't move files

**Solution:**
```bash
# Check permissions
ls -la /downloads /archive

# Try dry run first to see what would happen
mediadata organize /downloads --archive /archive --dry-run --verbose

# Use copy instead if you want to keep originals
mediadata organize /downloads --archive /archive --action copy
```

### Hash verification fails

**Problem:** `Hash verification failed` errors

**Solution:**
```bash
# Skip hash verification if files are known good
mediadata process /downloads --archive /archive  # no --verify-hashes

# Check for corrupted files
mediadata scan /downloads --verify-hashes --verbose
```

### Database locked

**Problem:** `database is locked` error

**Solution:**
```python
# Close any MediaData instances properly
with MediaData(archive_dir='/archive') as media:
    # Operations here
    pass  # Automatically closes

# Or check for stuck processes
ps aux | grep mediadata
```

### Memory usage high

**Problem:** High memory usage with large torrents

**Solution:**
```bash
# Reduce worker count
mediadata process /downloads --archive /archive --max-workers 2

# Process in smaller batches
mediadata process /downloads/batch1 --archive /archive
mediadata process /downloads/batch2 --archive /archive
```

## FAQ

**Q: Can I use MediaData without torrent files?**
A: No, MediaData is specifically designed around torrents as the organizational structure. The torrent info hash is used as the unique identifier for each media item.

**Q: Does MediaData modify my original files?**
A: By default, yes - it moves files. Use `--action copy` to keep originals, or `--dry-run` to preview changes first.

**Q: What happens if I run the same torrent twice?**
A: MediaData checks for existing archives by info hash and will skip duplicates or handle them according to your `--collision` strategy.

**Q: Can I organize media already in my archive?**
A: Yes, use the `metadata` command to process metadata for existing archives without moving files.

**Q: How do I get a TMDB API key?**
A: Register at https://www.themoviedb.org/ and request an API key from Settings → API. It's free for non-commercial use.

**Q: Does this work with private trackers?**
A: Yes, MediaData only uses the .torrent file structure and doesn't connect to trackers or download content.

**Q: Can I customize the NFO format?**
A: NFO files follow the Kodi/Jellyfin standard. You can add manual overrides in `metadata/manual.nfo` which take precedence.

**Q: What's the difference between scan and process?**
A: `scan` only finds and matches torrents to files. `process` does scan + organize + metadata fetching all in one command.

**Q: How do I backup my library?**
A: The archive directory is self-contained. Back up the entire archive directory including torrent files, data, and metadata.

**Q: Can I run MediaData on a NAS or server?**
A: Yes, MediaData is designed for headless operation and works well on servers, NAS devices, or in Docker containers.