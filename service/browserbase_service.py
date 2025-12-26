import os
import json
import time
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Playwright
from browserbase import Browserbase
from openai import OpenAI


class BrowserbaseService:
    
    def __init__(self, 
                 browserbase_api_key: Optional[str] = None, 
                 browserbase_project_id: Optional[str] = None,
                 openai_api_key: Optional[str] = None):
        self.browserbase_api_key = browserbase_api_key or os.environ.get('BROWSERBASE_API_KEY', '')
        self.browserbase_project_id = browserbase_project_id or os.environ.get('BROWSERBASE_PROJECT_ID', '')
        self.openai_api_key = openai_api_key or os.environ.get('OPENAI_API_KEY', '')
        
        if not self.browserbase_api_key:
            raise ValueError("BROWSERBASE_API_KEY is required")
        if not self.browserbase_project_id:
            raise ValueError("BROWSERBASE_PROJECT_ID is required")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for agentic automation")
        
        self.bb = Browserbase(api_key=self.browserbase_api_key)
        
        self.openai_client = OpenAI(api_key=self.openai_api_key)
    
    def _get_page_elements(self, page) -> str:
        try:
            elements = page.evaluate("""
                () => {
                    const elements = [];
                    const selectors = [
                        'input#search',
                        'input[name="search_query"]',
                        'button#search-icon-legacy',
                        'button[aria-label*="Search"]',
                        'ytd-video-renderer',
                        'ytd-rich-item-renderer'
                    ];
                    
                    selectors.forEach(selector => {
                        const el = document.querySelector(selector);
                        if (el) {
                            elements.push({
                                selector: selector,
                                visible: el.offsetParent !== null,
                                text: el.textContent?.trim().substring(0, 50) || ''
                            });
                        }
                    });
                    
                    return elements;
                }
            """)
            return json.dumps(elements, indent=2)
        except:
            return "[]"
    
    def _ai_act(self, page, instruction: str) -> str:
        page_elements = self._get_page_elements(page)
        page_content = page.content()[:5000]
        
        prompt = f"""You are controlling a browser on YouTube. Your task is to: {instruction}

Current page elements:
{page_elements}

Page content (first 5000 chars):
{page_content}

Based on the instruction, determine the exact action to take. Respond with a JSON object with this structure:
{{
    "action": "click" | "type" | "press" | "wait" | "extract",
    "selector": "CSS selector for the element",
    "text": "text to type (if action is 'type')",
    "key": "key to press (if action is 'press')",
    "wait_time": seconds to wait (if action is 'wait')
}}

Only respond with valid JSON, no other text."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a browser automation assistant. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content)
            action = result.get("action")
            
            if action == "click":
                selector = result.get("selector")
                if selector:
                    page.click(selector, timeout=5000)
                    return f"Clicked {selector}"
            elif action == "type":
                selector = result.get("selector")
                text = result.get("text", "")
                if selector:
                    page.fill(selector, text)
                    return f"Typed '{text}' into {selector}"
            elif action == "press":
                selector = result.get("selector")
                key = result.get("key", "Enter")
                if selector:
                    page.press(selector, key)
                    return f"Pressed {key} on {selector}"
            elif action == "wait":
                wait_time = result.get("wait_time", 2)
                time.sleep(wait_time)
                return f"Waited {wait_time} seconds"
            
            return "Action completed"
        except Exception as e:
            print(f"AI action error: {e}")
            return f"Error: {str(e)}"
    
    def _ai_extract(self, page, instruction: str, schema: Dict) -> Dict:
        try:
            page_content = page.content()[:10000]
            
            visible_text = page.evaluate("""
                () => {
                    return document.body.innerText.substring(0, 5000);
                }
            """)
            
            prompt = f"""Extract data from this YouTube search results page based on the instruction: {instruction}

Page visible text:
{visible_text}

Extract the data according to this JSON schema:
{json.dumps(schema, indent=2)}

Return only valid JSON matching the schema. Skip ads and promoted content."""

            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a data extraction assistant. Extract structured data from web pages. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"AI extraction error: {e}")
            return {"videos": []}
    
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
                
                chromium = playwright.chromium
                browser = chromium.connect_over_cdp(session.connect_url)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                
                try:
                    send_status("info", "Navigating to YouTube...")
                    page.goto("https://www.youtube.com", wait_until="domcontentloaded")
                    page.wait_for_load_state("networkidle", timeout=10000)
                    time.sleep(2)
                    
                    send_status("info", "Navigated to YouTube")
                    
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
                        search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
                        page.goto(search_url, wait_until="domcontentloaded")
                    
                    send_status("info", "Waiting for search results...")
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(3)
                    
                    try:
                        page.wait_for_selector('ytd-video-renderer, ytd-rich-item-renderer, a[href*="/watch"]', timeout=10000)
                    except:
                        print("Warning: Video elements not found with wait_for_selector")
                    
                    try:
                        page.evaluate("window.scrollTo(0, 500)")
                        time.sleep(1)
                    except:
                        pass
                    
                    send_status("info", "Extracting video information from search results...")
                    
                    page_info = page.evaluate("""
                        () => {
                            return {
                                videoRenderers: document.querySelectorAll('ytd-video-renderer').length,
                                richItems: document.querySelectorAll('ytd-rich-item-renderer').length,
                                watchLinks: document.querySelectorAll('a[href*="/watch"]').length,
                                url: window.location.href,
                                title: document.title
                            };
                        }
                    """)
                    print(f"Page debug info: {page_info}")
                    
                    if page_info.get('watchLinks', 0) == 0 and page_info.get('videoRenderers', 0) == 0:
                        print("WARNING: No video elements found on page. The search may have failed.")
                        print("Current URL:", page_info.get('url'))
                        print("Page title:", page_info.get('title'))
                    
                    video_elements = page.evaluate(r"""
                        () => {
                            const videos = [];
                            const seenUrls = new Set();
                            
                            const videoElements = document.querySelectorAll('ytd-video-renderer');
                            console.log('Total video renderers found:', videoElements.length);
                            
                            for (let i = 0; i < videoElements.length && videos.length < 20; i++) {
                                const video = videoElements[i];
                                try {
                                    if (video.querySelector('[class*="ad"], [class*="promo"], [class*="sponsored"]')) {
                                        continue;
                                    }
                                    
                                    const allWatchLinks = video.querySelectorAll('a[href*="/watch?v="]');
                                    let titleLink = null;
                                    let videoUrl = null;
                                    let videoId = null;
                                    let titleAriaLabel = null;
                                    
                                    for (const link of allWatchLinks) {
                                        const href = link.getAttribute('href');
                                        if (!href) continue;
                                        
                                        const ariaLabel = link.getAttribute('aria-label') || '';
                                        const linkText = (link.innerText || link.textContent || '').trim();
                                        
                                        if (linkText === 'Watch' || linkText === 'watch' || linkText.length < 5) {
                                            continue;
                                        }
                                        
                                        if (ariaLabel && ariaLabel.length > 15 && (ariaLabel.includes(' by ') || ariaLabel.includes(' · '))) {
                                            const match = href.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
                                            if (match) {
                                                titleLink = link;
                                                videoId = match[1];
                                                videoUrl = 'https://www.youtube.com/watch?v=' + videoId;
                                                titleAriaLabel = ariaLabel;
                                                break;
                                            }
                                        }
                                    }
                                    
                                    if (!titleLink) {
                                        const directTitleLink = video.querySelector('a#video-title-link');
                                        if (directTitleLink) {
                                            const href = directTitleLink.getAttribute('href');
                                            if (href) {
                                                const match = href.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
                                                if (match) {
                                                    titleLink = directTitleLink;
                                                    videoId = match[1];
                                                    videoUrl = 'https://www.youtube.com/watch?v=' + videoId;
                                                    titleAriaLabel = directTitleLink.getAttribute('aria-label') || '';
                                                }
                                            }
                                        }
                                    }
                                    
                                    if (!titleLink && allWatchLinks.length > 0) {
                                        for (const link of allWatchLinks) {
                                            const linkText = (link.innerText || link.textContent || '').trim();
                                            if (linkText !== 'Watch' && linkText !== 'watch' && linkText.length > 5) {
                                                const href = link.getAttribute('href');
                                                if (href) {
                                                    const match = href.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
                                                    if (match) {
                                                        titleLink = link;
                                                        videoId = match[1];
                                                        videoUrl = 'https://www.youtube.com/watch?v=' + videoId;
                                                        titleAriaLabel = titleLink.getAttribute('aria-label') || '';
                                                        break;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    
                                    if (!videoUrl || !videoId) continue;
                                    
                                    if (seenUrls.has(videoUrl)) continue;
                                    seenUrls.add(videoUrl);
                                    
                                    let thumbnailUrl = null;
                                    try {
                                        const thumbnailImg = video.querySelector('img[src*="ytimg.com"], img[src*="youtube.com"]');
                                        if (thumbnailImg) {
                                            thumbnailUrl = thumbnailImg.getAttribute('src') || thumbnailImg.getAttribute('data-src');
                                            if (thumbnailUrl) {
                                                thumbnailUrl = thumbnailUrl.replace(/\/[^\/]+\.jpg/, '/maxresdefault.jpg');
                                                if (!thumbnailUrl.includes('maxresdefault')) {
                                                    thumbnailUrl = thumbnailUrl.replace(/\/[^\/]+\.jpg/, '/hqdefault.jpg');
                                                }
                                            }
                                        }
                                        if (!thumbnailUrl && videoId) {
                                            thumbnailUrl = `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`;
                                        }
                                    } catch (e) {
                                        if (videoId) {
                                            thumbnailUrl = `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`;
                                        }
                                    }
                                    
                                    let title = '';
                                    
                                    if (titleAriaLabel) {
                                        const parts = titleAriaLabel.split(/ by | · | - /);
                                        title = parts[0].trim();
                                        title = title.replace(/\s+\d{1,2}:\d{2}.*$/, '').trim();
                                    }
                                    
                                    if (!title || title.length < 3) {
                                        const titleEl = video.querySelector('#video-title, h3#video-title');
                                        if (titleEl) {
                                            const ariaLabel = titleEl.getAttribute('aria-label');
                                            if (ariaLabel) {
                                                const parts = ariaLabel.split(/ by | · | - /);
                                                title = parts[0].trim().replace(/\s+\d{1,2}:\d{2}.*$/, '');
                                            }
                                            if (!title || title.length < 3) {
                                                title = (titleEl.innerText || titleEl.textContent || '').trim();
                                            }
                                        }
                                    }
                                    
                                    if ((!title || title.length < 3) && titleLink) {
                                        title = (titleLink.innerText || titleLink.textContent || '').trim();
                                        if (title === 'Watch' || title.length < 5) {
                                            title = '';
                                        }
                                    }
                                    
                                    if (title) {
                                        title = title.replace(/\s*[·•]\s*\d{1,2}:\d{2}.*$/, '')
                                                    .replace(/\s+by\s+.*$/i, '')
                                                    .trim();
                                    }
                                    
                                    if (!title || title.length < 3) {
                                        title = 'Video ' + videoId;
                                    }
                                    
                                    let channelName = null;
                                    const channelEl = video.querySelector('ytd-channel-name a, ytd-channel-name #text-container, ytd-channel-name #container #text');
                                    if (channelEl) {
                                        channelName = channelEl.textContent?.trim() || channelEl.innerText?.trim();
                                        if (!channelName || channelName.length < 2) {
                                            channelName = null;
                                        }
                                    }
                                    
                                    let duration = null;
                                    
                                    if (titleAriaLabel && titleAriaLabel.includes('·')) {
                                        const parts = titleAriaLabel.split('·');
                                        if (parts.length > 1) {
                                            const durText = parts[parts.length - 1].trim();
                                            const durMatch = durText.match(/(\d{1,2}:\d{2}(?::\d{2})?)/);
                                            if (durMatch) {
                                                duration = durMatch[1];
                                            }
                                        }
                                    }
                                    
                                    if (!duration) {
                                        const overlayTimeRenderer = video.querySelector('ytd-thumbnail-overlay-time-status-renderer');
                                        if (overlayTimeRenderer) {
                                            const timeSpan = overlayTimeRenderer.querySelector('span');
                                            if (timeSpan) {
                                                let durText = (timeSpan.innerText || timeSpan.textContent || '').trim();
                                                if (!durText) {
                                                    durText = timeSpan.getAttribute('aria-label') || '';
                                                }
                                                if (durText) {
                                                    const durMatch = durText.match(/(\d{1,2}:\d{2}(?::\d{2})?)/);
                                                    if (durMatch) {
                                                        duration = durMatch[1];
                                                    }
                                                }
                                            }
                                            
                                            if (!duration) {
                                                let durText = (overlayTimeRenderer.innerText || overlayTimeRenderer.textContent || '').trim();
                                                if (durText) {
                                                    const durMatch = durText.match(/(\d{1,2}:\d{2}(?::\d{2})?)/);
                                                    if (durMatch) {
                                                        duration = durMatch[1];
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    
                                    if (!duration) {
                                        const thumbnailContainer = video.querySelector('ytd-thumbnail, #thumbnail, a[href*="/watch"]');
                                        if (thumbnailContainer) {
                                            const walker = document.createTreeWalker(
                                                thumbnailContainer,
                                                NodeFilter.SHOW_TEXT,
                                                null,
                                                false
                                            );
                                            
                                            let node;
                                            while (node = walker.nextNode()) {
                                                const text = node.textContent.trim();
                                                if (text && /^\d{1,2}:\d{2}(?::\d{2})?$/.test(text)) {
                                                    duration = text;
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                    
                                    if (!duration) {
                                        const durationSelectors = [
                                            'ytd-thumbnail-overlay-time-status-renderer span',
                                            'ytd-thumbnail-overlay-time-status-renderer #text',
                                            '[class*="time-status"] span',
                                            '[class*="duration"]',
                                            'span[class*="time"]'
                                        ];
                                        
                                        for (const selector of durationSelectors) {
                                            const durationEl = video.querySelector(selector);
                                            if (durationEl) {
                                                let durText = (durationEl.innerText || durationEl.textContent || '').trim();
                                                if (durText) {
                                                    const durMatch = durText.match(/(\d{1,2}:\d{2}(?::\d{2})?)/);
                                                    if (durMatch) {
                                                        duration = durMatch[1];
                                                        break;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    
                                    videos.push({ title, url, channelName, duration, thumbnailUrl });
                                } catch (e) {
                                    console.error('Error extracting video:', e);
                                }
                            }
                            
                            if (videos.length === 0) {
                                const allLinks = document.querySelectorAll('a[href*="/watch?v="]');
                                for (const link of allLinks) {
                                    if (videos.length >= 10) break;
                                    
                                    const href = link.getAttribute('href');
                                    if (!href) continue;
                                    
                                    let url = href.startsWith('http') ? href : 'https://www.youtube.com' + href;
                                    const match = url.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
                                    if (!match) continue;
                                    url = 'https://www.youtube.com/watch?v=' + match[1];
                                    
                                    if (seenUrls.has(url)) continue;
                                    seenUrls.add(url);
                                    
                                    let title = link.getAttribute('aria-label') || link.getAttribute('title') || '';
                                    if (!title) {
                                        const linkText = link.textContent?.trim() || link.innerText?.trim() || '';
                                        if (linkText && !['Watch', 'watch', 'Now playing', 'now playing'].includes(linkText) && !/^\d+:\d+/.test(linkText)) {
                                            title = linkText;
                                        }
                                    }
                                    if (title) {
                                        title = title.replace(/\s*[-–]\s*\d+:\d+.*$/, '').replace(/\s*\(\d+:\d+.*\)\s*$/, '').trim();
                                    }
                                    if (!title) {
                                        title = 'Video ' + match[1];
                                    }
                                    
                                    let thumbnailUrl = null;
                                    if (match && match[1]) {
                                        thumbnailUrl = `https://img.youtube.com/vi/${match[1]}/maxresdefault.jpg`;
                                    }
                                    videos.push({ title, url, channelName: null, duration: null, thumbnailUrl });
                                }
                            }
                            
                            return videos;
                        }
                    """)
                    
                    videos = video_elements if isinstance(video_elements, list) else []
                    send_status("info", f"Raw videos extracted: {len(videos)}")
                    
                    if len(videos) == 0:
                        print("ERROR: No videos extracted despite finding video renderers!")
                        print("This might be a selector issue. Trying fallback extraction...")
                        
                        fallback_videos = page.evaluate(r"""
                            () => {
                                const videos = [];
                                const seen = new Set();
                                const links = document.querySelectorAll('a[href*="/watch?v="]');
                                
                                for (const link of links) {
                                    const href = link.getAttribute('href');
                                    if (!href) continue;
                                    
                                    let url = href.startsWith('http') ? href : 'https://www.youtube.com' + href;
                                    const match = url.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
                                    if (!match) continue;
                                    
                                    url = 'https://www.youtube.com/watch?v=' + match[1];
                                    
                                    if (seen.has(url)) continue;
                                    seen.add(url);
                                    
                                    let title = '';
                                    title = link.getAttribute('aria-label') || link.getAttribute('title') || '';
                                    if (title) {
                                        const parts = title.split(/ by | · | - /);
                                        if (parts.length > 0) {
                                            title = parts[0].trim();
                                        }
                                    }
                                    
                                    if (!title || title.length < 3) {
                                        const linkText = link.textContent?.trim() || link.innerText?.trim() || '';
                                        if (linkText && linkText.length > 3 && 
                                            !['Watch', 'watch', 'Now playing', 'now playing'].includes(linkText) && 
                                            !/^\d+:\d+/.test(linkText)) {
                                            title = linkText;
                                        }
                                    }
                                    
                                    if (title) {
                                        title = title.replace(/\s*[·•]\s*\d+:\d+.*$/, '').replace(/\s+by\s+.*$/i, '').trim();
                                    }
                                    if (!title || title.length < 3) {
                                        title = 'Video ' + match[1];
                                    }
                                    
                                    let thumbnailUrl = null;
                                    if (match && match[1]) {
                                        thumbnailUrl = `https://img.youtube.com/vi/${match[1]}/maxresdefault.jpg`;
                                    }
                                    videos.push({
                                        title: title,
                                        url: url,
                                        channelName: null,
                                        duration: null,
                                        thumbnailUrl: thumbnailUrl
                                    });
                                    
                                    if (videos.length >= 10) break;
                                }
                                
                                return videos;
                            }
                        """)
                        
                        if isinstance(fallback_videos, list) and len(fallback_videos) > 0:
                            print(f"Fallback extraction found {len(fallback_videos)} videos")
                            videos = fallback_videos
                    
                    filtered_videos = []
                    seen_urls = set()
                    video_index = 0
                    
                    for video in videos:
                        if len(filtered_videos) >= max_videos:
                            break
                        
                        video_index += 1
                        
                        if video_index == 1:
                            print(f"Skipping first video (likely ad): {video.get('title', 'Unknown')}")
                            continue
                        
                        url = video.get("url", "")
                        if not url:
                            continue
                        
                        if not url.startswith("http"):
                            url = f"https://www.youtube.com{url}"
                        
                        if "/watch" not in url:
                            continue
                        
                        import re
                        video_id_match = re.search(r'[?&]v=([a-zA-Z0-9_-]{11})', url)
                        if not video_id_match:
                            print(f"Skipping invalid URL: {url}")
                            continue
                        
                        video_id = video_id_match.group(1)
                        url = f"https://www.youtube.com/watch?v={video_id}"
                        
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        
                        title = video.get("title") or "Unknown Title"
                        duration = video.get("duration")
                        channel_name = video.get("channelName")
                        thumbnail_url = video.get("thumbnailUrl")
                        
                        if (not title or title.startswith("Video ") or title == "Unknown Title" or not duration or not thumbnail_url):
                            send_status("info", f"Fetching metadata for video {len(filtered_videos) + 1}...")
                            try:
                                import yt_dlp
                                ydl_opts = {
                                    'quiet': True,
                                    'no_warnings': True,
                                    'extract_flat': False,
                                }
                                
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                    info = ydl.extract_info(url, download=False)
                                    if info:
                                        if (not title or title.startswith("Video ") or title == "Unknown Title"):
                                            title = info.get('title', title)
                                        if not duration:
                                            duration_seconds = info.get('duration', 0)
                                            if duration_seconds:
                                                hours = duration_seconds // 3600
                                                minutes = (duration_seconds % 3600) // 60
                                                seconds = duration_seconds % 60
                                                if hours > 0:
                                                    duration = f"{hours}:{minutes:02d}:{seconds:02d}"
                                                else:
                                                    duration = f"{minutes}:{seconds:02d}"
                                        if not channel_name:
                                            channel_name = info.get('channel', info.get('uploader', channel_name))
                                        if not thumbnail_url:
                                            thumbnail_url = info.get('thumbnail') or info.get('thumbnails', [{}])[0].get('url') if info.get('thumbnails') else None
                            except Exception as e:
                                pass
                        
                        if not thumbnail_url:
                            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                        
                        title_stripped = title.strip()
                        ad_keywords = ["Watch", "watch"]
                        if title_stripped in ad_keywords or (len(title_stripped) < 5 and title_stripped.lower() in ["ad", "ads"]):
                            print(f"Skipping likely ad video (title: '{title_stripped}'): {url}")
                            continue
                        
                        video_data = {
                            "title": title,
                            "url": url,
                            "duration": duration,
                            "channelName": channel_name,
                            "thumbnailUrl": thumbnail_url
                        }
                        
                        filtered_videos.append(video_data)
                    
                    send_status("success", f"Found {len(filtered_videos)} videos")
                    print(f"\nFound {len(filtered_videos)} videos:")
                    for index, video in enumerate(filtered_videos, 1):
                        print(f"\n   {index}. {video.get('title', 'Unknown')}")
                        print(f"      URL: {video.get('url', 'N/A')}")
                        print(f"      Duration: {video.get('duration', 'N/A')}")
                        if video.get('channelName'):
                            print(f"      Channel: {video.get('channelName')}")
                        if video.get('thumbnailUrl'):
                            print(f"      Thumbnail: {video.get('thumbnailUrl')}")
                    
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
                try:
                    print(f"Session completed: {session.id}")
                except Exception as e:
                    print(f"Warning: Could not close session: {str(e)}")
