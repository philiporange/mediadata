#!/usr/bin/env python3
"""
MediaData Demo - Full End-to-End Example

This demo uses two local torrent files from the assets folder:
1. Big Buck Bunny (movie) - approximately 276 MB
2. Box Office Murders LibriVox (audiobook) - smaller size

It downloads the media content and runs the complete MediaData workflow 
including matching, organizing, metadata processing, and cleanup. This 
demonstrates the full capabilities of the MediaData system with real data.

Requirements:
- pip install torrentp requests
"""

import asyncio
import os
import sys
import shutil
import tempfile
import time
from pathlib import Path
import logging
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from torrentp import TorrentDownloader
from src.mediadata import MediaData, process_media
from src.organize import OrganizeAction
from src.utils import get_torrent_info


def setup_logging():
    """Set up logging for the test."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


async def download_torrent_async(torrent_path, save_path, timeout=60):
    """Download a single torrent using torrentp Python module."""
    print(f"📥 Downloading {torrent_path} to {save_path}")
    
    # Create save directory
    Path(save_path).mkdir(parents=True, exist_ok=True)
    
    try:
        # Create downloader
        downloader = TorrentDownloader(
            file_path=str(torrent_path), 
            save_path=str(save_path),
            stop_after_download=True
        )
        
        # Start download with timeout
        start_time = time.time()
        await asyncio.wait_for(downloader.start_download(), timeout=timeout)
        
        download_time = time.time() - start_time
        print(f"✅ Download completed in {download_time:.1f}s")
        
        return True
        
    except asyncio.TimeoutError:
        print(f"❌ Download timed out after {timeout}s")
        return False
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False


async def download_torrents():
    """Use local torrent files and download their content."""
    temp_path = Path("/tmp/mediadata_test")
    torrents_dir = temp_path / "torrents"
    media_dir = temp_path / "media"
    
    # Ensure directories exist
    torrents_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)
    
    # Get local torrent files from assets folder
    assets_dir = Path(__file__).parent / "assets"
    local_torrents = [
        {
            "source_file": assets_dir / "big-buck-bunny.torrent",
            "name": "big-buck-bunny.torrent", 
            "timeout": 600  # Larger file, longer timeout
        },
        {
            "source_file": assets_dir / "boxofficemurders_2507_librivox_archive.torrent",
            "name": "boxofficemurders_librivox.torrent",
            "timeout": 600  # Give it 10 minutes for the audiobook
        }
    ]
    
    # Copy torrent files from assets to test directory
    for torrent_info in local_torrents:
        source_file = torrent_info["source_file"]
        target_file = torrents_dir / torrent_info["name"]
        
        if not target_file.exists():
            if source_file.exists():
                print(f"📄 Copying torrent file: {source_file.name}")
                shutil.copy2(source_file, target_file)
                print(f"✅ Copied to {target_file}")
            else:
                print(f"❌ Source torrent file not found: {source_file}")
                continue
    
    # Download media files for both torrents concurrently
    download_tasks = []
    for torrent_info in local_torrents:
        torrent_file = torrents_dir / torrent_info["name"]
        if torrent_file.exists():
            # Get torrent info to determine target directory
            info = get_torrent_info(str(torrent_file))
            target_dir = media_dir / info["name"]
            
            # Skip download if files already exist and contain media files
            if target_dir.exists():
                existing_files = list(target_dir.iterdir())
                media_files = [f for f in existing_files if f.suffix.lower() in ['.mp4', '.mkv', '.avi', '.m4b', '.mp3', '.m4a']]
                if media_files:
                    print(f"⏭️  Skipping download - {info['name']} already exists with {len(media_files)} media files")
                    continue
                
            # Create download task
            task = download_torrent_async(
                torrent_file, 
                media_dir,
                timeout=torrent_info["timeout"]
            )
            download_tasks.append(task)
    
    # Execute downloads concurrently if any are needed
    if download_tasks:
        print(f"🚀 Starting {len(download_tasks)} concurrent downloads...")
        results = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        # Check results
        success_count = sum(1 for r in results if r is True)
        print(f"📊 Download results: {success_count}/{len(results)} successful")
        
        return success_count == len(results)
    else:
        print("✅ All torrent data already downloaded")
        return True


def analyze_media_structure(media_dir):
    """Analyze and display the downloaded media structure."""
    print(f"\n📋 Media Structure Analysis:")
    
    total_size = 0
    file_count = 0
    
    for root, dirs, files in os.walk(media_dir):
        level = root.replace(str(media_dir), '').count(os.sep)
        indent = '  ' * level
        dir_name = os.path.basename(root) or 'media'
        print(f"{indent}📁 {dir_name}/")
        
        subindent = '  ' * (level + 1)
        for file in files:
            file_path = Path(root) / file
            size = file_path.stat().st_size
            total_size += size
            file_count += 1
            
            # File type emoji
            if file.endswith(('.mp4', '.mkv', '.avi')):
                emoji = "🎬"
            elif file.endswith(('.m4b', '.mp3', '.m4a')):
                emoji = "🎵"
            elif file.endswith(('.nfo', '.xml')):
                emoji = "📋"
            else:
                emoji = "📄"
                
            print(f"{subindent}{emoji} {file} ({size:,} bytes)")
    
    print(f"\n📊 Total: {file_count} files, {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")
    return file_count, total_size


def select_best_files_and_cleanup(media_dir):
    """
    Select the best files from each torrent and clean up redundant ones.
    This simulates the logic of keeping only the best quality/most useful files.
    """
    print(f"\n🔧 Selecting best files and cleaning up...")
    
    for item in Path(media_dir).iterdir():
        if not item.is_dir():
            continue
            
        print(f"  Processing {item.name}...")
        files = list(item.iterdir())
        
        # For movie directories - keep main video file and important sidecars
        video_files = [f for f in files if f.suffix.lower() in ['.mp4', '.mkv', '.avi']]
        if video_files:
            # Keep the largest video file (assume best quality)
            best_video = max(video_files, key=lambda f: f.stat().st_size)
            files_to_keep = {best_video}
            
            # Keep important sidecar files
            for f in files:
                if f.suffix.lower() in ['.srt', '.nfo'] or f.name.lower() in ['poster.jpg', 'fanart.jpg']:
                    files_to_keep.add(f)
            
            # Remove redundant files
            for f in files:
                if f not in files_to_keep:
                    print(f"    🗑️  Removing redundant: {f.name}")
                    f.unlink()
        
        # For audiobook directories - keep the main audio files
        audio_files = [f for f in files if f.suffix.lower() in ['.m4b', '.mp3', '.m4a']]
        if audio_files:
            # Keep all audio files but remove redundant formats if multiple exist
            if len(audio_files) > 5:  # If too many small parts, keep just a few for testing
                files_to_keep = set(audio_files[:3])  # Keep first 3 parts
                for f in audio_files[3:]:
                    print(f"    🗑️  Removing excess audio part: {f.name}")
                    f.unlink()


def run_demo():
    """Run the MediaData demo."""
    # Load environment variables from .env file
    load_dotenv()
    
    setup_logging()
    
    print("🚀 MediaData Full End-to-End Demo")
    print("=" * 60)
    
    start_time = time.time()
    
    # Set up paths
    temp_path = Path("/tmp/mediadata_test")
    torrents_dir = temp_path / "torrents"
    media_dir = temp_path / "media"
    archive_dir = temp_path / "archive"
    
    # Clean up archive for fresh test
    if archive_dir.exists():
        shutil.rmtree(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Step 1: Setup torrents and download content
        print(f"\n📡 Step 1: Using local torrents and downloading content...")
        download_success = asyncio.run(download_torrents())
        if not download_success:
            print("❌ Content downloads failed")
            return False
        
        # Step 2: Analyze media structure
        file_count, total_size = analyze_media_structure(media_dir)
        if file_count == 0:
            print("❌ No media files found after download")
            return False
        
        # Step 3: Select best files and cleanup
        select_best_files_and_cleanup(media_dir)
        
        # Step 4: Run MediaData processing
        print(f"\n🔄 Step 4: Running MediaData processing...")
        
        # Get TMDB API key from environment variables
        tmdb_api_key = os.getenv('TMDB_API_KEY')
        if tmdb_api_key:
            print(f"  ✅ Using TMDB API key from environment")
        else:
            print(f"  ⚠️  No TMDB_API_KEY found in environment - metadata fetching will be limited")
        
        stats = process_media(
            folder_paths=[str(torrents_dir), str(media_dir)], 
            archive_dir=str(archive_dir),
            tmdb_api_key=tmdb_api_key,
            dry_run=False,
            verify_hashes=False,  # Skip hash verification for speed
            organize_action=OrganizeAction.COPY
        )
        
        # Step 5: Analyze results
        print(f"\n📊 Step 5: Processing Results")
        print("-" * 40)
        print(f"  Torrents found: {stats.total_torrents_found}")
        print(f"  Successful matches: {stats.successful_matches}")
        print(f"  Organized torrents: {stats.organized_torrents}")
        print(f"  Metadata processed: {stats.metadata_processed}")
        print(f"  Processing time: {stats.processing_time_seconds:.2f}s")
        
        # Check if processing was successful based on statistics
        success_rate = stats.successful_matches / stats.total_torrents_found if stats.total_torrents_found > 0 else 0
        if success_rate < 1.0:
            print(f"  ⚠️  Match rate: {success_rate:.1%} ({stats.total_torrents_found - stats.successful_matches} unmatched)")
        
        # Step 6: Verify archive structure
        print(f"\n🏛️  Step 6: Archive Verification")
        print("-" * 40)
        
        archive_count = 0
        nfo_count = 0
        
        for item in archive_dir.iterdir():
            if item.is_dir() and len(item.name) == 40:  # Info hash directory
                archive_count += 1
                print(f"  📦 Archive: {item.name[:8]}...")
                
                # Check for data and metadata
                data_dir = item / "data"
                metadata_dir = item / "metadata"
                
                if data_dir.exists():
                    data_files = list(data_dir.iterdir())
                    print(f"    📁 Data: {len(data_files)} files")
                
                if metadata_dir.exists():
                    nfo_files = list(metadata_dir.glob("*.nfo"))
                    nfo_count += len(nfo_files)
                    for nfo in nfo_files:
                        content_preview = nfo.read_text()[:100].strip()
                        if '<movie>' in content_preview:
                            print(f"    🎬 Movie NFO: {nfo.name}")
                        elif '<audiobook>' in content_preview:
                            print(f"    📚 Audiobook NFO: {nfo.name}")
                        else:
                            print(f"    📋 NFO: {nfo.name}")
        
        # Show final results
        total_time = time.time() - start_time
        success = (archive_count >= 1)
        
        print(f"\n🎯 Demo Results:")
        print("-" * 40)
        print(f"  Archives created: {archive_count}")
        print(f"  NFO files generated: {nfo_count}")
        print(f"  Total time: {total_time:.1f}s")
        
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"\n🏁 Demo Status: {status}")
        
        if success:
            print(f"\n💡 Check the archive at: {archive_dir}")
            print("   You can explore the organized media and generated metadata!")
        
        return success
        
    except Exception as e:
        print(f"❌ Demo failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point for the demo."""
    print(__doc__)
    
    # Check for required dependencies
    try:
        import torrentp
        import requests
    except ImportError as e:
        print(f"❌ Missing required dependency: {e}")
        print("\n🔧 Install with: pip install torrentp requests")
        sys.exit(1)
    
    success = run_demo()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()