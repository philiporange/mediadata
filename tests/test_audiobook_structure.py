#!/usr/bin/env python3
"""
Test audiobook structure matching for MediaData.

This creates the correct file structure for the Box Office Murders audiobook torrent.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
load_dotenv(project_root / '.env')

from mediadata import MediaData, process_media


def test_audiobook_structure():
    """Test audiobook structure matching."""
    
    # Use fixed directory
    temp_path = Path("/tmp/mediadata_test")
    torrent_dir = temp_path / "torrents"
    media_dir = temp_path / "media" 
    archive_dir = temp_path / "archive"
    
    print(f"AudioBook Structure Test")
    print("=" * 50)
    
    # Get TMDB API key
    tmdb_api_key = os.environ.get('TMDB_API_KEY')
    if not tmdb_api_key:
        print("❌ No TMDB API key found")
        return False
    
    # Create the correct audiobook structure based on torrent
    audiobook_dir = media_dir / "boxofficemurders_2507_librivox"
    if audiobook_dir.exists():
        import shutil
        shutil.rmtree(audiobook_dir)
    
    audiobook_dir.mkdir(exist_ok=True)
    
    print("📚 Creating correct audiobook file structure...")
    
    # Create the main audiobook file (the torrent expects this exact name)
    main_file = audiobook_dir / "BoxOfficeMurders_LibriVox.m4b"
    mock_content = b"Mock audiobook content for Box Office Murders LibriVox recording"
    main_file.write_bytes(mock_content * 1000)  # Make it a bit larger
    
    # Create some of the other expected files
    other_files = [
        ("__ia_thumb.jpg", b"Mock thumbnail image"),
        ("boxoffice_murders_2507.jpg", b"Mock cover image"),
        ("boxoffice_murders_2507.pdf", b"Mock PDF content"),
    ]
    
    for filename, content in other_files:
        file_path = audiobook_dir / filename
        file_path.write_bytes(content)
    
    print(f"  ✅ Created {len(other_files) + 1} files")
    
    # List the structure
    print(f"\n📋 Current audiobook structure:")
    for file_path in audiobook_dir.iterdir():
        size = file_path.stat().st_size
        file_type = "🎵" if file_path.suffix in ['.m4b', '.mp3', '.m4a'] else "📄"
        print(f"  {file_type} {file_path.name} ({size:,} bytes)")
    
    # Clean archive for fresh test
    if archive_dir.exists():
        import shutil
        shutil.rmtree(archive_dir)
    archive_dir.mkdir(exist_ok=True)
    
    print(f"\n🔄 Running MediaData scan...")
    
    try:
        # Test just the audiobook
        with MediaData(archive_dir=str(archive_dir), tmdb_api_key=tmdb_api_key) as media:
            matches = media.scan_and_match(str(torrent_dir), str(media_dir))
            
            print(f"\n📊 Scan Results:")
            print(f"  Total matches found: {len(matches)}")
            
            for match in matches:
                print(f"\n🎯 Match: {match.name}")
                print(f"  Torrent file: {match.torrent_file.name}")
                print(f"  Info hash: {match.info_hash}")
                print(f"  Files matched: {len(match.files)}")
                print(f"  Complete: {match.complete}")
                
                # Show first few matched files
                for i, file_match in enumerate(match.files[:5]):
                    print(f"    {i+1}. {file_match.torrent_path} -> {file_match.local_path}")
                if len(match.files) > 5:
                    print(f"    ... and {len(match.files) - 5} more files")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    """Run the audiobook structure test."""
    
    success = test_audiobook_structure()
    
    if success:
        print(f"\n✅ AudioBook structure test completed")
        sys.exit(0)
    else:
        print(f"\n❌ AudioBook structure test failed")
        sys.exit(1)