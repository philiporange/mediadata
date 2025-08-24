#!/usr/bin/env python3
"""
Test TMDB metadata retrieval for specific movie examples.

This test searches for classic movies to examine metadata formatting.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
load_dotenv(project_root / '.env')

from src.metadata import TMDBClient


def test_tmdb_examples():
    """Test TMDB searches for specific movie examples."""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # Get TMDB API key
    tmdb_api_key = os.environ.get('TMDB_API_KEY')
    if not tmdb_api_key:
        print("❌ No TMDB API key found in .env file")
        return False
    
    print(f"✅ Using TMDB API key: {tmdb_api_key[:8]}...")
    
    # Initialize TMDB client
    tmdb = TMDBClient(tmdb_api_key)
    
    # Test movies
    test_movies = [
        "The Exorcist",
        "12 Angry Men", 
        "Big Buck Bunny"
    ]
    
    print("\n" + "="*80)
    print("TMDB METADATA EXAMPLES")
    print("="*80)
    
    for movie_title in test_movies:
        print(f"\n🎬 Testing: '{movie_title}'")
        print("-" * 60)
        
        try:
            # Search for the movie
            search_results = tmdb.search_movie(movie_title)
            
            if not search_results:
                print(f"❌ No results found for '{movie_title}'")
                continue
            
            # Get the first result
            movie = search_results[0]
            movie_id = movie.get('id')
            
            print(f"📊 Search Results:")
            print(f"  Title: {movie.get('title')}")
            print(f"  Release Date: {movie.get('release_date')}")
            print(f"  ID: {movie_id}")
            print(f"  Overview (search): {movie.get('overview', 'N/A')[:100]}...")
            
            # Get detailed information
            if movie_id:
                details = tmdb.get_movie_details(movie_id)
                if details:
                    print(f"\n📋 Detailed Metadata:")
                    print(f"  Title: {details.get('title')}")
                    print(f"  Original Title: {details.get('original_title')}")
                    print(f"  Year: {details.get('release_date', '')[:4] if details.get('release_date') else 'N/A'}")
                    print(f"  Runtime: {details.get('runtime')} minutes")
                    
                    # Plot/Overview
                    plot = details.get('overview', '')
                    print(f"  Plot Length: {len(plot)} characters")
                    print(f"  Plot Preview: {plot[:150]}..." if len(plot) > 150 else f"  Plot: {plot}")
                    
                    # Rating
                    vote_average = details.get('vote_average')
                    vote_count = details.get('vote_count')
                    print(f"  Rating: {vote_average}/10 ({vote_count} votes)")
                    
                    # Genres
                    genres = details.get('genres', [])
                    genre_names = [g.get('name') for g in genres]
                    print(f"  Genres: {', '.join(genre_names)}")
                    
                    # Director (from credits)
                    credits = details.get('credits', {})
                    crew = credits.get('crew', [])
                    directors = [person['name'] for person in crew if person.get('job') == 'Director']
                    print(f"  Director(s): {', '.join(directors) if directors else 'N/A'}")
                    
                    # External IDs
                    external_ids = details.get('external_ids', {})
                    imdb_id = external_ids.get('imdb_id')
                    print(f"  IMDB ID: {imdb_id}")
                    
                    # Keywords
                    keywords = details.get('keywords', {}).get('keywords', [])
                    if keywords:
                        keyword_names = [k.get('name') for k in keywords[:5]]  # First 5
                        print(f"  Keywords: {', '.join(keyword_names)}")
                    
        except Exception as e:
            print(f"❌ Error processing '{movie_title}': {e}")
    
    print(f"\n" + "="*80)
    print("TEST COMPLETED")
    print("="*80)
    
    return True


if __name__ == "__main__":
    """Run the TMDB examples test."""
    
    success = test_tmdb_examples()
    
    if success:
        print("\n✅ TMDB examples test completed")
        sys.exit(0)
    else:
        print("\n❌ TMDB examples test failed")
        sys.exit(1)