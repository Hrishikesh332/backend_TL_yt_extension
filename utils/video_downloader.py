import yt_dlp
import os
import time


def download_youtube_video(url, output_path):
    proxy_url = os.environ.get('PROXY_URL')
    
    # Get cookies file path - check multiple locations
    cookies_file = None
    cookies_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cookies.txt'),  # Local: project root
        '/etc/secrets/cookies.txt',  # Render deployment
        os.path.join(os.getcwd(), 'cookies.txt'),  # Current working directory
    ]
    
    for path in cookies_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            cookies_file = path
            break
    
    cookies_available = cookies_file is not None
    
    if cookies_available:
        print(f"[COOKIES] Using cookies file: {cookies_file}")
    else:
        print("[COOKIES] No cookies file found")
    
    if proxy_url:
        print(f"[PROXY] Proxy available: {proxy_url[:50]}...")
    else:
        print("[PROXY] No proxy configured.")
    
    # Strategy: Try cookies without proxy first, then with proxy
    strategies = []
    
    if cookies_available:
        strategies.append({'use_cookies': True, 'use_proxy': False, 'name': 'Cookies only'})
        if proxy_url:
            strategies.append({'use_cookies': True, 'use_proxy': True, 'name': 'Cookies + Proxy'})
    
    if proxy_url:
        strategies.append({'use_cookies': False, 'use_proxy': True, 'name': 'Proxy only'})
    
    # Fallback: no cookies, no proxy
    strategies.append({'use_cookies': False, 'use_proxy': False, 'name': 'Direct'})
    
    last_error = None
    
    for strategy_idx, strategy in enumerate(strategies):
        print(f"\n[STRATEGY {strategy_idx + 1}/{len(strategies)}] {strategy['name']}")
        
        for attempt in range(3):
            try:
                ydl_opts = {
                    'format': '18/22/best[ext=mp4]/best',
                    'outtmpl': output_path,
                    'quiet': False,
                    'no_warnings': True,
                    'ignoreerrors': False,
                    'noplaylist': True,
                    'merge_output_format': 'mp4',
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                    },
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['ios', 'android'],
                            'player_skip': ['webpage', 'configs'],
                        }
                    },
                    'geo_bypass': True,
                    'geo_bypass_country': 'US',
                    'nocheckcertificate': True,
                    'socket_timeout': 60,
                    'retries': 5,
                    'fragment_retries': 5,
                    'skip_unavailable_fragments': True,
                    'source_address': '0.0.0.0',
                }
                
                # Apply strategy
                if strategy['use_proxy'] and proxy_url:
                    ydl_opts['proxy'] = proxy_url
                    os.environ['HTTP_PROXY'] = proxy_url
                    os.environ['HTTPS_PROXY'] = proxy_url
                    os.environ['http_proxy'] = proxy_url
                    os.environ['https_proxy'] = proxy_url
                else:
                    # Clear proxy env vars
                    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
                        if key in os.environ:
                            del os.environ[key]
                
                if strategy['use_cookies'] and cookies_available:
                    ydl_opts['cookiefile'] = cookies_file
                
                print(f"[DOWNLOAD] Attempt {attempt + 1}/3")
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    print(f"[DOWNLOAD] Extracting video info from: {url}")
                    info = ydl.extract_info(url, download=False)
                    
                    if info is None:
                        raise Exception("Failed to extract video info")
                    
                    video_title = info.get('title', 'video')
                    print(f"[DOWNLOAD] Found video: {video_title}")
                    print(f"[DOWNLOAD] Starting download...")
                    
                    ydl.download([url])
                    
                    if os.path.exists(output_path):
                        print(f"[DOWNLOAD] Success! File saved to: {output_path}")
                        return output_path
                    
                    output_dir = os.path.dirname(output_path)
                    base_name_without_ext = os.path.splitext(os.path.basename(output_path))[0]
                    
                    if os.path.exists(output_dir):
                        for filename in os.listdir(output_dir):
                            if filename.startswith(base_name_without_ext):
                                full_path = os.path.join(output_dir, filename)
                                if os.path.isfile(full_path) and not filename.endswith('.part'):
                                    print(f"[DOWNLOAD] Success! File saved to: {full_path}")
                                    return full_path
                    
                    base_name = os.path.splitext(output_path)[0]
                    for ext in ['.mkv', '.mp4', '.webm', '.m4a']:
                        if os.path.exists(base_name + ext):
                            print(f"[DOWNLOAD] Success! File saved to: {base_name + ext}")
                            return base_name + ext
                    
                    raise Exception(f"Downloaded file not found. Expected: {output_path}")
                    
            except Exception as e:
                last_error = str(e)
                print(f"[ERROR] Attempt {attempt + 1}: {last_error}")
                
                # If bot detection, try next strategy immediately
                if 'bot' in str(e).lower() or 'sign in' in str(e).lower():
                    print(f"[INFO] Bot detection, trying next strategy...")
                    break
                
                if attempt < 2:
                    wait_time = 2 * (attempt + 1)
                    print(f"[RETRY] Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
    
    raise Exception(f"Error downloading video after trying all strategies: {last_error}")
