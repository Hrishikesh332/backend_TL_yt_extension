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
        
    def _extract_video_id(self, url: str) -> Optional[str]:
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

    def _extract_title(self, video_el: ElementHandle, link_el: ElementHandle = None, aria_label: str = None) -> str:
        title = None
        
        if aria_label:
            parts = re.split(r' by | · | - ', aria_label)
            if parts:
                title = parts[0].strip()
                title = re.sub(r'\s+\d{1,2}:\d{2}.*$', '', title).strip()
        
            if not title or len(title) < 3:
                title_el = video_el.query_selector('#video-title, h3#video-title')
                if title_el:
                    title_aria = title_el.get_attribute('aria-label')
                    if title_aria:
                        parts = re.split(r' by | · | - ', title_aria)
                        if parts:
                            title = parts[0].strip()
                            title = re.sub(r'\s+\d{1,2}:\d{2}.*$', '', title)
                    if not title or len(title) < 3:
                        title = title_el.inner_text().strip()
        
        if (not title or len(title) < 3) and link_el:
            link_text = link_el.inner_text().strip()
            if link_text and link_text not in ['Watch', 'watch'] and len(link_text) >= 5:
                title = link_text
        
        if title:
            title = re.sub(r'\s*[·•]\s*\d{1,2}:\d{2}.*$', '', title)
            title = re.sub(r'\s+by\s+.*$', '', title, flags=re.IGNORECASE).strip()
        
        return title

    def _extract_duration(self, video_el: ElementHandle, aria_label: str = None) -> Optional[str]:
        duration = None
        
        if aria_label and '·' in aria_label:
            parts = aria_label.split('·')
            if len(parts) > 1:
                dur_text = parts[-1].strip()
                dur_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', dur_text)
                if dur_match:
                    duration = dur_match.group(1)
        
        if not duration:
            overlay_el = video_el.query_selector('ytd-thumbnail-overlay-time-status-renderer')
            if overlay_el:
                time_span = overlay_el.query_selector('span')
                if time_span:
                    dur_text = time_span.inner_text().strip()
                    if not dur_text:
                        dur_text = time_span.get_attribute('aria-label') or ''
                    if dur_text:
                        dur_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', dur_text)
                        if dur_match:
                            duration = dur_match.group(1)
                
                if not duration:
                    dur_text = overlay_el.inner_text().strip()
                    if dur_text:
                        dur_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', dur_text)
                        if dur_match:
                            duration = dur_match.group(1)
        
        if not duration:
            thumbnail_container = video_el.query_selector('ytd-thumbnail, #thumbnail, a[href*="/watch"]')
            if thumbnail_container:
                try:
                    all_text = thumbnail_container.inner_text()
                    dur_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', all_text)
                    if dur_match:
                        duration = dur_match.group(1)
                except:
                    pass
        
        if not duration:
            duration_selectors = [
                'ytd-thumbnail-overlay-time-status-renderer span',
                'ytd-thumbnail-overlay-time-status-renderer #text',
                '[class*="time-status"] span',
                '[class*="duration"]',
                'span[class*="time"]'
            ]
            for selector in duration_selectors:
                dur_el = video_el.query_selector(selector)
                if dur_el:
                    dur_text = dur_el.inner_text().strip()
                    if dur_text:
                        dur_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', dur_text)
                        if dur_match:
                            duration = dur_match.group(1)
                            break
        
        return duration

    def _extract_thumbnail_url(self, video_el: ElementHandle, video_id: str) -> str:
        thumbnail_url = None
        
        try:
            thumbnail_img = video_el.query_selector('img[src*="ytimg.com"], img[src*="youtube.com"]')
            if thumbnail_img:
                thumbnail_url = thumbnail_img.get_attribute('src') or thumbnail_img.get_attribute('data-src')
                if thumbnail_url:
                    thumbnail_url = re.sub(r'/[^/]+\.jpg', '/maxresdefault.jpg', thumbnail_url)
                    if 'maxresdefault' not in thumbnail_url:
                        thumbnail_url = re.sub(r'/[^/]+\.jpg', '/hqdefault.jpg', thumbnail_url)
        except:
            pass
        
        if not thumbnail_url:
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        
        return thumbnail_url

    def _find_title_link(self, video_el: ElementHandle) -> Optional[ElementHandle]:
        all_links = video_el.query_selector_all('a[href*="/watch?v="]')
        
        for link in all_links:
            href = link.get_attribute('href')
            if not href:
                continue
            
            aria_label = link.get_attribute('aria-label') or ''
            link_text = link.inner_text().strip()
            
            if link_text in ['Watch', 'watch'] or len(link_text) < 5:
                continue
            
            if aria_label and len(aria_label) > 15 and (' by ' in aria_label or ' · ' in aria_label):
                video_id = self._extract_video_id(href)
                if video_id:
                    return link
        
        direct_title_link = video_el.query_selector('a#video-title-link')
        if direct_title_link:
            href = direct_title_link.get_attribute('href')
            if href and self._extract_video_id(href):
                return direct_title_link
        
        for link in all_links:
            link_text = link.inner_text().strip()
            if link_text not in ['Watch', 'watch'] and len(link_text) > 5:
                href = link.get_attribute('href')
                if href and self._extract_video_id(href):
                    return link
        
        return None

    def _extract_video_data_from_element(self, video_el: ElementHandle) -> Optional[Dict]:
        try:
            title_link = self._find_title_link(video_el)
            if not title_link:
                return None
            
            href = title_link.get_attribute('href')
            video_id = self._extract_video_id(href)
            if not video_id:
                return None
            
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            aria_label = title_link.get_attribute('aria-label') or ''
            
            title = self._extract_title(video_el, title_link, aria_label)
            if not title or len(title) < 3:
                title = f"Video {video_id}"
            
            channel_name = None
            channel_el = video_el.query_selector('ytd-channel-name a, ytd-channel-name #text-container, ytd-channel-name #container #text')
            if channel_el:
                channel_name = channel_el.inner_text().strip()
                if len(channel_name) < 2:
                    channel_name = None
            
            duration = self._extract_duration(video_el, aria_label)
            thumbnail_url = self._extract_thumbnail_url(video_el, video_id)
            
            return {
                "title": title,
                "url": url,
                "videoId": video_id,
                "channelName": channel_name,
                "duration": duration,
                "thumbnailUrl": thumbnail_url
            }
        except Exception as e:
            print(f"Error extracting video data: {e}")
            return None

    def _extract_videos_from_page(self, page: Page, max_videos: int) -> List[Dict]:
        videos = []
        seen_ids = set()
        
        video_elements = page.query_selector_all('ytd-video-renderer')
        
        for video_el in video_elements:
            if len(videos) >= max_videos + 1:
                break
            
            ad_indicator = video_el.query_selector('[class*="ad"], [class*="promo"], [class*="sponsored"]')
            if ad_indicator:
                continue
            
            video_data = self._extract_video_data_from_element(video_el)
            if not video_data:
                continue
            
            video_id = video_data.get("videoId")
            if video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            
            videos.append(video_data)
        
        if not videos:
            video_elements = page.query_selector_all('ytd-rich-item-renderer')
            for video_el in video_elements:
                if len(videos) >= max_videos + 1:
                    break
                
                ad_indicator = video_el.query_selector('[class*="ad"], [class*="promo"], [class*="sponsored"]')
                if ad_indicator:
                    continue
                
                video_data = self._extract_video_data_from_element(video_el)
                if not video_data:
                    continue
                
                video_id = video_data.get("videoId")
                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)
                
                videos.append(video_data)
        
        if not videos:
            links = page.query_selector_all('a[href*="/watch?v="]')
            for link in links:
                if len(videos) >= max_videos + 1:
                    break
                
                href = link.get_attribute('href')
                video_id = self._extract_video_id(href)
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

    def _fetch_metadata_with_ytdlp(self, video: Dict) -> Dict:
        video = self._fetch_metadata_via_oembed(video)
        
        if (not video.get('title') or video['title'].startswith('Video ')) or not video.get('duration'):
            video = self._fetch_metadata_via_ytdlp(video)
        
        return video
    
    def _fetch_metadata_via_oembed(self, video: Dict) -> Dict:
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
    
    def _fetch_metadata_via_ytdlp(self, video: Dict) -> Dict:
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
    
    def discover_youtube_videos(self, search_query: str, max_videos: int = 3, status_callback=None) -> List[Dict]:
        def send_status(status, message):
            if status_callback:
                status_callback(status, message)
            print(f"[{status}] {message}")
        
        session = None
        
        try:
            send_status("starting", "Starting browser automation to find YouTube videos...")
            send_status("info", f"Search query: '{search_query}'")
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
                    page.goto("https://www.youtube.com", wait_until="domcontentloaded")
                    page.wait_for_load_state("networkidle", timeout=10000)
                    time.sleep(2)
                    
                    send_status("info", f"Searching for: '{search_query}'")
                    
                    search_selectors = [
                        'input#search',
                        'input[name="search_query"]',
                        'input[placeholder*="Search"]',
                        'input[aria-label*="Search"]',
                        '#search-input',
                        'input[type="text"]'
                    ]
                    
                    search_input = None
                    for selector in search_selectors:
                        try:
                            search_input = page.query_selector(selector)
                            if search_input:
                                break
                        except:
                            continue
                    
                    if search_input:
                        search_input.click()
                        time.sleep(0.3)
                        search_input.fill(search_query)
                        time.sleep(0.3)
                        search_input.press("Enter")
                    else:
                        encoded_query = search_query.replace(' ', '+')
                        page.goto(f"https://www.youtube.com/results?search_query={encoded_query}", wait_until="domcontentloaded")
                    
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

                    raw_videos = self._extract_videos_from_page(page, max_videos)
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
                            video = self._fetch_metadata_with_ytdlp(video)

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
