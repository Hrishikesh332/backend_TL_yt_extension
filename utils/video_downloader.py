import yt_dlp
import os
import time


def download_youtube_video(url, output_path):
    proxy_url = os.environ.get('PROXY_URL')
    
    # Get cookies file path - check multiple locations
    cookies_file = None
    cookies_paths = [
        '/etc/secrets/cookies.txt',  # Render deployment (check first)
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cookies.txt'),  # Local: project root
        os.path.join(os.getcwd(), 'cookies.txt'),  # Current working directory
    ]
    
    print(f"[DEBUG] Checking cookies paths...")
    for path in cookies_paths:
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        readable = False
        first_line = ""
        if exists:
            try:
                with open(path, 'r') as f:
                    first_line = f.readline().strip()
                    readable = True
            except Exception as e:
                print(f"[DEBUG]   {path}: exists but cannot read: {e}")
        print(f"[DEBUG]   {path}: exists={exists}, size={size}, readable={readable}")
        if exists and size > 0 and readable:
            cookies_file = path
            print(f"[DEBUG] ✅ Using cookies from: {cookies_file}")
            print(f"[DEBUG]   First line: {first_line[:50]}...")
            break
    
    cookies_available = cookies_file is not None
    if not cookies_available:
        print(f"[DEBUG] ❌ No cookies file found in any location")
    
    if cookies_available:
        print(f"[COOKIES] Using cookies file: {cookies_file}")
    else:
        print("[COOKIES] No cookies file found")
    
    if proxy_url:
        print(f"[PROXY] Proxy available: {proxy_url[:50]}...")
    else:
        print("[PROXY] No proxy configured.")
    
    # Strategy: Try different combinations
    strategies = []
    
    if cookies_available:
        strategies.append({'use_cookies': True, 'use_proxy': False, 'fake_ip': False, 'name': 'Cookies only'})
        if proxy_url:
            strategies.append({'use_cookies': True, 'use_proxy': True, 'fake_ip': False, 'name': 'Cookies + Proxy'})
            strategies.append({'use_cookies': True, 'use_proxy': True, 'fake_ip': True, 'name': 'Cookies + Proxy + FakeIP'})
    
    if proxy_url:
        strategies.append({'use_cookies': False, 'use_proxy': True, 'fake_ip': False, 'name': 'Proxy only'})
        strategies.append({'use_cookies': False, 'use_proxy': True, 'fake_ip': True, 'name': 'Proxy + FakeIP'})
    
    # Fallback: no cookies, no proxy
    strategies.append({'use_cookies': False, 'use_proxy': False, 'fake_ip': False, 'name': 'Direct'})
    
    last_error = None
    
    for strategy_idx, strategy in enumerate(strategies):
        print(f"\n[STRATEGY {strategy_idx + 1}/{len(strategies)}] {strategy['name']}")
        
        for attempt in range(3):
            try:
                # Fake IP configurations - different countries and IPs
                fake_ip_configs = [
                    {'country': 'US', 'ip': '104.28.45.67', 'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
                    {'country': 'GB', 'ip': '185.199.108.153', 'ua': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'},
                    {'country': 'DE', 'ip': '138.201.81.199', 'ua': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'},
                    {'country': 'CA', 'ip': '99.79.189.123', 'ua': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'},
                ]
                
                # Select fake IP config based on attempt
                fake_config = fake_ip_configs[attempt % len(fake_ip_configs)]
                
                # Base headers
                http_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                }
                
                geo_country = 'US'
                
                # Apply fake IP settings
                if strategy.get('fake_ip'):
                    http_headers = {
                        'User-Agent': fake_config['ua'],
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'X-Forwarded-For': fake_config['ip'],
                        'X-Real-IP': fake_config['ip'],
                        'CF-Connecting-IP': fake_config['ip'],
                    }
                    geo_country = fake_config['country']
                    print(f"[FAKE-IP] Using IP: {fake_config['ip']} Country: {geo_country}")
                
                ydl_opts = {
                    'format': '18/22/best[ext=mp4]/best',
                    'outtmpl': output_path,
                    'quiet': False,
                    'no_warnings': True,
                    'ignoreerrors': False,
                    'noplaylist': True,
                    'merge_output_format': 'mp4',
                    'http_headers': http_headers,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['ios', 'android'],
                            'player_skip': ['webpage', 'configs'],
                        }
                    },
                    'geo_bypass': True,
                    'geo_bypass_country': geo_country,
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
