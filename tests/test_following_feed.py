#!/usr/bin/env python3
"""
Test script to investigate Instagram's chronological following feed.

This script tests different approaches to access the chronological "Following" 
feed that's available on Instagram web via ?variant=following.

Usage:
    python tests/test_following_feed.py
    
Requirements:
    - .env file with INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD
    - Existing session at ./data/instagram_session.json (created on first run)
"""

import os
import sys
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import ClientError
from src.instagram_client import InstagramClient, InstagramPost

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestInstagramClient(InstagramClient):
    """Extended client for testing different feed parameters."""
    
    def get_timeline_feed_modified(self, extra_params: Dict[str, Any], count: int = 50) -> List[InstagramPost]:
        """
        Fetch timeline with modified parameters injected into the request.
        
        Args:
            extra_params: Additional parameters to inject into API request
            count: Number of posts to fetch
            
        Returns:
            List of InstagramPost objects
        """
        logger.info(f"Testing with extra params: {extra_params}")
        
        def _fetch():
            posts = []
            max_id = None
            page_count = 0
            max_pages = 15  # Fetch more pages for comprehensive testing
            
            while len(posts) < count and page_count < max_pages:
                page_count += 1
                
                logger.debug(f"Fetching page {page_count} (max_id={max_id})")
                
                # Make custom request with injected parameters
                try:
                    # Build base data dict (copied from instagrapi's implementation)
                    data = {
                        "has_camera_permission": "1",
                        "feed_view_info": "[]",
                        "phone_id": self.client.phone_id,
                        "reason": "pagination" if max_id else "pull_to_refresh",
                        "battery_level": 100,
                        "timezone_offset": str(self.client.timezone_offset),
                        "device_id": self.client.uuid,
                        "request_id": self.client.request_id,
                        "_uuid": self.client.uuid,
                        "is_charging": 0,
                        "is_dark_mode": 1,
                        "will_sound_on": 0,
                        "session_id": self.client.client_session_id,
                        "bloks_versioning_id": self.client.bloks_versioning_id,
                        "is_pull_to_refresh": "0" if max_id else "1",
                    }
                    
                    if max_id:
                        data["max_id"] = max_id
                    
                    # Inject extra parameters
                    data.update(extra_params)
                    
                    # Make the request
                    headers = {
                        "X-Ads-Opt-Out": "0",
                        "X-DEVICE-ID": self.client.uuid,
                        "X-CM-Bandwidth-KBPS": "-1.000",
                        "X-CM-Latency": "2",
                    }
                    
                    timeline_response = self.client.private_request(
                        "feed/timeline/",
                        json.dumps(data),
                        with_signature=False,
                        headers=headers
                    )
                    
                except Exception as e:
                    logger.error(f"Request failed: {e}")
                    break
                
                items = timeline_response.get("feed_items", [])
                if not items:
                    logger.debug("No more feed items available")
                    break
                
                # Process items (same logic as regular get_timeline_feed)
                page_posts_added = 0
                page_ads_skipped = 0
                
                for item in items:
                    if len(posts) >= count:
                        break
                    
                    try:
                        media_data = item.get("media_or_ad")
                        if not media_data:
                            continue
                        
                        # Skip ads
                        if media_data.get("dr_ad_type") or media_data.get("is_paid_partnership"):
                            page_ads_skipped += 1
                            continue
                        
                        # Fix Pydantic validation issues
                        if "clips_metadata" in media_data:
                            clips = media_data.get("clips_metadata", {})
                            if isinstance(clips, dict) and "original_sound_info" in clips:
                                sound_info = clips.get("original_sound_info", {})
                                if isinstance(sound_info, dict) and sound_info.get("audio_filter_infos") is None:
                                    sound_info["audio_filter_infos"] = []
                        
                        from instagrapi.extractors import extract_media_v1
                        media = extract_media_v1(media_data)
                        
                        post = self._convert_media_to_post(media)
                        if post:
                            posts.append(post)
                            page_posts_added += 1
                    except Exception as e:
                        logger.warning(f"Failed to convert media item: {e}")
                        continue
                
                logger.info(f"Page {page_count}: added {page_posts_added} posts, skipped {page_ads_skipped} ads")
                
                # Get next page cursor
                next_max_id = timeline_response.get("next_max_id")
                if not next_max_id or next_max_id == max_id:
                    logger.debug("No more pages available")
                    break
                
                max_id = next_max_id
                time.sleep(1)  # Rate limiting
            
            logger.info(f"Fetched {len(posts)} posts across {page_count} pages")
            return posts
        
        return self._retry_with_backoff(_fetch)
    
    def try_following_endpoint(self, count: int = 50) -> Optional[List[InstagramPost]]:
        """
        Test if feed/following/ endpoint exists.
        
        Args:
            count: Number of posts to fetch
            
        Returns:
            List of posts if successful, None if endpoint doesn't exist
        """
        logger.info("Testing feed/following/ endpoint")
        
        try:
            # Try the following endpoint
            data = {
                "phone_id": self.client.phone_id,
                "device_id": self.client.uuid,
                "_uuid": self.client.uuid,
            }
            
            response = self.client.private_request(
                "feed/following/",
                json.dumps(data),
                with_signature=False
            )
            
            logger.info("feed/following/ endpoint exists!")
            # Parse response similar to timeline feed
            # (Would need to implement full parsing if this works)
            return None  # Placeholder
            
        except ClientError as e:
            if "404" in str(e):
                logger.info("feed/following/ endpoint does not exist (404)")
            else:
                logger.error(f"Error testing feed/following/: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error testing feed/following/: {e}")
            return None
    
    def get_user_profile_posts(self, username: str, count: int = 50) -> List[InstagramPost]:
        """
        Fetch posts from a specific user's profile.
        
        Args:
            username: Instagram username
            count: Number of posts to fetch
            
        Returns:
            List of InstagramPost objects
        """
        logger.info(f"Fetching posts from @{username}'s profile")
        
        try:
            # Get user ID
            user_id = self.client.user_id_from_username(username)
            logger.debug(f"User @{username} has ID: {user_id}")
            
            # Fetch user's media
            medias = self.client.user_medias(user_id, amount=count)
            logger.info(f"Fetched {len(medias)} posts from @{username}")
            
            # Convert to InstagramPost format
            posts = []
            for media in medias:
                post = self._convert_media_to_post(media)
                if post:
                    posts.append(post)
            
            return posts
            
        except Exception as e:
            logger.error(f"Failed to fetch user profile posts: {e}")
            return []


def analyze_posts(posts: List[InstagramPost], test_name: str) -> Dict[str, Any]:
    """
    Analyze a list of posts and extract metrics.
    
    Args:
        posts: List of InstagramPost objects
        test_name: Name of the test for logging
        
    Returns:
        Dictionary with analysis results
    """
    if not posts:
        return {
            "test_name": test_name,
            "total_posts": 0,
            "rnz_posts": 0,
            "other_accounts": [],
            "date_range": None,
            "is_chronological": False,
            "posts_detail": []
        }
    
    # Count posts by author
    rnz_posts = [p for p in posts if p.author_username == "radionewzealand"]
    other_accounts = list(set(p.author_username for p in posts if p.author_username != "radionewzealand"))
    
    # Check chronological ordering
    timestamps = [p.posted_at for p in posts]
    is_chronological = timestamps == sorted(timestamps, reverse=True)  # Newest first
    
    # Date range
    oldest = min(timestamps) if timestamps else None
    newest = max(timestamps) if timestamps else None
    
    # Detailed post list
    posts_detail = [
        {
            "author": p.author_username,
            "posted_at": p.posted_at.isoformat(),
            "type": p.post_type,
            "caption_preview": (p.caption[:60] + "...") if p.caption and len(p.caption) > 60 else p.caption
        }
        for p in posts[:20]  # First 20 for readability
    ]
    
    return {
        "test_name": test_name,
        "total_posts": len(posts),
        "rnz_posts": len(rnz_posts),
        "rnz_posts_list": [
            {
                "posted_at": p.posted_at.isoformat(),
                "caption_preview": (p.caption[:60] + "...") if p.caption else None
            }
            for p in rnz_posts
        ],
        "other_accounts": other_accounts,
        "other_accounts_count": len(other_accounts),
        "date_range": {
            "oldest": oldest.isoformat() if oldest else None,
            "newest": newest.isoformat() if newest else None
        },
        "is_chronological": is_chronological,
        "posts_detail": posts_detail
    }


def run_all_tests(client: TestInstagramClient) -> Dict[str, Any]:
    """
    Run all test configurations.
    
    Args:
        client: Authenticated TestInstagramClient instance
        
    Returns:
        Dictionary with all test results
    """
    results = {}
    
    # Test 1: Baseline - Current algorithmic timeline
    logger.info("\n" + "="*70)
    logger.info("TEST 1: BASELINE - Algorithmic Timeline")
    logger.info("="*70)
    posts = client.get_timeline_feed(count=50)
    results["baseline"] = analyze_posts(posts, "Baseline (Algorithmic Timeline)")
    time.sleep(3)
    
    # Test 2: feed_view_mode parameter
    logger.info("\n" + "="*70)
    logger.info("TEST 2: feed_view_mode='following'")
    logger.info("="*70)
    posts = client.get_timeline_feed_modified({"feed_view_mode": "following"}, count=50)
    results["feed_view_mode"] = analyze_posts(posts, "feed_view_mode='following'")
    time.sleep(3)
    
    # Test 3: timeline_type parameter
    logger.info("\n" + "="*70)
    logger.info("TEST 3: timeline_type='following'")
    logger.info("="*70)
    posts = client.get_timeline_feed_modified({"timeline_type": "following"}, count=50)
    results["timeline_type"] = analyze_posts(posts, "timeline_type='following'")
    time.sleep(3)
    
    # Test 4: variant parameter
    logger.info("\n" + "="*70)
    logger.info("TEST 4: variant='following'")
    logger.info("="*70)
    posts = client.get_timeline_feed_modified({"variant": "following"}, count=50)
    results["variant"] = analyze_posts(posts, "variant='following'")
    time.sleep(3)
    
    # Test 5: is_following_only parameter
    logger.info("\n" + "="*70)
    logger.info("TEST 5: is_following_only='1'")
    logger.info("="*70)
    posts = client.get_timeline_feed_modified({"is_following_only": "1"}, count=50)
    results["is_following_only"] = analyze_posts(posts, "is_following_only='1'")
    time.sleep(3)
    
    # Test 6: feed_type parameter
    logger.info("\n" + "="*70)
    logger.info("TEST 6: feed_type='following'")
    logger.info("="*70)
    posts = client.get_timeline_feed_modified({"feed_type": "following"}, count=50)
    results["feed_type"] = analyze_posts(posts, "feed_type='following'")
    time.sleep(3)
    
    # Test 7: Combined parameters
    logger.info("\n" + "="*70)
    logger.info("TEST 7: Combined Parameters")
    logger.info("="*70)
    combined_params = {
        "feed_view_mode": "following",
        "timeline_type": "following",
        "is_following_only": "1"
    }
    posts = client.get_timeline_feed_modified(combined_params, count=50)
    results["combined"] = analyze_posts(posts, "Combined Parameters")
    time.sleep(3)
    
    # Test 8: Alternative endpoint
    logger.info("\n" + "="*70)
    logger.info("TEST 8: feed/following/ Endpoint")
    logger.info("="*70)
    posts = client.try_following_endpoint(count=50)
    results["following_endpoint"] = {
        "test_name": "feed/following/ Endpoint",
        "endpoint_exists": posts is not None,
        "total_posts": 0,
        "rnz_posts": 0,
        "message": "Endpoint not available" if posts is None else "Endpoint exists (parsing needed)"
    }
    time.sleep(3)
    
    # Test 9: User Profile Feed (radionewzealand)
    logger.info("\n" + "="*70)
    logger.info("TEST 9: User Profile Feed (@radionewzealand)")
    logger.info("="*70)
    posts = client.get_user_profile_posts("radionewzealand", count=50)
    results["user_profile"] = analyze_posts(posts, "User Profile Feed (@radionewzealand)")
    
    return results


def generate_report(results: Dict[str, Any]) -> str:
    """
    Generate human-readable report from test results.
    
    Args:
        results: Dictionary with all test results
        
    Returns:
        Formatted report string
    """
    report = []
    report.append("=" * 80)
    report.append("INSTAGRAM FOLLOWING FEED INVESTIGATION RESULTS")
    report.append("=" * 80)
    report.append(f"\nTest completed: {datetime.now().isoformat()}")
    report.append(f"\nGoal: Find method to access chronological following feed")
    report.append(f"Success Criteria: 10+ RNZ posts (vs baseline)")
    report.append("\n")
    
    # Baseline summary
    baseline = results.get("baseline", {})
    report.append("=" * 80)
    report.append("BASELINE: Current Algorithmic Timeline")
    report.append("=" * 80)
    report.append(f"Total posts: {baseline.get('total_posts', 0)}")
    report.append(f"RNZ posts: {baseline.get('rnz_posts', 0)} {'❌' if baseline.get('rnz_posts', 0) < 10 else '✅'}")
    report.append(f"Other accounts: {baseline.get('other_accounts_count', 0)} (should be 0 - these are ads)")
    if baseline.get('other_accounts'):
        report.append(f"  Accounts: {', '.join(baseline.get('other_accounts', []))}")
    report.append(f"Chronological order: {'Yes ✅' if baseline.get('is_chronological') else 'No ❌'}")
    date_range = baseline.get('date_range', {})
    report.append(f"Date range: {date_range.get('oldest', 'N/A')} to {date_range.get('newest', 'N/A')}")
    report.append("")
    
    # Test results
    test_keys = [k for k in results.keys() if k != "baseline"]
    successful_tests = []
    
    for test_key in test_keys:
        result = results[test_key]
        report.append("=" * 80)
        report.append(f"TEST: {result.get('test_name', test_key)}")
        report.append("=" * 80)
        
        rnz_count = result.get('rnz_posts', 0)
        baseline_rnz = baseline.get('rnz_posts', 0)
        is_success = rnz_count >= 10
        is_better = rnz_count > baseline_rnz
        
        report.append(f"Total posts: {result.get('total_posts', 0)}")
        report.append(f"RNZ posts: {rnz_count} {'✅ SUCCESS!' if is_success else '❌'} (baseline: {baseline_rnz}, diff: {rnz_count - baseline_rnz:+d})")
        report.append(f"Other accounts: {result.get('other_accounts_count', 0)} (should be 0)")
        if result.get('other_accounts'):
            report.append(f"  Accounts: {', '.join(result.get('other_accounts', []))}")
        report.append(f"Chronological order: {'Yes ✅' if result.get('is_chronological') else 'No ❌'}")
        date_range = result.get('date_range', {})
        report.append(f"Date range: {date_range.get('oldest', 'N/A')} to {date_range.get('newest', 'N/A')}")
        
        if is_success:
            successful_tests.append(test_key)
            report.append(f"\n🎉 THIS TEST MET SUCCESS CRITERIA! ({rnz_count} RNZ posts)")
        elif is_better:
            report.append(f"\n⚠️ Better than baseline but didn't meet 10+ threshold")
        
        report.append("")
    
    # Final recommendation
    report.append("=" * 80)
    report.append("RECOMMENDATION")
    report.append("=" * 80)
    
    if successful_tests:
        report.append(f"\n✅ SUCCESS! Found {len(successful_tests)} working method(s):")
        for test_key in successful_tests:
            result = results[test_key]
            report.append(f"\n  • {result.get('test_name')}")
            report.append(f"    RNZ posts: {result.get('rnz_posts')}")
            report.append(f"    Chronological: {'Yes' if result.get('is_chronological') else 'No'}")
        
        report.append("\n📝 Next Steps:")
        report.append("  1. Implement the successful method in instagram_client.py")
        report.append("  2. Add optional parameter to get_timeline_feed()")
        report.append("  3. Update config to enable chronological feed")
    else:
        report.append("\n❌ No method successfully accessed chronological following feed")
        report.append("\n📝 Recommendation: Implement user profile fetching")
        report.append("  1. Add support for tracking specific accounts")
        report.append("  2. Use feed/user/{user_id}/ for each tracked account")
        report.append("  3. Configure priority accounts in settings")
        
        # Check if user profile worked
        user_profile = results.get("user_profile", {})
        if user_profile.get('rnz_posts', 0) >= 10:
            report.append(f"\n✅ User profile feed returned {user_profile.get('rnz_posts')} RNZ posts")
            report.append("   This confirms comprehensive coverage is possible via profile fetching")
    
    report.append("\n" + "=" * 80)
    report.append("For detailed results, see: tests/following_feed_test_results.json")
    report.append("=" * 80)
    
    return "\n".join(report)


def main():
    """Main execution function."""
    logger.info("Starting Instagram Following Feed Investigation")
    logger.info("=" * 70)
    
    # Load credentials
    username = os.getenv("INSTAGRAM_USERNAME")
    password = os.getenv("INSTAGRAM_PASSWORD")
    session_file = os.getenv("SESSION_FILE", "./data/instagram_session.json")
    
    if not username or not password:
        logger.error("INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD must be set in .env")
        return 1
    
    logger.info(f"Username: {username}")
    logger.info(f"Session file: {session_file}")
    
    # Initialize client
    try:
        client = TestInstagramClient(username, password, session_file=session_file)
        
        # Login (will use session if available)
        logger.info("\nAuthenticating...")
        if not client.login():
            logger.error("Failed to login")
            return 1
        
        logger.info("✅ Authentication successful!")
        logger.info("\nStarting tests... (this will take ~10-15 minutes)")
        logger.info("=" * 70)
        
        # Run all tests
        results = run_all_tests(client)
        
        # Save raw results
        output_dir = Path("tests")
        output_dir.mkdir(exist_ok=True)
        
        results_file = output_dir / "following_feed_test_results.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"\n✅ Raw results saved to: {results_file}")
        
        # Generate and save report
        report = generate_report(results)
        report_file = output_dir / "following_feed_test_report.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        logger.info(f"✅ Report saved to: {report_file}")
        
        # Print report
        print("\n\n")
        print(report)
        
        # Cleanup
        client.logout()
        
        return 0
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
