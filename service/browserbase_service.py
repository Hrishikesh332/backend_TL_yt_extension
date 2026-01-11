import os
import re
import time
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Page, ElementHandle
from browserbase import Browserbase


class BrowserbaseService:
    
    def __init__(self, 
                 browserbase_api_key: Optional[str] = None, 
                 browserbase_project_id: Optional[str] = None):
        self.browserbase_api_key = browserbase_api_key or os.environ.get('BROWSERBASE_API_KEY', '')
        self.browserbase_project_id = browserbase_project_id or os.environ.get('BROWSERBASE_PROJECT_ID', '')
        
        if not self.browserbase_api_key:
            raise ValueError("BROWSERBASE_API_KEY is required")
        if not self.browserbase_project_id:
            raise ValueError("BROWSERBASE_PROJECT_ID is required")
        
        self.bb = Browserbase(api_key=self.browserbase_api_key)
        
    def extract_video_id(self, url: str) -> Optional[str]:
        if not url:
            return None
        patterns = [
            r'[?&]v=([a-zA-Z0-9_-]{11})',
            r'youtu\.be/([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def extract_videos_from_page(self, page: Page, max_videos: int) -> List[Dict]:
        videos = []
        seen_ids = set()
        
        links = page.query_selector_all('a[href*="/watch?v="]')
        
        for link in links:
            if len(videos) >= max_videos + 1:
                break
            
            href = link.get_attribute('href')
            video_id = self.extract_video_id(href)
            if not video_id or video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            
            title = link.get_attribute('aria-label') or link.get_attribute('title') or ''
            if title:
                parts = re.split(r' by | · | - ', title)
                if parts:
                    title = parts[0].strip()
            
            if not title or len(title) < 3:
                link_text = link.inner_text().strip()
                if link_text and link_text not in ['Watch', 'watch', 'Now playing', 'now playing'] and not re.match(r'^\d+:\d+', link_text) and len(link_text) > 3:
                    title = link_text
            
            if title:
                title = re.sub(r'\s*[-–]\s*\d+:\d+.*$', '', title)
                title = re.sub(r'\s*\(\d+:\d+.*\)\s*$', '', title).strip()
            
            if not title or len(title) < 3:
                title = f"Video {video_id}"
            
            videos.append({
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "videoId": video_id,
                "channelName": None,
                "duration": None,
                "thumbnailUrl": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
            })
        
        return videos

    def fetch_metadata_with_ytdlp(self, video: Dict) -> Dict:
        video = self.fetch_metadata_via_oembed(video)
        
        if (not video.get('title') or video['title'].startswith('Video ')) or not video.get('duration'):
            video = self.fetch_metadata_via_ytdlp(video)
        
        return video
    
    def fetch_metadata_via_oembed(self, video: Dict) -> Dict:
        try:
            import urllib.request
            import json
            
            video_url = video.get('url', '')
            oembed_url = f"https://www.youtube.com/oembed?url={video_url}&format=json"
            
            req = urllib.request.Request(
                oembed_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                if not video.get('title') or video['title'].startswith('Video '):
                    video['title'] = data.get('title', video.get('title'))
                
                if not video.get('channelName'):
                    video['channelName'] = data.get('author_name')
                
                print(f"[METADATA] oEmbed success: {video.get('title', 'Unknown')[:50]}")
        except Exception as e:
            print(f"[METADATA] oEmbed fetch failed: {e}")
        
        return video
    
    def fetch_metadata_via_ytdlp(self, video: Dict) -> Dict:
        try:
            import yt_dlp
            
            proxy_url = os.environ.get('PROXY_URL')
            cookies_file = None
            cookies_paths = [
                os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cookies.txt'),
                '/etc/secrets/cookies.txt',
                os.path.join(os.getcwd(), 'cookies.txt'),
            ]
            for path in cookies_paths:
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    cookies_file = path
                    break
            cookies_available = cookies_file is not None
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'ignoreerrors': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                },
                'geo_bypass': True,
                'nocheckcertificate': True,
            }
            
            if proxy_url:
                ydl_opts['proxy'] = proxy_url
            
            if cookies_available:
                ydl_opts['cookiefile'] = cookies_file

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video['url'], download=False)
                if info:
                    if not video.get('title') or video['title'].startswith('Video '):
                        video['title'] = info.get('title', video['title'])

                    if not video.get('duration'):
                        duration_seconds = info.get('duration', 0)
                        if duration_seconds:
                            hours = duration_seconds // 3600
                            minutes = (duration_seconds % 3600) // 60
                            seconds = duration_seconds % 60
                            if hours > 0:
                                video['duration'] = f"{hours}:{minutes:02d}:{seconds:02d}"
                            else:
                                video['duration'] = f"{minutes}:{seconds:02d}"

                    if not video.get('channelName'):
                        video['channelName'] = info.get('channel') or info.get('uploader')

                    if not video.get('thumbnailUrl'):
                        video['thumbnailUrl'] = info.get('thumbnail') or (info.get('thumbnails', [{}])[0].get('url') if info.get('thumbnails') else None)
                    
                    print(f"[METADATA] yt-dlp success: {video.get('title', 'Unknown')[:50]}")
        except Exception as e:
            print(f"[METADATA] yt-dlp fetch failed: {e}")

        return video
    
    def parse_query_filters(self, search_query: str) -> Dict:
        """Parse search query to extract YouTube filter parameters."""
        filters = {
            "duration": None,
            "upload_date": None,
            "query_text": search_query
        }
        
        query_lower = search_query.lower()
        
        if any(term in query_lower for term in ["short", "under 4", "less than 4", "< 4"]):
            filters["duration"] = "short"
        elif any(term in query_lower for term in ["medium", "4-20", "4 to 20", "between 4 and 20"]):
            filters["duration"] = "medium"
        elif any(term in query_lower for term in ["long", "over 20", "more than 20", "> 20"]):
            filters["duration"] = "long"
        
        duration_patterns = [
            r'(\d+)\s*(?:min|mins|minute|minutes|m)\s*(?:video|vid|clip)?',
            r'(\d+)\s*(?:second|seconds|sec|secs|s)\s*(?:video|vid|clip)?',
            r'video\s*(?:of|about|on)?\s*(\d+)\s*(?:min|mins|minute|minutes|m)',
            r'in\s*(\d+)\s*(?:min|mins|minute|minutes|m)',
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, query_lower)
            if match:
                minutes = int(match.group(1))
                if minutes <= 4:
                    filters["duration"] = "short"
                elif minutes <= 20:
                    filters["duration"] = "medium"
                else:
                    filters["duration"] = "long"
                filters["query_text"] = re.sub(pattern, '', filters["query_text"], flags=re.IGNORECASE).strip()
                break
        
        if any(term in query_lower for term in ["today", "recent", "latest", "new"]):
            filters["upload_date"] = "today"
        elif any(term in query_lower for term in ["this week", "past week", "last week"]):
            filters["upload_date"] = "week"
        elif any(term in query_lower for term in ["this month", "past month", "last month"]):
            filters["upload_date"] = "month"
        elif any(term in query_lower for term in ["this year", "past year", "last year"]):
            filters["upload_date"] = "year"
        
        query_clean = filters["query_text"]
        filter_words = ["short", "medium", "long", "today", "recent", "latest", "new", 
                       "this week", "past week", "last week", "this month", "past month", 
                       "last month", "this year", "past year", "last year", "video", "videos"]
        for word in filter_words:
            query_clean = re.sub(rf'\b{word}\b', '', query_clean, flags=re.IGNORECASE)
        filters["query_text"] = ' '.join(query_clean.split()).strip()
        
        return filters
    
    def build_youtube_search_url(self, query_text: str, filters: Dict) -> str:
        """Build YouTube search URL with filters."""
        import urllib.parse
        
        base_url = "https://www.youtube.com/results"
        params = {
            "search_query": query_text
        }
        
        if filters.get("duration"):
            duration_map = {
                "short": "EgIYAQ%253D%253D",
                "medium": "EgIYAw%253D%253D",
                "long": "EgIYAg%253D%253D"
            }
            if filters["duration"] in duration_map:
                params["sp"] = duration_map[filters["duration"]]
        
        if filters.get("upload_date"):
            date_map = {
                "hour": "EgQIARAB",
                "today": "EgQIAhAB",
                "week": "EgQIAxAB",
                "month": "EgQIBBAB",
                "year": "EgQIBRAB"
            }
            if filters["upload_date"] in date_map:
                if "sp" in params:
                    params["sp"] = params["sp"] + "%252C" + date_map[filters["upload_date"]]
                else:
                    params["sp"] = date_map[filters["upload_date"]]
        
        query_string = urllib.parse.urlencode(params)
        return f"{base_url}?{query_string}"
    
    def discover_youtube_videos(self, search_query: str, max_videos: int = 3, status_callback=None) -> List[Dict]:
        def send_status(status, message):
            if status_callback:
                status_callback(status, message)
            print(f"[{status}] {message}")
        
        session = None
        
        try:
            send_status("starting", "Starting browser automation to find YouTube videos...")
            
            send_status("info", "Analyzing query to extract filters...")
            filters = self.parse_query_filters(search_query)
            clean_query = filters["query_text"] or search_query
            
            send_status("info", f"Search query: '{clean_query}'")
            
            filters_applied = []
            if filters.get("duration"):
                filters_applied.append(f"Duration: {filters['duration']}")
                send_status("info", f"Duration filter detected: {filters['duration']}")
            if filters.get("upload_date"):
                filters_applied.append(f"Upload date: {filters['upload_date']}")
                send_status("info", f"Upload date filter detected: {filters['upload_date']}")
            
            if filters_applied:
                send_status("info", f"Applying YouTube filters: {', '.join(filters_applied)}")
            else:
                send_status("info", "No filters detected, using default search")
            
            send_status("info", f"Max videos to find: {max_videos}")
            
            with sync_playwright() as playwright:
                send_status("info", "Creating Browserbase session...")
                session = self.bb.sessions.create(project_id=self.browserbase_project_id)
                
                print(f"Session created: {session.id}")
                print(f"Watch live: https://browserbase.com/sessions/{session.id}")
                
                browser = playwright.chromium.connect_over_cdp(session.connect_url)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                
                try:
                    send_status("info", "Navigating to YouTube...")
                    
                    search_url = self.build_youtube_search_url(clean_query, filters)
                    if filters.get("duration") or filters.get("upload_date"):
                        send_status("info", f"Navigating to filtered search results...")
                    else:
                        send_status("info", f"Navigating to search results...")
                    
                    page.goto(search_url, wait_until="domcontentloaded")
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(3)
                    
                    if filters.get("duration") or filters.get("upload_date"):
                        try:
                            filter_button = page.query_selector('button[aria-label*="Filter"], button[aria-label*="filter"], ytd-search-filter-renderer')
                            if filter_button:
                                send_status("info", "Applying additional filters via YouTube UI...")
                                filter_button.click()
                                time.sleep(1)
                                
                                if filters.get("duration"):
                                    duration_labels = {
                                        "short": "Under 4 minutes",
                                        "medium": "4 - 20 minutes",
                                        "long": "Over 20 minutes"
                                    }
                                    duration_label = duration_labels.get(filters["duration"])
                                    if duration_label:
                                        send_status("info", f"Selecting duration filter: {duration_label}")
                                        duration_option = page.query_selector(f'text="{duration_label}"')
                                        if duration_option:
                                            duration_option.click()
                                            time.sleep(0.5)
                                            send_status("info", f"✓ Duration filter applied: {duration_label}")
                                
                                if filters.get("upload_date"):
                                    date_labels = {
                                        "today": "Today",
                                        "week": "This week",
                                        "month": "This month",
                                        "year": "This year"
                                    }
                                    date_label = date_labels.get(filters["upload_date"])
                                    if date_label:
                                        send_status("info", f"Selecting upload date filter: {date_label}")
                                        date_option = page.query_selector(f'text="{date_label}"')
                                        if date_option:
                                            date_option.click()
                                            time.sleep(0.5)
                                            send_status("info", f"✓ Upload date filter applied: {date_label}")
                                
                                send_status("info", "Filters applied successfully")
                        except Exception as e:
                            send_status("info", f"Note: Could not apply filters via UI, using URL-based filters: {e}")
                    else:
                        send_status("info", "No filters to apply, using standard search")
                    
                    send_status("info", "Waiting for search results...")
                    page.wait_for_load_state("networkidle", timeout=15000)
                    page.wait_for_selector('ytd-video-renderer, ytd-rich-item-renderer, a[href*="/watch"]', timeout=10000)
                    time.sleep(3)
                    
                    try:
                        page.evaluate("window.scrollTo(0, 500)")
                        time.sleep(1)
                    except:
                        pass
                    
                    send_status("info", "Extracting video information...")

                    raw_videos = self.extract_videos_from_page(page, max_videos)
                    send_status("info", f"Found {len(raw_videos)} raw videos")

                    filtered_videos = []
                    for i, video in enumerate(raw_videos):
                        if len(filtered_videos) >= max_videos:
                            break
                        
                        if i == 0:
                            print(f"Skipping first video (often ad): {video.get('title')}")
                            continue
                        
                        title = video.get('title', '').strip()
                        if title.lower() in ['watch', 'ad', 'ads'] or (len(title) < 5 and title.lower() in ['ad', 'ads']):
                            print(f"Skipping likely ad: {title}")
                            continue
                        
                        needs_metadata = (
                            not video.get('title') or
                            video['title'].startswith('Video ') or
                            not video.get('duration') or
                            not video.get('channelName')
                        )

                        if needs_metadata:
                            send_status("info", f"Fetching metadata for video {len(filtered_videos) + 1}...")
                            video = self.fetch_metadata_with_ytdlp(video)

                        if not video.get('thumbnailUrl'):
                            video['thumbnailUrl'] = f"https://img.youtube.com/vi/{video.get('videoId', '')}/maxresdefault.jpg"

                        video.pop('videoId', None)
                        filtered_videos.append(video)
                    
                    send_status("success", f"Found {len(filtered_videos)} videos")

                    for idx, video in enumerate(filtered_videos, 1):
                        print(f"\n   {idx}. {video.get('title', 'Unknown')}")
                        print(f"      URL: {video.get('url')}")
                        print(f"      Duration: {video.get('duration', 'N/A')}")
                        if video.get('channelName'):
                            print(f"      Channel: {video.get('channelName')}")
                    
                    return filtered_videos
                    
                finally:
                    page.close()
                    browser.close()
                    
        except Exception as e:
            send_status("error", f"Error in browser automation: {str(e)}")
            print(f"Error in browser automation: {str(e)}")
            raise
        finally:
            if session:
                    print(f"Session completed: {session.id}")
